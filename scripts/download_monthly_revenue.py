"""
月營收下載腳本（P/S 估值原始資料）
從 FinMind TaiwanStockMonthRevenue 下載月營收，寫入 Supabase monthly_revenue 表。
同時從 TaiwanStockInfo 取得流通股數，更新 stocks.listed_shares 欄位。

revenue 單位：元（元 ÷ (千股×1000) = 元/股，與 EPS 單位一致）
listed_shares 單位：千股

用法：
  python scripts/download_monthly_revenue.py            # 全量下載
  python scripts/download_monthly_revenue.py --skip-file done.txt
  python scripts/download_monthly_revenue.py --shares-only  # 只更新流通股數
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
CALL_INTERVAL = 6.5

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


def finmind_get(dataset: str, stock_id: str | None, start_date: str | None) -> list:
    params: dict = {"dataset": dataset, "token": FINMIND_TOKEN}
    if stock_id:
        params["data_id"]    = stock_id
    if start_date:
        params["start_date"] = start_date
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


def _fetch_shares_from_url(url: str, verify_ssl: bool = True) -> dict[str, int]:
    """從 TWSE/TPEX OpenAPI 取得股票流通股數（股），回傳 {stock_id: 千股}"""
    try:
        resp = requests.get(url, timeout=20, verify=verify_ssl)
        data = resp.json()
    except Exception as e:
        print(f"  ⚠️  {url} 請求失敗: {e}")
        return {}

    result: dict[str, int] = {}
    for r in data:
        # TWSE: 公司代號 / TPEX: CompanyCode 或 SecuritiesCompanyCode
        stock_id = (r.get("公司代號") or r.get("SecuritiesCompanyCode") or r.get("CompanyCode", "")).strip()
        # 已發行普通股數（單位：股）
        shares_raw = r.get("已發行普通股數或TDR原股發行股數") or r.get("IssuedShares") or r.get("CommonSharesIssuedAndOutstanding")
        if not stock_id or shares_raw is None:
            continue
        try:
            shares_股 = int(float(str(shares_raw).replace(",", "")))
            shares_千股 = shares_股 // 1000
        except (TypeError, ValueError):
            continue
        if shares_千股 > 0:
            result[stock_id] = shares_千股
    return result


def update_listed_shares() -> int:
    """從 TWSE/TPEX OpenAPI 取得全市場流通股數，批次更新 stocks.listed_shares"""
    print("從 TWSE/TPEX 取得流通股數...")

    # TWSE 上市（SSL 正常）
    twse_map = _fetch_shares_from_url(
        "https://openapi.twse.com.tw/v1/opendata/t187ap03_L", verify_ssl=True
    )
    # TPEX 上櫃（SSL 憑證有問題，略過驗證）
    tpex_map = _fetch_shares_from_url(
        "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_stkinfo", verify_ssl=False
    )
    shares_map = {**twse_map, **tpex_map}
    print(f"  取得 TWSE {len(twse_map)} 支 + TPEX {len(tpex_map)} 支")

    if not shares_map:
        print("  ⚠️  無任何流通股數資料")
        return 0

    updated = 0
    for stock_id, shares_千股 in shares_map.items():
        try:
            supabase.table("stocks").update({"listed_shares": shares_千股}).eq("stock_id", stock_id).execute()
            updated += 1
        except Exception as e:
            print(f"  ⚠️  {stock_id} 更新失敗: {e}")

    print(f"  ✅ 已更新 {updated} 支股票的流通股數")
    return updated


def download_stock_revenue(stock_id: str) -> int:
    """下載單支股票的月營收，回傳寫入筆數"""
    raw = finmind_get("TaiwanStockMonthRevenue", stock_id, START_DATE)
    if not raw:
        return 0

    rows = []
    for r in raw:
        # 用 revenue_year + revenue_month 組成正確的營收歸屬月份
        rev_year  = r.get("revenue_year")
        rev_month = r.get("revenue_month")
        revenue   = r.get("revenue")
        if not rev_year or not rev_month or revenue is None:
            continue
        try:
            year_month = f"{int(rev_year):04d}-{int(rev_month):02d}-01"
            rev_val    = int(float(str(revenue).replace(",", "")))
        except (TypeError, ValueError):
            continue
        if rev_val < 0:
            continue
        rows.append({
            "stock_id":   stock_id,
            "year_month": year_month,
            "revenue":    rev_val,
        })

    if not rows:
        return 0

    # 同一股票同一月份可能重複，以 upsert 去重
    supabase.table("monthly_revenue").upsert(
        rows, on_conflict="stock_id,year_month"
    ).execute()
    return len(rows)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="下載台股月營收（P/S 估值原始資料）")
    parser.add_argument("--skip-file",   help="已處理股票代碼清單，跳過這些股票")
    parser.add_argument("--shares-only", action="store_true", help="只更新流通股數，跳過月營收下載")
    args = parser.parse_args()

    # 第一步：更新所有股票的流通股數（整批一次拉取，速度快）
    update_listed_shares()
    time.sleep(CALL_INTERVAL)

    if args.shares_only:
        return

    skip: set[str] = set()
    if args.skip_file:
        with open(args.skip_file, encoding="utf-8") as f:
            skip = {line.strip() for line in f if line.strip()}
        print(f"跳過清單：{len(skip)} 支已處理股票")

    all_ids   = fetch_all_stock_ids()
    stock_ids = [s for s in all_ids if s not in skip]
    total     = len(stock_ids)
    print(f"開始下載月營收資料：{total} 支股票，起始日 {START_DATE}")

    written_total = 0
    for i, sid in enumerate(stock_ids, 1):
        written = download_stock_revenue(sid)
        label   = f"寫入 {written} 筆" if written > 0 else "無資料"
        print(f"[{i}/{total}] {sid}: {label}")
        written_total += written
        time.sleep(CALL_INTERVAL)

    print(f"\n✅ 完成，共寫入 {written_total} 筆月營收資料")


if __name__ == "__main__":
    main()
