"""
Reject Rate Daily Report
- Fetches previous day's reject data for adv id 130010
- Finds offers with reject_rate > 20%
- Sorted by reject count descending
- Pushes to Feishu webhook
"""

import pymysql
import json
import os
import sys
import traceback
import urllib.request
from datetime import datetime, timedelta, timezone

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
REJECT_RATE_THRESHOLD = float(os.environ.get('REJECT_RATE_THRESHOLD', '0.20'))
MAX_RETRIES = 3


def get_yesterday_date():
    beijing = timezone(timedelta(hours=8))
    now_beijing = datetime.now(beijing)
    yesterday = now_beijing - timedelta(days=1)
    return yesterday.strftime('%Y%m%d')


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


def fetch_high_reject_offers(date_str):
    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()

    sql = '''
    SELECT
        adgroup_id,
        pkg_name,
        SUM(reject) as total_reject,
        SUM(conversion) as total_conversion,
        ROUND(SUM(reject) * 1.0 / NULLIF(SUM(conversion), 0), 4) as reject_rate
    FROM offerplus_detail_report
    WHERE src = %s AND date = %s
    GROUP BY adgroup_id, pkg_name
    HAVING reject_rate > %s AND total_reject > 0
    ORDER BY total_reject DESC
    '''
    cursor.execute(sql, [ADV_ID, date_str, REJECT_RATE_THRESHOLD])
    results = cursor.fetchall()

    sql_overall = '''
    SELECT
        SUM(reject) as total_reject,
        SUM(conversion) as total_conversion,
        ROUND(SUM(reject) * 1.0 / NULLIF(SUM(conversion), 0), 4) as reject_rate
    FROM offerplus_detail_report
    WHERE src = %s AND date = %s
    '''
    cursor.execute(sql_overall, [ADV_ID, date_str])
    overall = cursor.fetchone()

    cursor.close()
    conn.close()
    return results, overall


def build_message(date_str, offers, overall):
    beijing = timezone(timedelta(hours=8))
    now_beijing = datetime.now(beijing)
    date_display = f"{date_str[:4]}年{int(date_str[4:6])}月{int(date_str[6:])}日"

    overall_reject = int(overall[0]) if overall and overall[0] else 0
    overall_conv = int(overall[1]) if overall and overall[1] else 0
    overall_rate = float(overall[2]) if overall and overall[2] else 0

    lines = [
        f"{date_display} Adv {ADV_ID} Reject 日报",
        f"总体: Reject={overall_reject}  Conversion={overall_conv}  RejectRate={overall_rate:.2%}",
        f"阈值: RejectRate > {REJECT_RATE_THRESHOLD:.0%}",
        "",
    ]

    if offers:
        lines.append(f"{'Offer ID':<15} {'包名':<50} {'Reject':>8} {'Conversion':>12} {'RejectRate':>10}")
        lines.append("-" * 100)
        for o in offers:
            oid = o[0] or '-'
            pkg = o[1] or '-'
            rej = int(o[2]) if o[2] else 0
            conv = int(o[3]) if o[3] else 0
            rate = float(o[4]) if o[4] else 0
            lines.append(f"{oid:<15} {pkg:<50} {rej:>8} {conv:>12} {rate:>9.2%}")
        lines.append("")
        lines.append(f"共 {len(offers)} 个 offer 超过阈值")
    else:
        lines.append("无超过阈值的 offer")

    lines.append("")
    lines.append(f"推送时间: {now_beijing.strftime('%Y-%m-%d %H:%M:%S')} (北京时间)")
    return "\n".join(lines)


def send_error_alert(error_msg):
    try:
        send_feishu(f"[Reject 推送异常]\n{error_msg}")
    except Exception:
        print(f"Failed to send error alert: {traceback.format_exc()}", file=sys.stderr)


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('date', nargs='?', help='Date in YYYYMMDD format (default: yesterday)')
    args = parser.parse_args()
    date_str = args.date if args.date else get_yesterday_date()

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            offers, overall = fetch_high_reject_offers(date_str)

            if attempt == 1:
                pass
            else:
                print(f"Retry {attempt} succeeded")

            message = build_message(date_str, offers, overall)
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
                f"日期: {date_str}\n"
                f"重试次数: {MAX_RETRIES}\n"
                f"错误信息: {str(e)}\n\n"
                f"详细堆栈:\n{error_detail}"
            )
            send_error_alert(error_msg)
            sys.exit(1)


if __name__ == '__main__':
    main()
