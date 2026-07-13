"""
Reject Rate Daily Alert
- Fetches reject data for adv id 130010 (1-2 days)
- Alerts on reject_rate > 5%
- Per-row detail with country breakdown
- Pushes to Feishu webhook
"""

import pymysql
import json
import os
import sys
import traceback
import urllib.request
from datetime import datetime, timedelta, timezone
from collections import defaultdict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def _load_webhooks():
    urls = []
    if 'FEISHU_WEBHOOK' in os.environ and os.environ['FEISHU_WEBHOOK']:
        urls.extend(u.strip() for u in os.environ['FEISHU_WEBHOOK'].split(',') if u.strip())
    i = 2
    while f'FEISHU_WEBHOOK_{i}' in os.environ:
        val = os.environ[f'FEISHU_WEBHOOK_{i}']
        if val:
            urls.append(val.strip())
        i += 1
    if not urls:
        raise ValueError("No FEISHU_WEBHOOK configured")
    return urls


WEBHOOK_URLS = _load_webhooks()

DB_CONFIG = {
    'host': os.environ['DB_HOST'],
    'port': int(os.environ['DB_PORT']),
    'user': os.environ['DB_USER'],
    'password': os.environ['DB_PASSWORD'],
    'database': os.environ['DB_NAME'],
    'charset': 'utf8mb4',
}

ADV_ID = os.environ.get('ADV_ID', '130010')
ADV_NAME = os.environ.get('ADV_NAME', 'Appnext-Click')
REJECT_RATE_THRESHOLD = float(os.environ.get('REJECT_RATE_THRESHOLD', '0.05'))
MAX_RETRIES = 3


def get_dates(args):
    if len(args) >= 2:
        return sorted(args[:2])
    if len(args) == 1:
        return [args[0]]
    beijing = timezone(timedelta(hours=8))
    now_beijing = datetime.now(beijing)
    yesterday = (now_beijing - timedelta(days=1)).strftime('%Y%m%d')
    return [yesterday]


def send_feishu(text):
    payload = json.dumps({
        "msg_type": "text",
        "content": {"text": text}
    }, ensure_ascii=False).encode('utf-8')

    results = []
    for url in WEBHOOK_URLS:
        req = urllib.request.Request(
            url,
            data=payload,
            headers={'Content-Type': 'application/json; charset=utf-8'}
        )
        resp = urllib.request.urlopen(req, timeout=30)
        result = json.loads(resp.read().decode('utf-8'))
        if result.get('code') != 0:
            raise Exception(f"Feishu API error ({url[-20:]}...): {result}")
        results.append(result)
    return results


def fetch_reject_records(dates):
    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()

    placeholders = ','.join(['%s'] * len(dates))
    params = [ADV_ID] + dates + [REJECT_RATE_THRESHOLD]

    sql = f'''
    SELECT
        date,
        adgroup_id,
        pkg_name,
        adv_country,
        reject,
        conversion
    FROM offerplus_detail_report
    WHERE src = %s AND date IN ({placeholders}) AND reject > 0
    '''

    cursor.execute(sql, [ADV_ID] + dates)
    rows = cursor.fetchall()

    results = []
    for row in rows:
        date_str = row[0]
        oid = row[1]
        pkg = row[2]
        country = row[3]
        reject = int(row[4]) if row[4] else 0
        conv = int(row[5]) if row[5] else 0

        if conv == 0 and reject > 0:
            rate = 1.0
        elif conv == 0:
            rate = 0
        else:
            rate = reject / conv

        if rate > REJECT_RATE_THRESHOLD:
            results.append((date_str, oid, pkg, country, reject, conv, rate))

    cursor.close()
    conn.close()

    results.sort(key=lambda x: (x[0], -x[4]))
    return results


def build_message(dates, records):
    beijing = timezone(timedelta(hours=8))
    now_beijing = datetime.now(beijing)
    threshold_pct = int(REJECT_RATE_THRESHOLD * 100)

    if len(dates) == 1:
        date_range = f"{dates[0][:4]}-{dates[0][4:6]}-{dates[0][6:]}"
    else:
        date_range = f"{dates[0][:4]}-{dates[0][4:6]}-{dates[0][6:]} ~ {dates[1][:4]}-{dates[1][4:6]}-{dates[1][6:]}"

    lines = [
        f"{date_range} Reject拒绝率预警（reject_rate > {threshold_pct}%）",
        f"📡 来源：{ADV_NAME}（{ADV_ID}）",
    ]

    by_date = defaultdict(list)
    for r in records:
        by_date[r[0]].append(r)

    if not records:
        lines.append(f"⚠️ 未发现拒绝率超过 {threshold_pct}% 的记录")
    else:
        date_counts = {}
        total_records = len(records)
        for d in dates:
            date_counts[d] = len(by_date.get(d, []))
        count_parts = ' / '.join(f"{d[4:6]}-{d[6:]}: {date_counts[d]}条" for d in dates if date_counts.get(d, 0) > 0)
        lines.append(f"⚠️ 共发现 {total_records} 条异常记录（{count_parts}）")

    lines.append("━" * 30)
    lines.append(f"\nPub: {ADV_NAME} ({ADV_ID})\n")

    for d in dates:
        if d not in by_date or not by_date[d]:
            continue
        day_records = by_date[d]
        date_display = f"{d[:4]}-{d[4:6]}-{d[6:]}"
        lines.append(f"📅 {date_display}")

        unique_offers = set()
        for i, r in enumerate(day_records):
            is_last = (i == len(day_records) - 1)
            prefix = "└─" if is_last else "├─"
            oid = r[1] or '-'
            pkg = r[2] or '-'
            country = r[3] or '-'
            reject = r[4]
            conv = r[5]
            rate = r[6]
            lines.append(f"{prefix} Offer: {oid} ({pkg}) | 国家: {country} | Reject率: {rate:.1%} | 拒绝数: {reject} | 转化数: {conv}")
            unique_offers.add(oid)

        offer_list = '|'.join(sorted(unique_offers, key=lambda x: str(x)))
        lines.append(f"总计{len(day_records)}条 / {len(unique_offers)}个Offer：{offer_list}\n")

    lines.append("━" * 30)
    lines.append(f"🕐 执行时间：{now_beijing.strftime('%Y-%m-%d %H:%M:%S')} CST")
    return "\n".join(lines)


def send_error_alert(error_msg):
    try:
        send_feishu(f"[Reject 推送异常]\n{error_msg}")
    except Exception:
        print(f"Failed to send error alert: {traceback.format_exc()}", file=sys.stderr)


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('dates', nargs='*', help='Date(s) in YYYYMMDD format (default: yesterday)')
    args = parser.parse_args()

    dates = get_dates(args.dates)

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            records = fetch_reject_records(dates)
            message = build_message(dates, records)
            print(message)
            result = send_feishu(message)
            print(f"Sent successfully: {result}")
            return

        except Exception as e:
            error_detail = traceback.format_exc()
            print(f"Attempt {attempt}/{MAX_RETRIES} failed: {e}", file=sys.stderr)

            if attempt < MAX_RETRIES:
                continue

            error_msg = (
                f"日期: {dates}\n"
                f"重试次数: {MAX_RETRIES}\n"
                f"错误信息: {str(e)}\n\n"
                f"详细堆栈:\n{error_detail}"
            )
            send_error_alert(error_msg)
            sys.exit(1)


if __name__ == '__main__':
    main()
