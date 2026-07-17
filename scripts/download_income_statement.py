"""
損益表下載腳本（業外收支偵測原始資料）
從 FinMind TaiwanStockFinancialStatements 下載季度營業利益與稅後淨利，
寫入 Supabase income_statement_quarterly 表。

operating_income、net_income 單位：元（NTD）
注意：此資料集與 CashFlowsStatement 不同，單位為「元」而非「千元」

用法：
  python scripts/download_income_statement.py            # 全量下載
  python scripts/download_income_statement.py --skip-file done.txt
  python scripts/download_income_statement.py --discover # 印出可用欄位類型
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
CALL_INTERVAL = 6.5

# 依序嘗試；IFRS/台灣會計準則欄位名稱略有差異
# 以 --discover 模式確認實際欄位名稱後可調整優先順序
OPERATING_INCOME_TYPES = (
    "OperatingIncome",                         # 最常見
    "IncomeLossFromContinuingOperations",
    "OperatingProfit",
    "TotalOperatingIncome",
    "EBITDAOperatingIncome",
)
NET_INCOME_TYPES = (
    "IncomeAfterTaxes",                        # 主要（已 --discover 確認）
    "IncomeFromContinuingOperations",          # 備用（部分公司同值）
    "NetIncome",
    "ProfitLoss",
    "ProfitLossAttributableToOwnersOfParent",
    "ConsolidatedNetIncome",
)

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


def finmind_get(dataset: str, stock_id: str | None, start_date: str | None) -> list:
    """委派給共用客戶端：抓取失敗會拋 FinMindError，不以空清單掩蓋故障"""
    return fm.fetch(dataset, stock_id, start_date, FINMIND_TOKEN)


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


def download_stock_income(stock_id: str) -> int:
    """下載單支股票的損益表，回傳寫入筆數"""
    raw = finmind_get("TaiwanStockFinancialStatements", stock_id, START_DATE)
    if not raw:
        return 0

    # 依日期分組，每個季度有多個 type/value 資料列
    by_date: dict[str, dict[str, float]] = {}
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
        if date_str not in by_date:
            by_date[date_str] = {}
        by_date[date_str][type_str] = val

    rows = []
    for date_str, types in by_date.items():
        operating_income = next((types[t] for t in OPERATING_INCOME_TYPES if t in types), None)
        net_income       = next((types[t] for t in NET_INCOME_TYPES if t in types), None)

        if operating_income is None and net_income is None:
            continue

        rows.append({
            "stock_id":         stock_id,
            "quarter_end_date": date_str,
            "operating_income": operating_income,
            "net_income":       net_income,
        })

    if not rows:
        return 0

    supabase.table("income_statement_quarterly").upsert(
        rows, on_conflict="stock_id,quarter_end_date"
    ).execute()
    return len(rows)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="下載台股損益表（業外收支偵測原始資料）")
    parser.add_argument("--skip-file", help="已處理股票代碼清單，跳過這些股票")
    parser.add_argument("--discover",  action="store_true",
                        help="用 2330 試跑，印出所有可用 type 值後退出")
    args = parser.parse_args()

    if args.discover:
        raw   = finmind_get("TaiwanStockFinancialStatements", "2330", "2024-01-01")
        types = sorted({r["type"] for r in raw if "type" in r})
        print(f"TaiwanStockFinancialStatements 可用的 type 值（共 {len(types)} 種）：")
        for t in types:
            sample = next((r["value"] for r in raw if r.get("type") == t), "—")
            print(f"  {t}: {sample}")
        return

    skip: set[str] = set()
    if args.skip_file:
        with open(args.skip_file, encoding="utf-8") as f:
            skip = {line.strip() for line in f if line.strip()}
        print(f"跳過清單：{len(skip)} 支已處理股票")

    all_ids   = fetch_all_stock_ids()
    stock_ids = [s for s in all_ids if s not in skip]
    total     = len(stock_ids)
    print(f"開始下載損益表：{total} 支股票，起始日 {START_DATE}")

    tracker = fm.FailureTracker("損益表下載")
    written_total = 0
    for i, sid in enumerate(stock_ids, 1):
        # 單支失敗不中斷整批，但結尾 tracker.finish() 會讓工作以失敗結束
        try:
            written = download_stock_income(sid)
        except fm.FinMindError as e:
            tracker.record(sid, e)
            written = 0
        label   = f"寫入 {written} 筆" if written > 0 else "無資料"
        print(f"[{i}/{total}] {sid}: {label}")
        written_total += written
        time.sleep(CALL_INTERVAL)

    print(f"\n✅ 完成，共寫入 {written_total} 筆損益表資料")
    tracker.finish()   # 有任何抓取失敗就以 exit 1 結束，觸發通知


if __name__ == "__main__":
    main()
