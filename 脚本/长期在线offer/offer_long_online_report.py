# -*- coding: utf-8 -*-
"""长期在线 offer 名单生成（push 用）

规则:
  1) 当前在线: 基准日最后一个非 NULL 小时 = 1
  2) 连续在线 >= min_hours: 从当前小时往前逐小时数, 遇 0 或某天无记录即中断
  3) ecpc > 0 时: 再筛 全程 payout/click*1000 > 阈值 (ecpc=0 则不筛)
  4) min_conv > 0 时: 再筛 全程转化数 SUM(conversion) >= min_conv (min_conv=0 则不筛)
"""
import os
import sys
import csv
from datetime import datetime, timedelta
from collections import defaultdict

import pymysql

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(SCRIPT_DIR, '长期在线offer结果')
ENV_KEYS = ['DB_HOST', 'DB_PORT', 'DB_USER', 'DB_PASSWORD', 'DB_NAME']

H_COLS = [f'h{i:02d}' for i in range(24)]
COALESCE_COLS = ','.join(f'h{i:02d}' for i in range(23, -1, -1))


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
    min_hours = 48
    ecpc = 0.5
    min_conv = 0
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        a = args[i]
        if a == '--min-hours' and i + 1 < len(args):
            min_hours = int(args[i + 1])
            i += 2
        elif a == '--ecpc' and i + 1 < len(args):
            ecpc = float(args[i + 1])
            i += 2
        elif a == '--min-conv' and i + 1 < len(args):
            min_conv = int(args[i + 1])
            i += 2
        else:
            i += 1
    return min_hours, ecpc, min_conv


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


def calc_streak(base_dt, lookback_days, days_dict):
    total = 0
    i = 0
    while i < lookback_days:
        d = (base_dt - timedelta(days=i)).strftime('%Y%m%d')
        hs = days_dict.get(d)
        if hs is None:
            break
        last = None
        for j in range(23, -1, -1):
            if hs[j] is not None:
                last = j
                break
        if last is None:
            break
        cnt = 0
        for j in range(last, -1, -1):
            if hs[j] == 1:
                cnt += 1
            else:
                break
        total += cnt
        if cnt < last + 1:
            break
        i += 1
    return total


def main():
    min_hours, ecpc, min_conv = parse_args()
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
    lookback_days = max(10, min_hours // 24 + 3)
    start_date = (base_dt - timedelta(days=lookback_days - 1)).strftime('%Y%m%d')

    cur.execute('DROP TEMPORARY TABLE IF EXISTS tmp_cur')
    cur.execute(
        'CREATE TEMPORARY TABLE tmp_cur AS '
        'SELECT offer_id, pkg_name, country FROM offerplus_offer_daily_status '
        f'WHERE date=%s AND COALESCE({COALESCE_COLS})=1',
        (base_date,),
    )
    cur.execute('SELECT COUNT(*) FROM tmp_cur')
    n_online = cur.fetchone()[0]

    cur.execute('SELECT offer_id, pkg_name, country FROM tmp_cur')
    info = {}
    for oid, pkg, country in cur.fetchall():
        info[str(oid)] = (pkg or '', country or '')

    cols = ','.join(H_COLS)
    cur.execute(
        f'SELECT s.offer_id, s.date, {cols} '
        'FROM offerplus_offer_daily_status s '
        'JOIN tmp_cur t ON s.offer_id=t.offer_id '
        'WHERE s.date >= %s',
        (start_date,),
    )
    data = defaultdict(dict)
    for r in cur.fetchall():
        data[str(r[0])][r[1]] = r[2:26]

    hits = []
    for oid, days in data.items():
        st = calc_streak(base_dt, lookback_days, days)
        if st >= min_hours:
            hits.append((oid, st))
    n_streak = len(hits)

    agg = {}
    if hits:
        cur.execute('DROP TEMPORARY TABLE IF EXISTS tmp_out')
        cur.execute(
            'CREATE TEMPORARY TABLE tmp_out ('
            'offer_id varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci)'
        )
        cur.executemany('INSERT INTO tmp_out VALUES (%s)', [(o,) for o, _ in hits])
        cur.execute(
            'SELECT o.offer_id, SUM(d.payout), SUM(d.click), SUM(d.conversion) '
            'FROM tmp_out o '
            'LEFT JOIN offerplus_detail_report d ON o.offer_id=d.adgroup_id '
            'GROUP BY o.offer_id'
        )
        for oid, po, clk, cv in cur.fetchall():
            agg[str(oid)] = (float(po or 0), int(clk or 0), int(cv or 0))

    rows = []
    for oid, st in hits:
        po, clk, cv = agg.get(oid, (0.0, 0, 0))
        epc = po / clk * 1000 if clk > 0 else 0.0
        rows.append((oid, st, po, clk, cv, epc))

    if ecpc > 0:
        rows = [r for r in rows if r[5] > ecpc]
    n_ecpc = len(rows)
    if min_conv > 0:
        rows = [r for r in rows if r[4] >= min_conv]
    n_conv = len(rows)

    rows.sort(key=lambda x: (-x[5], -x[1], x[0]))

    parts = [f'offer_长期在线_{min_hours}h']
    if ecpc > 0:
        parts.append(f'ecpc{ecpc:g}')
    if min_conv > 0:
        parts.append(f'conv{min_conv}')
    parts.append(base_date)
    fname = '_'.join(parts) + '.csv'
    out_path = unique_path(os.path.join(OUT_DIR, fname))
    with open(out_path, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow(['Offer ID', 'pkg_name', 'GEO', '连续在线小时', '全程Payout',
                    '全程Click', '全程Conversion', '全程eCPC'])
        for oid, st, po, clk, cv, epc in rows:
            pkg, country = info.get(oid, ('', ''))
            w.writerow([oid, pkg, country, st, f'{po:.2f}', clk, cv, f'{epc:.2f}'])

    print('=' * 50)
    print(f'基准日: {base_date} | 回溯 {lookback_days} 天')
    print(f'当前在线: {n_online} 个')
    print(f'连续 >= {min_hours} 小时: {n_streak} 个')
    if ecpc > 0:
        print(f'payout eCPC > {ecpc}: {n_ecpc} 个')
    else:
        print('eCPC 筛选: 未启用（阈值=0）')
    if min_conv > 0:
        print(f'转化数 >= {min_conv}: {n_conv} 个')
    else:
        print('转化数筛选: 未启用（阈值=0）')
    print(f'合计输出: {len(rows)} 个')
    print(f'文件: {out_path}')
    print('=' * 50)

    cur.close()
    conn.close()

    try:
        os.startfile(out_path)
    except Exception:
        pass


if __name__ == '__main__':
    main()
