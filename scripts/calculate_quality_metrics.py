"""
品質指標計算腳本（TTM 營業利益率）
載入 income_statement_quarterly + valuations 既有 P/S 每股營收，
計算 TTM 營業利益率（%），寫入 valuations.operating_margin。

計算邏輯：
  TTM 營業利益 = 最近 4 季 operating_income 加總（元）
  TTM 年營收   = ps_revenue_per_share × listed_shares × 1000（元）
  營業利益率   = TTM 營業利益 / TTM 年營收 × 100

用法：
  python scripts/calculate_quality_metrics.py
"""

import os
import sys
import pandas as pd
from dotenv import load_dotenv
from supabase import create_client

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

MIN_QUARTERS = 4  # 至少需要 4 季損益表資料才計算


def _fetch_paged(table: str, columns: str) -> list:
    """分頁取得 Supabase 資料（繞過 1000 筆上限）"""
    all_rows, offset = [], 0
    while True:
        resp = supabase.table(table).select(columns).range(offset, offset + 999).execute()
        all_rows.extend(resp.data or [])
        if len(resp.data or []) < 1000:
            break
        offset += 1000
    return all_rows


def main():
    # ── 1. 載入損益表（75k 筆，~8 頁）
    print("載入 income_statement_quarterly...")
    income_df = pd.DataFrame(_fetch_paged("income_statement_quarterly", "stock_id,quarter_end_date,operating_income"))
    income_df["operating_income"] = pd.to_numeric(income_df["operating_income"], errors="coerce")
    print(f"  → {len(income_df)} 筆")

    # ── 2. 載入 stocks + valuations 的 TTM 每股營收
    print("載入 stocks + valuations...")
    stocks_df = pd.DataFrame(_fetch_paged("stocks", "stock_id,listed_shares"))
    val_df    = pd.DataFrame(_fetch_paged("valuations", "stock_id,ps_revenue_per_share"))
    stocks_df["listed_shares"]       = pd.to_numeric(stocks_df["listed_shares"],       errors="coerce")
    val_df["ps_revenue_per_share"]   = pd.to_numeric(val_df["ps_revenue_per_share"],   errors="coerce")

    # TTM 年營收（元）= 每股營收 × 流通股數（千股）× 1000
    revenue_map: dict[str, float] = {}
    merged = val_df.merge(stocks_df, on="stock_id")
    for _, row in merged.iterrows():
        rev = row["ps_revenue_per_share"]
        shares = row["listed_shares"]
        if pd.notna(rev) and pd.notna(shares) and rev > 0 and shares > 0:
            revenue_map[row["stock_id"]] = float(rev) * float(shares) * 1000
    print(f"  → {len(revenue_map)} 支股票有 TTM 營收資料")

    # ── 3. 對每支股票取最近 4 季 operating_income 加總
    print("計算 TTM 營業利益率...")
    results: dict[str, float] = {}
    for stock_id, grp in income_df.groupby("stock_id"):
        latest4 = grp.sort_values("quarter_end_date", ascending=False).head(MIN_QUARTERS)
        if len(latest4) < MIN_QUARTERS or latest4["operating_income"].isna().any():
            continue
        ttm_op_income = float(latest4["operating_income"].sum())  # 元

        ttm_revenue = revenue_map.get(stock_id)
        if not ttm_revenue:
            continue  # 無月營收（金融股等）→ 跳過

        raw = ttm_op_income / ttm_revenue * 100
        # 保留真實比率，不 clamp、也不因超出範圍寫 null。
        #
        # 原本 clamp 到 ±999.99 以避開 DECIMAL(6,2) 溢位，但邊界值是【假數字】——
        # 使用者看到「-999.99%」會當成真實比率讀，實際上 6467 是 -18,375%。
        #
        # 曾考慮改寫 null，實測後否決：有 75 支比率 < -100%，其中 39 支 ROE ≥0
        # （本業大虧、靠業外撐住帳面獲利），排行榜正是靠「利益率 < 0」把它們擋掉。
        # 寫 null 會讓其中 14 支便宜股漏進榜單——那是最該被警示的類型。
        # 故改為放寬欄位（DECIMAL(10,2)）容納真實值，極端值的可讀性由前端處理。
        results[stock_id] = round(raw, 2)

    extreme = sum(1 for v in results.values() if v is not None and abs(v) > 100)
    print(f"  → 有效結果：{len(results)} 支（其中 {extreme} 支比率絕對值 >100%，"
          f"營收極小、本業大幅虧損，數值為真實值不做截斷）")

    # ── 4. 逐筆寫入 valuations.operating_margin
    print("寫入 valuations.operating_margin...")
    for i, (sid, margin) in enumerate(results.items(), 1):
        supabase.table("valuations").update({"operating_margin": margin}).eq("stock_id", sid).execute()
        if i % 200 == 0:
            print(f"  已寫入 {i}/{len(results)}")

    print(f"完成！已更新 {len(results)} 支股票的 TTM 營業利益率")


if __name__ == "__main__":
    main()
