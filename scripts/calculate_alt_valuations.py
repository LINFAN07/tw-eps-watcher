"""
替代估值模型計算腳本（P/B、P/S、P/FCF）
讀取 Supabase 中的資產負債表、月營收、現金流量資料，
計算三種替代估值模型並更新 valuations 資料表。

執行前須先完成：
  1. 在 Supabase 執行 schema.sql 中的替代估值模型擴充語句
  2. python scripts/download_balance_sheet.py
  3. python scripts/download_monthly_revenue.py
  4. python scripts/download_cash_flows.py

邏輯與 calculate_valuation.py 相同：
  歷史倍數序列 → 20/50/80 百分位 → 便宜/合理/昂貴價
"""

import os
import sys
import traceback
from dotenv import load_dotenv
from supabase import create_client
import pandas as pd
import numpy as np

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
sys.stderr.reconfigure(encoding="utf-8", line_buffering=True)
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

# 各模型合理倍數範圍（超出者視為資料異常，不納入百分位計算）
PB_MIN,   PB_MAX   = 0.1, 50.0
PS_MIN,   PS_MAX   = 0.1, 200.0
PFCF_MIN, PFCF_MAX = 0.1, 200.0

MIN_PB_QUARTERS = 8   # P/B：至少 2 年季度資料
MIN_PS_MONTHS   = 24  # P/S：至少 2 年月營收（TTM 需 12 個月，再加 12 個月用於計算 PS 序列）
MIN_PFCF_QTRS   = 8   # P/FCF：至少 2 年季度資料


def _fetch_paged(table: str, filters: dict, columns: str) -> list:
    """分頁取得 Supabase 資料（繞過 1000 筆上限）"""
    all_rows, offset = [], 0
    order_col = columns.split(",")[0]
    while True:
        q = supabase.table(table).select(columns)
        for col, val in filters.items():
            q = q.eq(col, val)
        resp = q.order(order_col).range(offset, offset + 999).execute()
        all_rows.extend(resp.data)
        if len(resp.data) < 1000:
            break
        offset += 1000
    return all_rows


def fetch_all_stocks() -> list[dict]:
    all_rows: list[dict] = []
    offset = 0
    while True:
        resp = supabase.table("stocks").select("stock_id,listed_shares").range(offset, offset + 999).execute()
        all_rows.extend(resp.data or [])
        if len(resp.data or []) < 1000:
            break
        offset += 1000
    return all_rows


def fetch_prices(stock_id: str) -> pd.DataFrame:
    rows = _fetch_paged("daily_prices", {"stock_id": stock_id}, "date,close_price")
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["date"]        = df["date"].astype(str)
    df["close_price"] = pd.to_numeric(df["close_price"])
    return df.sort_values("date").reset_index(drop=True)


def get_status(current_price: float, cheap: float, fair: float) -> str:
    if current_price <= 0:
        return "無法計算"
    if current_price <= cheap:
        return "便宜"
    if current_price <= fair:
        return "合理"
    return "昂貴"


# ─────────────── P/B 股價淨值比 ───────────────

def calculate_pb(stock_id: str, price_df: pd.DataFrame, current_price: float) -> dict:
    rows = _fetch_paged("balance_sheet_quarterly", {"stock_id": stock_id}, "quarter_end_date,book_value_per_share")
    if not rows:
        return {}

    bvps_df = pd.DataFrame(rows)
    bvps_df["quarter_end_date"]     = bvps_df["quarter_end_date"].astype(str)
    bvps_df["book_value_per_share"] = pd.to_numeric(bvps_df["book_value_per_share"])
    bvps_df = bvps_df[bvps_df["book_value_per_share"] > 0].sort_values("quarter_end_date").reset_index(drop=True)

    if len(bvps_df) < MIN_PB_QUARTERS:
        return {}

    # 每季季末對應股價 → 計算歷史 P/B 序列
    pb_series = []
    for _, row in bvps_df.iterrows():
        bvps   = float(row["book_value_per_share"])
        q_date = row["quarter_end_date"]
        nearby = price_df[price_df["date"] <= q_date]
        if nearby.empty:
            continue
        price = float(nearby.iloc[-1]["close_price"])
        pb    = price / bvps
        if PB_MIN <= pb <= PB_MAX:
            pb_series.append(pb)

    if len(pb_series) < MIN_PB_QUARTERS:
        return {}

    pb_arr       = np.array(pb_series)
    cheap_pb     = float(np.percentile(pb_arr, 20))
    fair_pb      = float(np.percentile(pb_arr, 50))
    expensive_pb = float(np.percentile(pb_arr, 80))
    cur_bvps     = float(bvps_df.iloc[-1]["book_value_per_share"])

    cheap_price     = cur_bvps * cheap_pb
    fair_price      = cur_bvps * fair_pb
    expensive_price = cur_bvps * expensive_pb

    return {
        "pb_book_value":       round(cur_bvps, 4),
        "pb_cheap_pb":         round(cheap_pb, 4),
        "pb_fair_pb":          round(fair_pb, 4),
        "pb_expensive_pb":     round(expensive_pb, 4),
        "pb_cheap_price":      round(cheap_price, 2),
        "pb_fair_price":       round(fair_price, 2),
        "pb_expensive_price":  round(expensive_price, 2),
        "pb_status":           get_status(current_price, cheap_price, fair_price),
    }


