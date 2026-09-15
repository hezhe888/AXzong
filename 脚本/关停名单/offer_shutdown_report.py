# -*- coding: utf-8 -*-
"""offer 建议关停名单生成

规则:
  A 无流水: 入库>=N天 且 全程 revenue=0
  B 低eCPC : 入库>=N天 且 revenue>0 且 click>0 且 累计 revenue/click*1000 < 阈值
"""
import os
import sys
import csv
from datetime import datetime, timedelta

import pymysql

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(SCRIPT_DIR, '关停名单结果')
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
    days = 7
    active_days = 3
    ecpc = 0.1
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        a = args[i]
        if a == '--days' and i + 1 < len(args):
            days = int(args[i + 1])
            i += 2
        elif a == '--active-days' and i + 1 < len(args):
            active_days = int(args[i + 1])
            i += 2
        elif a == '--ecpc' and i + 1 < len(args):
            ecpc = float(args[i + 1])
            i += 2
        else:
            i += 1
    return days, active_days, ecpc


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
    days, active_days, ecpc = parse_args()
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
    active_start = (base_dt - timedelta(days=active_days - 1)).strftime('%Y%m%d')

    cur.execute('DROP TEMPORARY TABLE IF EXISTS tmp_act')
    cur.execute('DROP TEMPORARY TABLE IF EXISTS tmp_first')
    cur.execute('DROP TEMPORARY TABLE IF EXISTS tmp_agg')
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
        'CREATE TEMPORARY TABLE tmp_agg AS '
        'SELECT adgroup_id oid, SUM(revenue) rv, SUM(click) clk, SUM(conversion) cv '
        'FROM offerplus_detail_report GROUP BY adgroup_id'
    )

    sql = '''
    SELECT t.offer_id, f.f,
           (SELECT MAX(date) FROM offerplus_offer_daily_status s
             WHERE s.offer_id=t.offer_id AND s.date BETWEEN %s AND %s AND s.has_online=1) last_on,
           COALESCE(a.rv,0), COALESCE(a.clk,0), COALESCE(a.cv,0),
           CASE WHEN COALESCE(a.rv,0)=0 THEN 'A:无流水' ELSE 'B:低ecpc' END cond
    FROM tmp_act t
    JOIN tmp_first f ON t.offer_id=f.offer_id
    LEFT JOIN tmp_agg a ON t.offer_id=a.oid
    WHERE f.f <= %s
      AND (COALESCE(a.rv,0)=0 OR (a.rv>0 AND a.clk>0 AND a.rv/a.clk*1000 < %s))
    ORDER BY cond, t.offer_id
    '''
    cur.execute(sql, (active_start, base_date, cutoff, ecpc))
    rows = cur.fetchall()

    out_path = unique_path(os.path.join(OUT_DIR, f'offer_建议关停_{base_date}.csv'))
    with open(out_path, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow(['Offer ID', '入库日期', f'最后在线日期(近{active_days}天)', '全程Revenue',
                    '全程Click', '全程Conversion', '命中条件'])
        for r in rows:
            w.writerow([r[0], r[1], r[2] or '', f'{float(r[3]):.2f}', r[4], r[5], r[6]])

    n_a = sum(1 for r in rows if r[6].startswith('A'))
    n_b = len(rows) - n_a

    print('=' * 50)
    print(f'基准日: {base_date} | 入库满 {days} 天 | 近 {active_days} 天活跃 | eCPC < {ecpc}')
    print(f'A 无流水: {n_a} 个')
    print(f'B 低eCPC: {n_b} 个')
    print(f'合计    : {len(rows)} 个')
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
