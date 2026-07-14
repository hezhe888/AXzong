"""
Reject Rate Daily Alert
- Fetches reject data for adv id 130010 (1-2 days)
- Alerts on reject_rate > 5%
- Feishu Interactive Card with monospace code-block table
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

COLS = [
    ("Offer ID", 10, 'L'),
    ("包名", 22, 'L'),
    ("Geo", 6, 'L'),
    ("渠道", 18, 'L'),
    ("Conv", 6, 'R'),
    ("Reject", 6, 'R'),
    ("RejectRate", 10, 'R'),
]


def _cjk_width(s):
    w = 0
    for c in str(s):
        cp = ord(c)
        if (0x4E00 <= cp <= 0x9FFF or 0x3000 <= cp <= 0x303F or
                0xFF00 <= cp <= 0xFFEF or 0x2E80 <= cp <= 0x2FDF or
                0x3400 <= cp <= 0x4DBF or 0xF900 <= cp <= 0xFAFF):
            w += 2
        else:
            w += 1
    return w


def _cjk_pad(s, width, align='L'):
    s = str(s)
    cur = _cjk_width(s)
    if cur >= width:
        return s
    pad = width - cur
    if align == 'R':
        return ' ' * pad + s
    else:
        return s + ' ' * pad


def load_pub_mapping():
    if 'PUB_MAPPING' not in os.environ or not os.environ['PUB_MAPPING']:
        return {}
    return json.loads(os.environ['PUB_MAPPING'])


def get_dates(args):
    if len(args) >= 2:
        return sorted(args[:2])
    if len(args) == 1:
        return [args[0]]
    beijing = timezone(timedelta(hours=8))
    now_beijing = datetime.now(beijing)
    today = now_beijing.strftime('%Y%m%d')
    yesterday = (now_beijing - timedelta(days=1)).strftime('%Y%m%d')
    return [yesterday, today]


def send_feishu_card(card):
    payload = json.dumps({
        "msg_type": "interactive",
        "card": card
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

    beijing = timezone(timedelta(hours=8))
    now_beijing = datetime.now(beijing)
    today_str = now_beijing.strftime('%Y%m%d')

    all_rows = []

    past_dates = [d for d in dates if d != today_str]
    if past_dates:
        placeholders = ','.join(['%s'] * len(past_dates))
        sql = f'''
        SELECT date, adgroup_id, pkg_name, COALESCE(adv_country, '-'), mid, reject, conversion
        FROM offerplus_detail_report
        WHERE src = %s AND date IN ({placeholders}) AND reject > 0
        '''
        cursor.execute(sql, [ADV_ID] + past_dates)
        all_rows.extend(cursor.fetchall())

    if today_str in dates:
        sql = f'''
        SELECT date, adgroup_id, pkg_name, COALESCE(adv_country, '-'), mid, reject, conversion
        FROM offerplus_detail_report_snapshot_8
        WHERE src = %s AND date = %s AND reject > 0
        '''
        cursor.execute(sql, [ADV_ID, today_str])
        all_rows.extend(cursor.fetchall())

    pub_mapping = load_pub_mapping()
    unknown_mids = set()

    records = []
    for row in all_rows:
        date_str = row[0]
        oid = row[1]
        pkg = row[2]
        country = row[3] or '-'
        mid = str(row[4]) if row[4] else '-'
        reject = int(row[5]) if row[5] else 0
        conv = int(row[6]) if row[6] else 0

        pub_name = f"{pub_mapping.get(mid, mid)}-{mid}"
        if mid not in pub_mapping and mid != '-':
            unknown_mids.add(mid)

        total = reject + conv
        if total == 0:
            rate = 0
        else:
            rate = reject / total

        if rate > REJECT_RATE_THRESHOLD:
            records.append((date_str, oid, pkg, country, pub_name, conv, reject, rate))

    cursor.close()
    conn.close()

    records.sort(key=lambda x: (x[0], -x[7]))
    return records, unknown_mids


def _build_table(day_records):
    sep = '-' * 84
    lines = []

    header_cols = [_cjk_pad(c[0], c[1], c[2]) for c in COLS]
    lines.append(' '.join(header_cols))
    lines.append(sep)

    for r in day_records:
        oid = r[1] or '-'
        pkg = (r[2] or '-')[:22]
        country = r[3]
        pub = (r[4] or '-')[:18]
        conv = str(r[5])
        reject = str(r[6])
        rate = f"{r[7]:.2%}"

        vals = [
            _cjk_pad(oid, 10, 'L'),
            _cjk_pad(pkg, 22, 'L'),
            _cjk_pad(country, 6, 'L'),
            _cjk_pad(pub, 18, 'L'),
            _cjk_pad(conv, 6, 'R'),
            _cjk_pad(reject, 6, 'R'),
            _cjk_pad(rate, 10, 'R'),
        ]
        lines.append(' '.join(vals))

    return '\n'.join(lines)


def build_card(dates, records):
    beijing = timezone(timedelta(hours=8))
    now_beijing = datetime.now(beijing)
    threshold_pct = int(REJECT_RATE_THRESHOLD * 100)

    if len(dates) == 1:
        date_range = f"{dates[0][:4]}-{dates[0][4:6]}-{dates[0][6:]}"
    else:
        date_range = f"{dates[0][:4]}-{dates[0][4:6]}-{dates[0][6:]} ~ {dates[1][:4]}-{dates[1][4:6]}-{dates[1][6:]}"

    by_date = defaultdict(list)
    for r in records:
        by_date[r[0]].append(r)

    md_lines = []

    if not records:
        md_lines.append(f"⚠️ 未发现拒绝率超过 {threshold_pct}% 的记录")
    else:
        total_records = len(records)
        date_counts = {}
        for d in dates:
            date_counts[d] = len(by_date.get(d, []))
        count_parts = ' / '.join(
            f"{d[4:6]}-{d[6:]}: {date_counts[d]}条"
            for d in dates if date_counts.get(d, 0) > 0
        )
        md_lines.append(f"📡 来源：{ADV_NAME}（{ADV_ID}）")
        md_lines.append(f"⚠️ 共发现 {total_records} 条异常记录（{count_parts}）")
        md_lines.append("")

        for d in dates:
            if d not in by_date or not by_date[d]:
                continue
            day_records = by_date[d]
            date_display = f"{d[:4]}-{d[4:6]}-{d[6:]}"

            md_lines.append(f"**📅 {date_display}**")
            md_lines.append("```")
            md_lines.append(_build_table(day_records))
            md_lines.append("```")

            unique_offers = set(r[1] for r in day_records)
            offer_reject = defaultdict(int)
            for r in day_records:
                offer_reject[r[1]] += r[6]
            sorted_offers = sorted(unique_offers, key=lambda x: -offer_reject[x])
            offer_list = '|'.join(str(o) for o in sorted_offers)
            md_lines.append(f"总计{len(day_records)}条 / {len(unique_offers)}个Offer：{offer_list}")
            md_lines.append("")

    md_lines.append(f"🕐 执行时间：{now_beijing.strftime('%Y-%m-%d %H:%M:%S')} CST")

    card = {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {
                "tag": "plain_text",
                "content": f"{date_range} Reject拒绝率预警（reject_rate > {threshold_pct}%）"
            },
            "template": "red"
        },
        "elements": [
            {
                "tag": "markdown",
                "content": "\n".join(md_lines)
            }
        ]
    }
    return card


def send_error_alert(error_msg):
    try:
        payload = json.dumps({
            "msg_type": "text",
            "content": {"text": f"[Reject 推送异常]\n{error_msg}"}
        }, ensure_ascii=False).encode('utf-8')
        for url in WEBHOOK_URLS:
            req = urllib.request.Request(
                url,
                data=payload,
                headers={'Content-Type': 'application/json; charset=utf-8'}
            )
            urllib.request.urlopen(req, timeout=30)
    except Exception:
        print(f"Failed to send error alert: {traceback.format_exc()}", file=sys.stderr)


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('dates', nargs='*', help='Date(s) in YYYYMMDD format (default: yesterday+today)')
    args = parser.parse_args()

    dates = get_dates(args.dates)

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            records, _unknown_mids = fetch_reject_records(dates)
            card = build_card(dates, records)
            print(json.dumps(card, ensure_ascii=False, indent=2))
            result = send_feishu_card(card)
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