# ─────────────── P/S 股價營收比 ───────────────

def calculate_ps(stock_id: str, price_df: pd.DataFrame, current_price: float, listed_shares: int | None) -> dict:
    if not listed_shares or listed_shares <= 0:
        return {}

    rows = _fetch_paged("monthly_revenue", {"stock_id": stock_id}, "year_month,revenue")
    if not rows:
        return {}

    rev_df = pd.DataFrame(rows)
    rev_df["year_month"] = rev_df["year_month"].astype(str)
    rev_df["revenue"]    = pd.to_numeric(rev_df["revenue"])
    rev_df = rev_df.sort_values("year_month").reset_index(drop=True)

    if len(rev_df) < MIN_PS_MONTHS:
        return {}

    # 逐月計算 TTM 營收 per share → 搭配當月股價 → 歷史 P/S 序列
    # revenue 單位：元 / listed_shares 單位：千股 → rps = 元 / (千股×1000) = 元/股
    ps_series  = []
    latest_rps = None

    for i in range(11, len(rev_df)):
        ttm_rev = float(rev_df.iloc[i - 11: i + 1]["revenue"].sum())
        rps     = ttm_rev / (listed_shares * 1000)
        if rps <= 0:
            continue

        # 找當月（YYYY-MM）的收盤價（月末最後一筆）
        month_str    = rev_df.iloc[i]["year_month"][:7]
        month_prices = price_df[price_df["date"].str.startswith(month_str)]
        if month_prices.empty:
            nearby = price_df[price_df["date"] <= rev_df.iloc[i]["year_month"]]
            if nearby.empty:
                continue
            price = float(nearby.iloc[-1]["close_price"])
        else:
            price = float(month_prices.iloc[-1]["close_price"])

        ps = price / rps
        if PS_MIN <= ps <= PS_MAX:
            ps_series.append(ps)
        latest_rps = rps

    if len(ps_series) < 12 or latest_rps is None:
        return {}

    ps_arr       = np.array(ps_series)
    cheap_ps     = float(np.percentile(ps_arr, 20))
    fair_ps      = float(np.percentile(ps_arr, 50))
    expensive_ps = float(np.percentile(ps_arr, 80))

    cheap_price     = latest_rps * cheap_ps
    fair_price      = latest_rps * fair_ps
    expensive_price = latest_rps * expensive_ps

    return {
        "ps_revenue_per_share": round(latest_rps, 4),
        "ps_cheap_ps":          round(cheap_ps, 4),
        "ps_fair_ps":           round(fair_ps, 4),
        "ps_expensive_ps":      round(expensive_ps, 4),
        "ps_cheap_price":       round(cheap_price, 2),
        "ps_fair_price":        round(fair_price, 2),
        "ps_expensive_price":   round(expensive_price, 2),
        "ps_status":            get_status(current_price, cheap_price, fair_price),
    }


# ─────────────── P/FCF 自由現金流比 ───────────────

