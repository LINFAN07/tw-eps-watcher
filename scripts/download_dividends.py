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
import finmind_client as fm

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

FINMIND_TOKEN = os.getenv("FINMIND_TOKEN")
SUPABASE_URL  = os.getenv("SUPABASE_URL")
SUPABASE_KEY  = os.getenv("SUPABASE_KEY")
FINMIND_API   = "https://api.finmindtrade.com/api/v4/data"
START_DATE    = (datetime.today() - timedelta(days=365 * 10)).strftime("%Y-%m-%d")
CALL_INTERVAL = 6.5  # FinMind 免費版速率限制

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


def finmind_get(dataset: str, stock_id: str | None, start_date: str | None) -> list:
    """委派給共用客戶端：抓取失敗會拋 FinMindError，不以空清單掩蓋故障"""
    return fm.fetch(dataset, stock_id, start_date, FINMIND_TOKEN)


def fetch_all_stock_ids() -> list[str]:
    # Supabase 單次最多 1000 筆，需分頁取完整名冊
    all_ids: list[str] = []
    offset = 0
    while True:
        resp = supabase.table("stocks").select("stock_id").range(offset, offset + 999).execute()
        batch = [r["stock_id"] for r in (resp.data or [])]
        all_ids.extend(batch)
        if len(batch) < 1000:
            break
        offset += 1000
    return all_ids


def _amount(row: dict, *fields: str) -> float:
    """把多個金額欄位加總；缺值或非數字視為 0"""
    total = 0.0
    for f in fields:
        try:
            total += float(row.get(f, 0) or 0)
        except (TypeError, ValueError):
            pass
    return total


def download_stock_dividends(stock_id: str) -> int:
    """
    下載單支股票的除權息，回傳寫入筆數。

    現金股利與股票股利【各有自己的除權息交易日】，且未必同一天
    （只除息、只除權、或分開進行都存在），因此分別依各自的日期記錄。

    股票股利同樣會讓股價機械性下跌，必須納入還原：
    參考價 =（前收盤 − 現金股利）÷（1 + 配股率），配股率 = 股票股利 ÷ 10。
    實測 1436：(116 − 9.7965) ÷ (1 + 3.0143/10) = 81.60，與當日走勢相符。
    """
    raw = finmind_get("TaiwanStockDividend", stock_id, START_DATE)
    if not raw:
        return 0

    # 同一天可能有多筆（盈餘分配 + 法定盈餘公積分開列），故依日期累加
    by_date: dict[str, dict[str, float]] = {}

    def add(date_str: str, key: str, value: float):
        if not date_str or value <= 0:
            return
        by_date.setdefault(date_str, {"cash": 0.0, "stock": 0.0})[key] += value

    for r in raw:
        add((r.get("CashExDividendTradingDate") or "").strip(), "cash",
            _amount(r, "CashEarningsDistribution", "CashStatutorySurplus"))
        add((r.get("StockExDividendTradingDate") or "").strip(), "stock",
            _amount(r, "StockEarningsDistribution", "StockStatutorySurplus"))

    if not by_date:
        return 0

    rows = [
        {"stock_id": stock_id, "ex_date": d,
         "cash_dividend": round(v["cash"], 4),
         "stock_dividend": round(v["stock"], 4)}
        for d, v in by_date.items()
    ]
    supabase.table("dividends").upsert(rows, on_conflict="stock_id,ex_date").execute()
    return len(rows)


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-file", help="包含已處理股票代碼的文字檔（每行一個），跳過這些股票")
    args = parser.parse_args()

    skip: set[str] = set()
    if args.skip_file:
        with open(args.skip_file, encoding="utf-8") as f:
            skip = {line.strip() for line in f if line.strip()}
        print(f"跳過清單：{len(skip)} 支已處理股票")

    all_ids = fetch_all_stock_ids()
    stock_ids = [s for s in all_ids if s not in skip]
    total = len(stock_ids)
    print(f"開始下載股利資料：{total} 支股票（全市場 {len(all_ids)} 支），起始日 {START_DATE}")

    tracker = fm.FailureTracker("股利下載")
    written_total = 0
    for i, sid in enumerate(stock_ids, 1):
        try:
            written = download_stock_dividends(sid)
        except fm.FinMindError as e:
            tracker.record(sid, e)
            written = 0
        if written > 0:
            print(f"[{i}/{total}] {sid}: 寫入 {written} 筆")
        else:
            print(f"[{i}/{total}] {sid}: 無股利資料")
        written_total += written
        time.sleep(CALL_INTERVAL)

    print(f"\n✅ 完成，共寫入 {written_total} 筆股利資料")
    tracker.finish()   # 有任何抓取失敗就以 exit 1 結束，觸發通知


if __name__ == "__main__":
    main()
