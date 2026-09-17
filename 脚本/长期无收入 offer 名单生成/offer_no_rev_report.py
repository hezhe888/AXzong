# -*- coding: utf-8 -*-
"""长期无收入 offer 名单生成

规则:
  1) 入库满 N 天（从监控首现日算起）
  2) 最近 M 天内无收入（Revenue=0）
  3) 最近 K 天内至少一天在线
  4) 按全程 Revenue 降序排列
"""
import os
import sys
import csv
from datetime import datetime, timedelta

import pymysql

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(SCRIPT_DIR, '长期无收入 offer 名单生成结果')
ENV_KEYS = ['DB_HOST', 'DB_PORT', 'DB_USER', 'DB_PASSWORD', 'DB_NAME']


def load_env():
    env = {}
    missing = []
    for k in ENV_KEYS:
        v = os.environ.get(k)
        if v:
            env[k] = v
        else:
            missing.append(k)
    if missing:
        env_path = os.path.join(SCRIPT_DIR, 'db.env')
        if os.path.exists(env_path):
            with open(env_path, 'r', encoding='utf-8-sig') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#') or '=' not in line:
                        continue
                    k, _, v = line.partition('=')
                    k = k.strip()
                    v = v.strip().strip('"').strip("'")
                    if k in missing and v:
                        env[k] = v
    miss2 = [k for k in ENV_KEYS if not env.get(k)]
    if miss2:
        raise SystemExit('缺少数据库配置: ' + ', '.join(miss2) + '（检查环境变量或同目录 db.env）')
    return env


def parse_args():
    days = 15
    no_rev_days = 15
    active_days = 1
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        a = args[i]
        if a == '--days' and i + 1 < len(args):
            days = int(args[i + 1])
            i += 2
        elif a == '--no-rev-days' and i + 1 < len(args):
            no_rev_days = int(args[i + 1])
            i += 2
        elif a == '--active-days' and i + 1 < len(args):
            active_days = int(args[i + 1])
            i += 2
        else:
            i += 1
    return days, no_rev_days, active_days


def unique_path(path):
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    n = 2
    while True:
        p = f'{base}_{n}{ext}'
        if not os.path.exists(p):
            return p
        n += 1


def main():
    days, no_rev_days, active_days = parse_args()
    env = load_env()
    os.makedirs(OUT_DIR, exist_ok=True)

    conn = pymysql.connect(
        host=env['DB_HOST'], port=int(env['DB_PORT']), user=env['DB_USER'],
        password=env['DB_PASSWORD'], database=env['DB_NAME'],
        charset='utf8mb4', autocommit=True,
    )
    cur = conn.cursor()

    cur.execute('SELECT MAX(date) FROM offerplus_offer_daily_status')
    base_date = cur.fetchone()[0]
    if not base_date:
        raise SystemExit('daily_status 无数据，无法确定基准日')

    base_dt = datetime.strptime(base_date, '%Y%m%d')
    cutoff = (base_dt - timedelta(days=days)).strftime('%Y%m%d')
    rev_start = (base_dt - timedelta(days=no_rev_days - 1)).strftime('%Y%m%d')
    active_start = (base_dt - timedelta(days=active_days - 1)).strftime('%Y%m%d')

    cur.execute('DROP TEMPORARY TABLE IF EXISTS tmp_act')
    cur.execute('DROP TEMPORARY TABLE IF EXISTS tmp_first')
    cur.execute('DROP TEMPORARY TABLE IF EXISTS tmp_rev')
    cur.execute('DROP TEMPORARY TABLE IF EXISTS tmp_revall')
    cur.execute(
        'CREATE TEMPORARY TABLE tmp_act AS '
        'SELECT DISTINCT offer_id FROM offerplus_offer_daily_status '
        'WHERE date BETWEEN %s AND %s AND has_online=1',
        (active_start, base_date),
    )
    cur.execute(
        'CREATE TEMPORARY TABLE tmp_first AS '
        'SELECT offer_id, MIN(date) f FROM offerplus_offer_daily_status GROUP BY offer_id'
    )
    cur.execute(
        'CREATE TEMPORARY TABLE tmp_rev AS '
        'SELECT adgroup_id oid, SUM(revenue) rv, SUM(click) clk, SUM(conversion) cv '
        'FROM offerplus_detail_report WHERE date BETWEEN %s AND %s GROUP BY adgroup_id',
        (rev_start, base_date),
    )
    cur.execute(
        'CREATE TEMPORARY TABLE tmp_revall AS '
        'SELECT adgroup_id oid, SUM(revenue) rv, SUM(click) clk '
        'FROM offerplus_detail_report GROUP BY adgroup_id'
    )

    sql = '''
    SELECT t.offer_id, f.f,
           COALESCE(r.rv,0), COALESCE(r.clk,0), COALESCE(r.cv,0),
           CASE WHEN COALESCE(r.clk,0)>0 THEN COALESCE(r.rv,0)/r.clk*1000 ELSE 0 END ecpc_m,
           COALESCE(ra.rv,0),
           CASE WHEN COALESCE(ra.clk,0)>0 THEN COALESCE(ra.rv,0)/ra.clk*1000 ELSE 0 END ecpc_all
    FROM tmp_act t
    JOIN tmp_first f ON t.offer_id=f.offer_id
    LEFT JOIN tmp_rev r ON t.offer_id=r.oid
    LEFT JOIN tmp_revall ra ON t.offer_id=ra.oid
    WHERE f.f <= %s
      AND (r.rv IS NULL OR r.rv=0)
    ORDER BY COALESCE(ra.rv,0) DESC
    '''
    cur.execute(sql, (cutoff,))
    rows = cur.fetchall()

    fname = f'offer_无收入_{no_rev_days}天_{base_date}.csv'
    out_path = unique_path(os.path.join(OUT_DIR, fname))
    with open(out_path, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow(['Offer ID', '入库日期', f'近{no_rev_days}天Revenue', f'近{no_rev_days}天Click',
                    f'近{no_rev_days}天Conversion', f'近{no_rev_days}天eCPC', '全程Revenue', '全程eCPC'])
        for r in rows:
            w.writerow([r[0], r[1], f'{float(r[2]):.2f}', r[3], r[4], f'{float(r[5]):.2f}',
                        f'{float(r[6]):.2f}', f'{float(r[7]):.2f}'])

    n_stopped = sum(1 for r in rows if float(r[6]) > 0)

    print('=' * 50)
    print(f'基准日: {base_date} | 入库满 {days} 天 | 近 {no_rev_days} 天无收入 | 近 {active_days} 天在线')
    print(f'数量    : {len(rows)} 个')
    print(f'曾有收入后停: {n_stopped} 个')
    print(f'文件    : {out_path}')
    print('=' * 50)

    cur.close()
    conn.close()

    try:
        os.startfile(out_path)
    except Exception:
        pass


if __name__ == '__main__':
    main()