def calculate_pfcf(stock_id: str, price_df: pd.DataFrame, current_price: float, listed_shares: int | None) -> dict:
    if not listed_shares or listed_shares <= 0:
        return {}

    rows = _fetch_paged("cash_flows_quarterly", {"stock_id": stock_id}, "quarter_end_date,operating_cf,capex")
    if not rows:
        return {}

    cf_df = pd.DataFrame(rows)
    cf_df["quarter_end_date"] = cf_df["quarter_end_date"].astype(str)
    cf_df["operating_cf"]     = pd.to_numeric(cf_df["operating_cf"], errors="coerce")
    cf_df["capex"]            = pd.to_numeric(cf_df["capex"],        errors="coerce")
    cf_df = cf_df.dropna(subset=["operating_cf", "capex"]).sort_values("quarter_end_date").reset_index(drop=True)

    if len(cf_df) < MIN_PFCF_QTRS:
        return {}

    # FCF = 營業現金流 + 資本支出（capex 為負值，加法等於扣除）
    cf_df["fcf"] = cf_df["operating_cf"] + cf_df["capex"]

    pfcf_series    = []
    latest_fcf_ps  = None

    for i in range(3, len(cf_df)):
        ttm_fcf = float(cf_df.iloc[i - 3: i + 1]["fcf"].sum())
        # 現金流量表單位為元；listed_shares 單位為千股
        # 元 ÷ (千股 × 1000) = 元/股
        fcf_ps  = ttm_fcf / (listed_shares * 1000)
        if fcf_ps <= 0:  # 負 FCF 無意義，跳過
            continue

        q_date = cf_df.iloc[i]["quarter_end_date"]
        nearby = price_df[price_df["date"] <= q_date]
        if nearby.empty:
            continue
        price = float(nearby.iloc[-1]["close_price"])

        pfcf = price / fcf_ps
        if PFCF_MIN <= pfcf <= PFCF_MAX:
            pfcf_series.append(pfcf)
        latest_fcf_ps = fcf_ps

    if len(pfcf_series) < MIN_PFCF_QTRS or latest_fcf_ps is None or latest_fcf_ps <= 0:
        return {}

    pfcf_arr        = np.array(pfcf_series)
    cheap_pfcf      = float(np.percentile(pfcf_arr, 20))
    fair_pfcf       = float(np.percentile(pfcf_arr, 50))
    expensive_pfcf  = float(np.percentile(pfcf_arr, 80))

    cheap_price     = latest_fcf_ps * cheap_pfcf
    fair_price      = latest_fcf_ps * fair_pfcf
    expensive_price = latest_fcf_ps * expensive_pfcf

    return {
        "pfcf_per_share":        round(latest_fcf_ps, 4),
        "pfcf_cheap_pfcf":       round(cheap_pfcf, 4),
        "pfcf_fair_pfcf":        round(fair_pfcf, 4),
        "pfcf_expensive_pfcf":   round(expensive_pfcf, 4),
        "pfcf_cheap_price":      round(cheap_price, 2),
        "pfcf_fair_price":       round(fair_price, 2),
        "pfcf_expensive_price":  round(expensive_price, 2),
        "pfcf_status":           get_status(current_price, cheap_price, fair_price),
    }


# ─────────────── 主流程 ───────────────

def run(stock_ids: list[str] | None = None):
    all_stocks  = fetch_all_stocks()
    shares_map  = {s["stock_id"]: s.get("listed_shares") for s in all_stocks}

    if stock_ids is None:
        stock_ids = list(shares_map.keys())

    total                              = len(stock_ids)
    success_pb = success_ps = success_pfcf = 0
    print(f"開始計算替代估值，共 {total} 支股票")

    for idx, stock_id in enumerate(stock_ids, 1):
        try:
            price_df = fetch_prices(stock_id)
            if price_df.empty:
                print(f"  [{idx}/{total}] {stock_id} → 無股價資料，跳過")
                continue

            current_price  = float(price_df.iloc[-1]["close_price"])
            listed_shares  = shares_map.get(stock_id)

            updates: dict = {}

            pb = calculate_pb(stock_id, price_df, current_price)
            if pb:
                updates.update(pb)
                success_pb += 1

            ps = calculate_ps(stock_id, price_df, current_price, listed_shares)
            if ps:
                updates.update(ps)
                success_ps += 1

            pfcf = calculate_pfcf(stock_id, price_df, current_price, listed_shares)
            if pfcf:
                updates.update(pfcf)
                success_pfcf += 1

            if updates:
                updates["stock_id"] = stock_id
                supabase.table("valuations").upsert(updates).execute()

            pb_s   = pb.get("pb_status",   "—") if pb   else "—"
            ps_s   = ps.get("ps_status",   "—") if ps   else "—"
            pfcf_s = pfcf.get("pfcf_status","—") if pfcf else "—"
            print(f"  [{idx}/{total}] {stock_id} → P/B:{pb_s}  P/S:{ps_s}  P/FCF:{pfcf_s}")

        except Exception as e:
            print(f"  [{idx}/{total}] {stock_id} → 錯誤: {e}")
            traceback.print_exc()

    print(f"\n完成：P/B {success_pb} 支 ／ P/S {success_ps} 支 ／ P/FCF {success_pfcf} 支")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="計算替代估值模型（P/B、P/S、P/FCF）")
    parser.add_argument("stock_ids", nargs="*", help="指定股票代碼（留空則全市場）")
    args = parser.parse_args()
    run(args.stock_ids or None)
