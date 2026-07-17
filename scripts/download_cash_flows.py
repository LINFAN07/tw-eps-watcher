"""
現金流量表下載腳本（P/FCF 估值原始資料）
從 FinMind TaiwanStockCashFlowsStatement 下載季度營業現金流與資本支出，
寫入 Supabase cash_flows_quarterly 表。

operating_cf、capex 單位：千元
FCF = operating_cf + capex（capex 通常為負值）

用法：
  python scripts/download_cash_flows.py            # 全量下載
  python scripts/download_cash_flows.py --skip-file done.txt
  python scripts/download_cash_flows.py --discover # 印出可用欄位類型
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

# 依序嘗試；FinMind 欄位名稱因公司會計準則（IFRS/GAAP）略有差異
# 已用 --discover 確認主流欄位名稱，其餘作為備用
OPERATING_CF_TYPES = (
    "CashFlowsFromOperatingActivities",      # 主要（已確認）
    "NetCashInflowFromOperatingActivities",  # 備用（部分公司同值）
    "OperatingActivities",
    "NetCashFlowsFromOperatingActivities",
    "OperatingActivitiesNetCashflow",
)
CAPEX_TYPES = (
    "PropertyAndPlantAndEquipment",          # 主要（FinMind 現金流表中為負值）
    "PurchaseOfPropertyPlantAndEquipment",
    "AcquisitionOfPropertyPlantAndEquipment",
    "CapitalExpenditure",
    "CapitalExpenditures",
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


def download_stock_cash_flows(stock_id: str) -> int:
    """下載單支股票的現金流量表，回傳寫入筆數"""
    raw = finmind_get("TaiwanStockCashFlowsStatement", stock_id, START_DATE)
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
        # 依優先順序找到第一個存在的欄位
        operating_cf = next((types[t] for t in OPERATING_CF_TYPES if t in types), None)
        capex        = next((types[t] for t in CAPEX_TYPES if t in types), None)

        # 兩個值都沒有就跳過
        if operating_cf is None and capex is None:
            continue

        rows.append({
            "stock_id":         stock_id,
            "quarter_end_date": date_str,
            "operating_cf":     operating_cf,
            "capex":            capex,
        })

    if not rows:
        return 0

    supabase.table("cash_flows_quarterly").upsert(
        rows, on_conflict="stock_id,quarter_end_date"
    ).execute()
    return len(rows)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="下載台股現金流量表（P/FCF 估值原始資料）")
    parser.add_argument("--skip-file", help="已處理股票代碼清單，跳過這些股票")
    parser.add_argument("--discover",  action="store_true",
                        help="用 2330 試跑，印出所有可用 type 值後退出")
    args = parser.parse_args()

    if args.discover:
        raw   = finmind_get("TaiwanStockCashFlowsStatement", "2330", "2024-01-01")
        types = sorted({r["type"] for r in raw if "type" in r})
        print(f"TaiwanStockCashFlowsStatement 可用的 type 值（共 {len(types)} 種）：")
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
    print(f"開始下載現金流量表：{total} 支股票，起始日 {START_DATE}")

    tracker = fm.FailureTracker("現金流量表下載")
    written_total = 0
    for i, sid in enumerate(stock_ids, 1):
        try:
            written = download_stock_cash_flows(sid)
        except fm.FinMindError as e:
            tracker.record(sid, e)
            written = 0
        label   = f"寫入 {written} 筆" if written > 0 else "無資料"
        print(f"[{i}/{total}] {sid}: {label}")
        written_total += written
        time.sleep(CALL_INTERVAL)

    print(f"\n✅ 完成，共寫入 {written_total} 筆現金流量資料")
    tracker.finish()   # 有任何抓取失敗就以 exit 1 結束，觸發通知


if __name__ == "__main__":
    main()
