import os
import re
import json
from pathlib import Path
from datetime import datetime, timedelta
from dotenv import load_dotenv
import pymysql
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

load_dotenv()

app = FastAPI(title="数据分析助手 API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

def get_conn():
    return pymysql.connect(
        host=os.environ["DB_HOST"],
        port=int(os.environ["DB_PORT"]),
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        database=os.environ["DB_NAME"],
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )

def extract_offer_id(offer_string):
    if not offer_string:
        return ""
    match = re.match(r"^(\d+)", str(offer_string))
    return match.group(1) if match else str(offer_string)

@app.get("/api/report")
def get_report(
    date_from: str = Query(default=None, description="开始日期 YYYYMMDD"),
    date_to: str = Query(default=None, description="结束日期 YYYYMMDD"),
):
    if not date_to:
        date_to = datetime.utcnow().strftime("%Y%m%d")
    if not date_from:
        dt = datetime.strptime(date_to, "%Y%m%d") - timedelta(days=7)
        date_from = dt.strftime("%Y%m%d")

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT date, mid, src, adgroup_id, src_offer_id, pkg_name,
                          adv_country, revenue, payout, click, conversion,
                          callback_conversion, revenue_ecpc, cvr
                   FROM offerplus_detail_report
                   WHERE date >= %s AND date <= %s
                   ORDER BY date DESC""",
                (date_from, date_to),
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    result = []
    for r in rows:
        offer = r["adgroup_id"]
        result.append({
            "Date": r["date"],
            "Pub ID": r["mid"],
            "Advertiser ID": r["src"],
            "Offer": offer,
            "Adv Offer ID": r["src_offer_id"],
            "Package Name": r["pkg_name"],
            "Adv GEO": r["adv_country"],
            "Revenue": float(r["revenue"]) if r["revenue"] is not None else 0,
            "Payout": float(r["payout"]) if r["payout"] is not None else 0,
            "Click": int(r["click"]) if r["click"] is not None else 0,
            "Conversion": int(r["conversion"]) if r["conversion"] is not None else 0,
            "Callback Conversion": int(r["callback_conversion"]) if r["callback_conversion"] is not None else 0,
            "Revenue eCPC": float(r["revenue_ecpc"]) if r["revenue_ecpc"] is not None else 0,
            "CVR": float(r["cvr"]) if r["cvr"] is not None else 0,
            "OfferIdRaw": extract_offer_id(offer),
        })

    return result

@app.get("/api/dates")
def get_dates():
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT DISTINCT date FROM offerplus_detail_report ORDER BY date DESC"
            )
            rows = cur.fetchall()
    finally:
        conn.close()
    return [r["date"] for r in rows]

@app.get("/api/latest")
def get_latest():
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT MAX(date) as latest_date, MAX(created_at) as latest_created FROM offerplus_detail_report"
            )
            row = cur.fetchone()
    finally:
        conn.close()
    return {
        "latest_date": row["latest_date"],
        "latest_created": str(row["latest_created"]) if row["latest_created"] else None,
    }

@app.get("/api/pubnames")
def get_pub_names():
    mapping_str = os.environ.get("PUB_MAPPING", "")
    if mapping_str:
        try:
            return json.loads(mapping_str)
        except (json.JSONDecodeError, TypeError):
            pass
    mapping_path = Path(__file__).resolve().parent.parent / "pub_mapping.json"
    if mapping_path.exists():
        with open(mapping_path, encoding="utf-8") as f:
            return json.load(f)
    return {}

@app.get("/api/advnames")
def get_adv_names():
    mapping_str = os.environ.get("ADV_MAPPING", "")
    if mapping_str:
        try:
            return json.loads(mapping_str)
        except (json.JSONDecodeError, TypeError):
            pass
    mapping_path = Path(__file__).resolve().parent.parent / "adv_mapping.json"
    if mapping_path.exists():
        with open(mapping_path, encoding="utf-8") as f:
            return json.load(f)
    return {}

if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True))
