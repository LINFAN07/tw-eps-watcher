"""
殖利率估值帶回填腳本
只針對有配息紀錄的股票計算，速度遠快於 calculate_alt_valuations.py 全量重算。

執行前須先在 Supabase 執行 schema.sql 最底部的 yield_* 欄位 ALTER TABLE。
"""

import os
import sys
import traceback
import pandas as pd
import numpy as np
from dotenv import load_dotenv
from supabase import create_client

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
sys.stderr.reconfigure(encoding="utf-8", line_buffering=True)
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

MIN_YIELD_MONTHS = 36  # 至少 3 年月資料（需涵蓋多個配息週期）


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


def get_stock_ids_with_dividends() -> list[str]:
    """取出有配息紀錄的不重複股票代碼"""
    all_ids, offset = set(), 0
    while True:
        resp = supabase.table("dividends").select("stock_id").range(offset, offset + 999).execute()
        for row in resp.data:
            all_ids.add(row["stock_id"])
        if len(resp.data) < 1000:
            break
        offset += 1000
    return sorted(all_ids)


def get_current_price(stock_id: str) -> float | None:
    """從 valuations 取現價（避免重新查 daily_prices）"""
    resp = supabase.table("valuations").select("current_price").eq("stock_id", stock_id).limit(1).execute()
    if resp.data and resp.data[0].get("current_price"):
        return float(resp.data[0]["current_price"])
    return None


def get_status(current_price: float, cheap: float, fair: float) -> str:
    if current_price <= cheap:
        return "便宜"
    if current_price <= fair:
        return "合理"
    return "昂貴"


def calculate_yield(stock_id: str) -> dict:
    # 取配息資料
    div_rows = _fetch_paged("dividends", {"stock_id": stock_id}, "ex_date,cash_dividend")
    if not div_rows:
        return {}

    div_df = pd.DataFrame(div_rows)
    div_df["ex_date"]       = pd.to_datetime(div_df["ex_date"])
    div_df["cash_dividend"] = pd.to_numeric(div_df["cash_dividend"], errors="coerce")
    div_df = div_df[div_df["cash_dividend"] > 0].sort_values("ex_date").reset_index(drop=True)
    if div_df.empty:
        return {}

    # 取歷史收盤價
    price_rows = _fetch_paged("daily_prices", {"stock_id": stock_id}, "date,close_price")
    if not price_rows:
        return {}

    pf = pd.DataFrame(price_rows)
    pf["date"]        = pd.to_datetime(pf["date"])
    pf["close_price"] = pd.to_numeric(pf["close_price"])
    pf = pf[pf["close_price"] > 0].sort_values("date").reset_index(drop=True)

    # 月採樣
    pf["ym"]  = pf["date"].dt.to_period("M")
    monthly   = pf.groupby("ym").last().reset_index()

    if len(monthly) < MIN_YIELD_MONTHS:
        return {}

    # 逐月計算 TTM 殖利率序列
    yield_series = []
    for _, row in monthly.iterrows():
        p_date = row["date"]
        price  = float(row["close_price"])
        mask    = (div_df["ex_date"] <= p_date) & (div_df["ex_date"] > p_date - pd.Timedelta(days=365))
        ttm_div = float(div_df[mask]["cash_dividend"].sum())
        if ttm_div > 0:
            yield_series.append(ttm_div / price)

    if len(yield_series) < 10:
        return {}

    yield_arr       = np.array(yield_series)
    cheap_yield     = float(np.percentile(yield_arr, 80))   # 高殖利率 = 股價便宜
    fair_yield      = float(np.percentile(yield_arr, 50))
    expensive_yield = float(np.percentile(yield_arr, 20))   # 低殖利率 = 股價昂貴

    # 最新 TTM 現金股利
    latest_date    = pf["date"].max()
    mask           = (div_df["ex_date"] <= latest_date) & (div_df["ex_date"] > latest_date - pd.Timedelta(days=365))
    latest_ttm_div = float(div_df[mask]["cash_dividend"].sum())
    if latest_ttm_div <= 0:
        return {}

    cheap_price     = round(latest_ttm_div / cheap_yield,     2)
    fair_price      = round(latest_ttm_div / fair_yield,      2)
    expensive_price = round(latest_ttm_div / expensive_yield, 2)

    return {
        "yield_ttm_div":         round(latest_ttm_div, 2),
        "yield_cheap_yield":     round(cheap_yield     * 100, 4),
        "yield_fair_yield":      round(fair_yield      * 100, 4),
        "yield_expensive_yield": round(expensive_yield * 100, 4),
        "yield_cheap_price":     cheap_price,
        "yield_fair_price":      fair_price,
        "yield_expensive_price": expensive_price,
    }


def run():
    stock_ids = get_stock_ids_with_dividends()
    total     = len(stock_ids)
    success   = 0
    print(f"有配息紀錄的股票：{total} 支，開始計算殖利率估值帶")

    for idx, stock_id in enumerate(stock_ids, 1):
        try:
            result = calculate_yield(stock_id)
            if not result:
                print(f"  [{idx}/{total}] {stock_id} → 資料不足，跳過")
                continue

            current_price = get_current_price(stock_id)
            if current_price:
                result["yield_status"] = get_status(current_price, result["yield_cheap_price"], result["yield_fair_price"])
            else:
                result["yield_status"] = "無法計算"

            result["stock_id"] = stock_id
            supabase.table("valuations").upsert(result).execute()
            success += 1
            print(f"  [{idx}/{total}] {stock_id} → {result['yield_status']}  TTM股利:{result['yield_ttm_div']}  便宜價:{result['yield_cheap_price']}")

        except Exception as e:
            print(f"  [{idx}/{total}] {stock_id} → 錯誤: {e}")
            traceback.print_exc()

    print(f"\n完成：{success}/{total} 支股票寫入殖利率估值帶")


if __name__ == "__main__":
    run()
