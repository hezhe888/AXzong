"""
JK Channel Daily Revenue Report
- Fetches previous day's revenue data (merged across all JK pubs)
- Pushes to Feishu webhook at scheduled time
- Retries on failure, sends error alerts
"""

import pymysql
import json
import os
import sys
import traceback
from datetime import datetime, timedelta, timezone
import urllib.request

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
def _load_webhooks():
    urls = []
    # Primary webhook
    if 'FEISHU_WEBHOOK' in os.environ and os.environ['FEISHU_WEBHOOK']:
        urls.extend(u.strip() for u in os.environ['FEISHU_WEBHOOK'].split(',') if u.strip())
    # Additional webhooks via FEISHU_WEBHOOK_2, FEISHU_WEBHOOK_3, etc.
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
    'host': os.environ.get('DB_HOST', '116.204.109.33'),
    'port': int(os.environ.get('DB_PORT', '34000')),
    'user': os.environ.get('DB_USER', 'affiliate'),
    'password': os.environ['DB_PASSWORD'],
    'database': os.environ.get('DB_NAME', 'affiliate'),
    'charset': 'utf8mb4',
}

MAX_RETRIES = 3


def load_jk_mids():
    raw = os.environ.get('JK_MIDS', '')
    jk_mids = [m.strip() for m in raw.split(',') if m.strip()]
    if not jk_mids:
        raise ValueError("No JK_MIDS configured")
    return jk_mids


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


def fetch_jk_report(date_str):
    jk_mids = load_jk_mids()
    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()
    placeholders = ','.join(['%s'] * len(jk_mids))

    sql_total = f'''
    SELECT ROUND(SUM(revenue), 2)
    FROM offerplus_detail_report
    WHERE mid IN ({placeholders}) AND date = %s
    '''
    cursor.execute(sql_total, jk_mids + [date_str])
    row = cursor.fetchone()
    total_rev = float(row[0]) if row and row[0] else 0.0

    sql_detail = f'''
    SELECT adgroup_id, pkg_name, adv_country, ROUND(SUM(revenue), 2) as rev
    FROM offerplus_detail_report
    WHERE mid IN ({placeholders}) AND date = %s AND revenue > 0
    GROUP BY adgroup_id, pkg_name, adv_country
    ORDER BY rev DESC
    '''
    cursor.execute(sql_detail, jk_mids + [date_str])
    details = cursor.fetchall()

    cursor.close()
    conn.close()
    return total_rev, details


def build_message(date_str, total_rev, details):
    beijing = timezone(timedelta(hours=8))
    now_beijing = datetime.now(beijing)
    date_display = f"{date_str[:4]}年{int(date_str[4:6])}月{int(date_str[6:])}日"

    lines = [
        f"{date_display} jk总Revenue：{total_rev}",
        "",
    ]
    if details:
        for d in details:
            lines.append(f"{d[0]} {d[1]} {d[2]}---{d[3]}")
    else:
        lines.append("（当天无Revenue数据）")

    lines.append("")
    lines.append(f"推送时间：{now_beijing.strftime('%Y-%m-%d %H:%M:%S')} (北京时间)")
    return "\n".join(lines)


def send_error_alert(error_msg):
    try:
        send_feishu(f"[JK Revenue 推送异常]\n{error_msg}")
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
            total_rev, details = fetch_jk_report(date_str)

            if attempt == 1:
                pass
            else:
                print(f"Retry {attempt} succeeded")

            message = build_message(date_str, total_rev, details)
            result = send_feishu(message)
            print(f"Sent successfully: {result}")
            return

        except Exception as e:
            error_detail = traceback.format_exc()
            print(f"Attempt {attempt}/{MAX_RETRIES} failed: {e}", file=sys.stderr)

            if attempt < MAX_RETRIES:
                continue

            error_msg = (
                f"日期：{date_str}\n"
                f"重试次数：{MAX_RETRIES}\n"
                f"错误信息：{str(e)}\n\n"
                f"详细堆栈：\n{error_detail}"
            )
            send_error_alert(error_msg)
            sys.exit(1)


if __name__ == '__main__':
    main()
