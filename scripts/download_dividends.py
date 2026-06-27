"""
股利資料下載腳本（需執行一次以初始化，之後每年更新一次即可）
從 FinMind 下載全市場現金股利資料，寫入 Supabase dividends 表。

執行前請先在 Supabase 執行以下 SQL 建表：
  CREATE TABLE dividends (
    stock_id TEXT NOT NULL REFERENCES stocks(stock_id) ON DELETE CASCADE,
    ex_date  DATE NOT NULL,
    cash_dividend NUMERIC(10, 4) NOT NULL DEFAULT 0,
    PRIMARY KEY (stock_id, ex_date)
  );
  CREATE INDEX idx_dividends_stock ON dividends(stock_id);
"""

import os
import sys
import time
from datetime import datetime, timedelta
from dotenv import load_dotenv
import requests
from supabase import create_client

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

FINMIND_TOKEN = os.getenv("FINMIND_TOKEN")
SUPABASE_URL  = os.getenv("SUPABASE_URL")
SUPABASE_KEY  = os.getenv("SUPABASE_KEY")
FINMIND_API   = "https://api.finmindtrade.com/api/v4/data"
START_DATE    = (datetime.today() - timedelta(days=365 * 10)).strftime("%Y-%m-%d")
CALL_INTERVAL = 6.5  # FinMind 免費版速率限制

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


def finmind_get(dataset: str, stock_id: str, start_date: str) -> list:
    params = {
        "dataset":    dataset,
        "data_id":    stock_id,
        "start_date": start_date,
        "token":      FINMIND_TOKEN,
    }
    for attempt in range(3):
        try:
            resp = requests.get(FINMIND_API, params=params, timeout=30).json()
            if resp.get("status") == 200:
                return resp.get("data", [])
            print(f"  ⚠️  API 異常: {resp.get('msg', '未知')}")
        except Exception as e:
            print(f"  ⚠️  請求失敗（第 {attempt + 1} 次）: {e}")
        time.sleep(10)
    return []


def fetch_all_stock_ids() -> list[str]:
    resp = supabase.table("stocks").select("stock_id").execute()
    return [r["stock_id"] for r in (resp.data or [])]


def download_stock_dividends(stock_id: str) -> int:
    """下載單支股票的股利，回傳寫入筆數"""
    raw = finmind_get("TaiwanStockDividend", stock_id, START_DATE)
    if not raw:
        return 0

    rows = []
    for r in raw:
        # FinMind TaiwanStockDividend 欄位：date（除息基準日）、CashDividend
        ex_date      = r.get("date", "")
        cash_div_raw = r.get("CashDividend", 0)
        try:
            cash_div = float(cash_div_raw)
        except (TypeError, ValueError):
            cash_div = 0.0
        if ex_date and cash_div > 0:
            rows.append({
                "stock_id":     stock_id,
                "ex_date":      ex_date,
                "cash_dividend": round(cash_div, 4),
            })

    if not rows:
        return 0

    # upsert 避免重複
    supabase.table("dividends").upsert(rows, on_conflict="stock_id,ex_date").execute()
    return len(rows)


def main():
    stock_ids = fetch_all_stock_ids()
    total = len(stock_ids)
    print(f"開始下載股利資料：{total} 支股票，起始日 {START_DATE}")

    written_total = 0
    for i, sid in enumerate(stock_ids, 1):
        written = download_stock_dividends(sid)
        if written > 0:
            print(f"[{i}/{total}] {sid}: 寫入 {written} 筆")
        else:
            print(f"[{i}/{total}] {sid}: 無股利資料")
        written_total += written
        time.sleep(CALL_INTERVAL)

    print(f"\n✅ 完成，共寫入 {written_total} 筆股利資料")


if __name__ == "__main__":
    main()
