"""
初始下載腳本（只需執行一次）
下載全市場近 10 年的股票名冊、季度 EPS、日收盤價，寫入 Supabase。
預計總耗時：6 小時。中途中斷可重新執行，會從上次進度繼續。
"""

import os
import sys
import json
import time
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv
from supabase import create_client

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

FINMIND_TOKEN = os.getenv("FINMIND_TOKEN")
SUPABASE_URL  = os.getenv("SUPABASE_URL")
SUPABASE_KEY  = os.getenv("SUPABASE_KEY")

FINMIND_API   = "https://api.finmindtrade.com/api/v4/data"
START_DATE    = (datetime.today() - timedelta(days=365 * 10)).strftime("%Y-%m-%d")
CALL_INTERVAL = 6.5
PROGRESS_FILE = os.path.join(os.path.dirname(__file__), "init_progress.json")
EPS_TYPES     = {"EPS", "BasicEPS", "EPSTaxExcluded"}

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


def finmind_get(dataset, stock_id=None, start_date=None):
    params = {"dataset": dataset, "token": FINMIND_TOKEN}
    if stock_id:  params["data_id"]    = stock_id
    if start_date: params["start_date"] = start_date
    for attempt in range(3):
        try:
            data = requests.get(FINMIND_API, params=params, timeout=30).json()
            if data.get("status") == 200:
                return data.get("data", [])
            print(f"  ⚠️  API 異常: {data.get('msg', '未知')}")
        except Exception as e:
            print(f"  ⚠️  請求失敗（第 {attempt + 1} 次）: {e}")
        time.sleep(10)
    return []


def upsert_batch(table, rows, batch_size=500):
    for i in range(0, len(rows), batch_size):
        supabase.table(table).upsert(rows[i:i + batch_size]).execute()


def load_progress():
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"eps_done": [], "prices_done": []}


def save_progress(progress):
    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump(progress, f, ensure_ascii=False)


def step1_download_stocks():
    print("=== 步驟 1：下載股票名冊 ===")
    raw = finmind_get("TaiwanStockInfo")
    if not raw:
        print("❌ 無法取得股票名冊，請確認 FINMIND_TOKEN 是否正確")
        return []

    seen, stocks = set(), []
    for item in raw:
        sid = str(item.get("stock_id", "")).strip()
        if sid.isdigit() and len(sid) == 4 and sid not in seen:
            seen.add(sid)
            stocks.append({"stock_id": sid, "name": item.get("stock_name", ""),
                           "market": item.get("market_category", "未知")})
    upsert_batch("stocks", stocks)
    print(f"✅ 完成：共 {len(stocks)} 支股票")
    return [s["stock_id"] for s in stocks]


# ── 步驟 2/3 共用：通用下載函式 ───────────────────────────

def _extract_eps(sid, raw):
    return [{"stock_id": sid, "quarter_end_date": r["date"], "eps": float(r["value"])}
            for r in raw if r.get("type") in EPS_TYPES and r.get("value") is not None]

def _extract_price(sid, raw):
    # FinMind 對「當日無成交」回傳 close = 0，那不是價格而是缺值。
    # 若照寫進資料庫，河流圖的月採樣會採到 0，畫出股價暴跌至零的假訊號
    # （實測 3629 有 31/122 個月採樣點為 0）。沒有成交就不該有記錄。
    return [{"stock_id": sid, "date": r["date"], "close_price": float(r["close"])}
            for r in raw if r.get("close") is not None and float(r["close"]) > 0]

def _download_step(label, dataset, table, progress_key, stock_ids, progress, extract_fn):
    done      = set(progress[progress_key])
    remaining = [s for s in stock_ids if s not in done]
    total     = len(stock_ids)
    print(f"\n=== {label}（已完成 {len(done)}/{total}，剩餘 {len(remaining)} 支）===")
    if not remaining:
        print("✅ 跳過（已全數完成）")
        return
    for idx, sid in enumerate(remaining, 1):
        rows = extract_fn(sid, finmind_get(dataset, sid, START_DATE))
        upsert_batch(table, rows)
        progress[progress_key].append(sid)
        save_progress(progress)
        print(f"  [{len(done) + idx}/{total}] {sid}：{len(rows)} 筆")
        time.sleep(CALL_INTERVAL)
    print("✅ 完成")


if __name__ == "__main__":
    print(f"開始時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"資料起始日：{START_DATE}\n")

    progress  = load_progress()
    stock_ids = step1_download_stocks()

    if stock_ids:
        _download_step("步驟 2：下載季度 EPS", "TaiwanStockFinancialStatements",
                       "eps_quarterly", "eps_done", stock_ids, progress, _extract_eps)
        _download_step("步驟 3：下載日收盤價", "TaiwanStockPrice",
                       "daily_prices", "prices_done", stock_ids, progress, _extract_price)
        print(f"\n全部完成！結束時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
