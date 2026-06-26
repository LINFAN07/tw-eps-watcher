"""
估值計算腳本
讀取 Supabase 的 EPS 與股價，計算 P/E 河流圖估值，寫入 valuations 資料表。

P/E 河流圖邏輯：
  TTM EPS = 最近 4 季 EPS 合計
  歷史 P/E 序列 = 每個交易日的 (收盤價 ÷ 當時 TTM EPS)
  便宜價 = TTM EPS × 歷史 P/E 第 20 百分位數
  合理價 = TTM EPS × 歷史 P/E 第 50 百分位數
  昂貴價 = TTM EPS × 歷史 P/E 第 80 百分位數
"""

import os
import sys
import traceback
from dotenv import load_dotenv
from supabase import create_client
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
sys.stderr.reconfigure(encoding="utf-8", line_buffering=True)
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

PE_CHEAP, PE_FAIR, PE_EXPENSIVE = 20, 50, 80
PE_MIN,   PE_MAX                = 3, 200


def _fetch_paged(table, filters: dict, columns: str) -> list:
    """分頁取得 Supabase 資料（繞過 1000 筆上限），以第一個欄位排序"""
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


def fetch_all_stock_ids() -> list[str]:
    rows = _fetch_paged("stocks", {}, "stock_id")
    return [r["stock_id"] for r in rows]


def fetch_eps(stock_id: str) -> pd.DataFrame:
    resp = (supabase.table("eps_quarterly").select("quarter_end_date, eps")
            .eq("stock_id", stock_id).order("quarter_end_date").execute())
    if not resp.data:
        return pd.DataFrame()
    df = pd.DataFrame(resp.data)
    df["quarter_end_date"] = pd.to_datetime(df["quarter_end_date"])
    return df


def fetch_prices(stock_id: str) -> pd.DataFrame:
    rows = _fetch_paged("daily_prices", {"stock_id": stock_id}, "date,close_price")
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values("date")


def build_pe_series(eps_df: pd.DataFrame, price_df: pd.DataFrame) -> pd.DataFrame:
    """用 merge_asof 向量化計算每個交易日的 P/E，取代逐行迴圈"""
    eps = eps_df.copy()
    eps["ttm_eps"] = eps["eps"].rolling(4, min_periods=4).sum()
    eps = eps.dropna(subset=["ttm_eps"])

    merged = pd.merge_asof(
        price_df.sort_values("date"),
        eps[["quarter_end_date", "ttm_eps"]].rename(columns={"quarter_end_date": "date"}),
        on="date", direction="backward",
    )
    merged = merged.dropna(subset=["ttm_eps"])
    merged = merged[merged["ttm_eps"] > 0].copy()
    merged["pe"] = merged["close_price"] / merged["ttm_eps"]
    return merged[(merged["pe"] >= PE_MIN) & (merged["pe"] <= PE_MAX)]


def calculate_valuation(stock_id: str) -> dict | None:
    eps_df   = fetch_eps(stock_id)
    price_df = fetch_prices(stock_id)
    if eps_df.empty or price_df.empty:
        return None

    series = build_pe_series(eps_df, price_df)
    if len(series) < 40:
        return None

    cheap_pe, fair_pe, expensive_pe = (
        series["pe"].quantile(p / 100) for p in (PE_CHEAP, PE_FAIR, PE_EXPENSIVE)
    )
    ttm_eps       = float(eps_df.tail(4)["eps"].sum())
    current_price = float(price_df.iloc[-1]["close_price"])

    if ttm_eps <= 0 or current_price <= 0:
        status = "無法計算"
    elif current_price <= ttm_eps * cheap_pe:
        status = "便宜"
    elif current_price <= ttm_eps * fair_pe:
        status = "合理"
    else:
        status = "昂貴"

    def r(v): return round(float(v), 2)
    return {
        "stock_id":        stock_id,
        "ttm_eps":         r(ttm_eps),
        "cheap_pe":        r(cheap_pe),
        "fair_pe":         r(fair_pe),
        "expensive_pe":    r(expensive_pe),
        "cheap_price":     r(ttm_eps * cheap_pe),
        "fair_price":      r(ttm_eps * fair_pe),
        "expensive_price": r(ttm_eps * expensive_pe),
        "current_price":   r(current_price),
        "status":          status,
    }


def run(stock_ids: list[str] | None = None):
    if stock_ids is None:
        stock_ids = fetch_all_stock_ids()

    total, success, skipped = len(stock_ids), 0, 0
    print(f"開始計算估值，共 {total} 支股票")

    for idx, stock_id in enumerate(stock_ids, 1):
        try:
            result = calculate_valuation(stock_id)
        except Exception as e:
            print(f"  [{idx}/{total}] {stock_id} -> 計算錯誤: {e}")
            traceback.print_exc()
            skipped += 1
            continue

        if result:
            try:
                supabase.table("valuations").upsert(result).execute()
                print(f"  [{idx}/{total}] {stock_id} -> {result['status']} "
                      f"便宜:{result['cheap_price']} 合理:{result['fair_price']} "
                      f"昂貴:{result['expensive_price']} 現價:{result['current_price']}")
                success += 1
            except Exception as e:
                print(f"  [{idx}/{total}] {stock_id} -> 寫入錯誤: {e}")
                skipped += 1
        else:
            print(f"  [{idx}/{total}] {stock_id} -> 跳過")
            skipped += 1

    print(f"\n完成：成功 {success} 支，跳過 {skipped} 支")


if __name__ == "__main__":
    run()
