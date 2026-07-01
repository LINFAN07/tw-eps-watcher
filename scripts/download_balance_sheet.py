"""
資產負債表下載腳本（P/B 估值原始資料）
從 FinMind TaiwanStockBalanceSheet 下載每股淨值（BookValuePerShare），
寫入 Supabase balance_sheet_quarterly 表。

執行前請先在 Supabase SQL Editor 執行 schema.sql 中的替代估值模型擴充語句。

用法：
  python scripts/download_balance_sheet.py            # 全量下載
  python scripts/download_balance_sheet.py --skip-file done.txt   # 斷點續傳
  python scripts/download_balance_sheet.py --discover # 印出欄位類型後退出（驗證用）
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
CALL_INTERVAL = 6.5  # FinMind 免費版速率限制（秒）

# FinMind 沒有直接的 BookValuePerShare 欄位
# 用 EquityAttributableToOwnersOfParent（母公司股東權益, 元）
# 和 CapitalStock（股本, 元，面額 NT$10）計算：
# BVPS = 10 × 股東權益 / 股本

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


def finmind_get(dataset: str, stock_id: str, start_date: str) -> list:
    params = {"dataset": dataset, "data_id": stock_id, "start_date": start_date, "token": FINMIND_TOKEN}
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


def download_stock_bvps(stock_id: str) -> int:
    """下載單支股票的每股淨值，回傳寫入筆數

    FinMind 無直接 BookValuePerShare 欄位，改以季度資產負債表計算：
      BVPS = 10 × EquityAttributableToOwnersOfParent / CapitalStock
    假設面額 NT$10（台股主流），極少數面額不同的公司誤差可接受。
    """
    raw = finmind_get("TaiwanStockBalanceSheet", stock_id, START_DATE)
    if not raw:
        return 0

    # 依日期收集需要的兩個欄位值
    equity_by_date: dict[str, float] = {}
    capital_by_date: dict[str, float] = {}

    for r in raw:
        date_str = r.get("date", "").strip()
        type_str = r.get("type", "")
        value    = r.get("value")
        if not date_str or value is None:
            continue
        try:
            val = float(value)
        except (TypeError, ValueError):
            continue
        if type_str == "EquityAttributableToOwnersOfParent":
            equity_by_date[date_str] = val
        elif type_str == "CapitalStock":
            capital_by_date[date_str] = val

    rows = []
    for date_str, equity in equity_by_date.items():
        capital = capital_by_date.get(date_str)
        if not capital or capital <= 0:
            continue
        bvps = 10.0 * equity / capital
        if bvps <= 0:
            continue
        rows.append({
            "stock_id":             stock_id,
            "quarter_end_date":     date_str,
            "book_value_per_share": round(bvps, 4),
        })

    if not rows:
        return 0

    # 從最新一期的 CapitalStock 推算流通股數（千股）並更新 stocks.listed_shares
    # listed_shares (千股) = CapitalStock (元, 面額10元) / 10 / 1000
    if capital_by_date:
        latest_capital = capital_by_date[max(capital_by_date.keys())]
        listed_shares = int(latest_capital / 10 / 1000)
        if listed_shares > 0:
            for attempt in range(3):
                try:
                    supabase.table("stocks").update({"listed_shares": listed_shares}).eq("stock_id", stock_id).execute()
                    break
                except Exception as e:
                    if attempt < 2:
                        time.sleep(5)
                    else:
                        print(f"  ⚠️  listed_shares 更新失敗: {e}")

    # 加入重試，避免 Supabase 瞬斷導致整支腳本崩潰
    for attempt in range(3):
        try:
            supabase.table("balance_sheet_quarterly").upsert(
                rows, on_conflict="stock_id,quarter_end_date"
            ).execute()
            return len(rows)
        except Exception as e:
            if attempt < 2:
                print(f"  ⚠️  Supabase 寫入失敗（第 {attempt + 1} 次），10 秒後重試: {e}")
                time.sleep(10)
            else:
                print(f"  ❌  Supabase 寫入失敗（已重試 3 次），跳過: {e}")
                return 0


def main():
    import argparse
    parser = argparse.ArgumentParser(description="下載台股每股淨值（P/B 估值原始資料）")
    parser.add_argument("--skip-file", help="已處理股票代碼清單（每行一個），跳過這些股票")
    parser.add_argument("--discover", action="store_true",
                        help="用 2330 試跑，印出所有可用 type 欄位後退出（用來驗證欄位名稱）")
    args = parser.parse_args()

    if args.discover:
        raw = finmind_get("TaiwanStockBalanceSheet", "2330", "2024-01-01")
        types = sorted({r["type"] for r in raw if "type" in r})
        print(f"TaiwanStockBalanceSheet 可用的 type 值（共 {len(types)} 種）：")
        for t in types:
            sample = next((r["value"] for r in raw if r.get("type") == t), "—")
            print(f"  {t}: {sample}")
        return

    skip: set[str] = set()
    if args.skip_file:
        with open(args.skip_file, encoding="utf-8") as f:
            skip = {line.strip() for line in f if line.strip()}
        print(f"跳過清單：{len(skip)} 支已處理股票")

    all_ids    = fetch_all_stock_ids()
    stock_ids  = [s for s in all_ids if s not in skip]
    total      = len(stock_ids)
    print(f"開始下載資產負債表（每股淨值），共 {total} 支股票，起始日 {START_DATE}")

    written_total = 0
    for i, sid in enumerate(stock_ids, 1):
        written = download_stock_bvps(sid)
        label   = f"寫入 {written} 筆" if written > 0 else "無資料"
        print(f"[{i}/{total}] {sid}: {label}")
        written_total += written
        time.sleep(CALL_INTERVAL)

    print(f"\n✅ 完成，共寫入 {written_total} 筆每股淨值資料")


if __name__ == "__main__":
    main()
