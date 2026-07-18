"""
估值計算腳本
讀取 Supabase 的 EPS 與股價，計算 P/E 河流圖估值，寫入 valuations 資料表。

P/E 河流圖邏輯：
  TTM EPS = 最近 4 季 EPS 合計（興櫃半年報改用 2 期）
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
import numpy as np
from price_adjust import back_adjust   # 除權息即時還原（不儲存，見 price_adjust.py）

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


def fetch_dividends(stock_id: str) -> list[tuple[str, float]]:
    """該股現金股利 (除息日, 每股股利)，供即時還原用"""
    rows = _fetch_paged("dividends", {"stock_id": stock_id}, "ex_date,cash_dividend")
    return [(r["ex_date"], float(r["cash_dividend"]))
            for r in rows if r.get("cash_dividend") is not None]


def fetch_prices(stock_id: str) -> pd.DataFrame:
    rows = _fetch_paged("daily_prices", {"stock_id": stock_id}, "date,close_price")
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["close_price"] = pd.to_numeric(df["close_price"])
    df = df.sort_values("date").reset_index(drop=True)
    # adj_price：除權息即時還原（不儲存），供歷史 P/E 分布使用，避免除息機械性
    # 下跌被當成估值變化。ISO 日期字串字典序即時間序，可直接餵 back_adjust。
    # 現價仍取原始 close_price（見 calculate_valuation 的 current_price）。
    df["adj_price"] = back_adjust(df["date"].astype(str).tolist(),
                                  df["close_price"].tolist(),
                                  fetch_dividends(stock_id))
    df["date"] = pd.to_datetime(df["date"])
    return df


def _eps_window(eps_df: pd.DataFrame) -> int:
    """興櫃半年報只有 6/30 與 12/31，用 2 期；上市/上櫃季報用 4 期"""
    months = set(eps_df["quarter_end_date"].dt.month.unique())
    return 2 if months.issubset({6, 12}) else 4


def build_pe_series(eps_df: pd.DataFrame, price_df: pd.DataFrame) -> pd.DataFrame:
    """用 merge_asof 向量化計算每個交易日的 P/E，取代逐行迴圈"""
    w = _eps_window(eps_df)
    eps = eps_df.copy()
    eps["ttm_eps"] = eps["eps"].rolling(w, min_periods=w).sum()
    eps = eps.dropna(subset=["ttm_eps"])

    merged = pd.merge_asof(
        price_df.sort_values("date"),
        eps[["quarter_end_date", "ttm_eps"]].rename(columns={"quarter_end_date": "date"}),
        on="date", direction="backward",
    )
    merged = merged.dropna(subset=["ttm_eps"])
    merged = merged[merged["ttm_eps"] > 0].copy()
    merged["pe"] = merged["adj_price"] / merged["ttm_eps"]   # 歷史 P/E 分布用還原價
    return merged[(merged["pe"] >= PE_MIN) & (merged["pe"] <= PE_MAX)]


def compute_normalized_eps(eps_df: pd.DataFrame) -> float | None:
    """取近 5 年 EPS 算術平均作為常態化基準；不足 2 年資料回傳 None"""
    w = _eps_window(eps_df)
    recent = eps_df.tail(w * 5)["eps"].astype(float)
    if len(recent) < w * 2:
        return None
    return float(recent.mean())


def detect_nonrecurring(eps_df: pd.DataFrame) -> tuple[float, str | None]:
    """
    偵測最近一個 TTM 週期（季報 4 期 / 半年報 2 期）是否有疑似一次性收益。
    使用 IQR 方法：上界 = Q75 + 2.5 × IQR（最小 IQR 為 0.5 避免零除）。
    若偵測到，將離群季度 cap 至上界後重算 TTM；否則回傳原始 TTM。
    回傳 (normalized_ttm, warning_text or None)
    """
    w        = _eps_window(eps_df)
    all_eps  = eps_df["eps"].astype(float)
    recent_4 = eps_df.tail(w)["eps"].astype(float)

    q25, q75 = float(np.percentile(all_eps, 25)), float(np.percentile(all_eps, 75))
    iqr = max(q75 - q25, 0.5)
    upper_fence = q75 + 2.5 * iqr

    outlier_mask = recent_4 > upper_fence
    if not outlier_mask.any():
        return float(recent_4.sum()), None

    # 找出離群季度，組成警告文字
    outlier_rows = eps_df.tail(w)[outlier_mask.values]
    parts = [
        f"{row['quarter_end_date'].strftime('%Y-%m-%d')} EPS {row['eps']:.2f} 元"
        for _, row in outlier_rows.iterrows()
    ]
    warning = f"TTM EPS 含疑似一次性收益（{', '.join(parts)}；正常上界 {upper_fence:.2f} 元），估值已調整"

    # 將離群季 cap 至上界，重算正規化 TTM
    normalized_ttm = float(recent_4.clip(upper=upper_fence).sum())
    return normalized_ttm, warning


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

    ttm_eps, warning = detect_nonrecurring(eps_df)
    normalized_eps   = compute_normalized_eps(eps_df)
    current_price    = float(price_df.iloc[-1]["close_price"])

    # 決定計算基準 EPS：
    # 優先嘗試以「5 年均值」替代谷底 TTM；
    # 若兩者都低於 0.5 元，P/E 模型本身失效，改給強警告。
    low_eps_warning = None
    if (normalized_eps is not None and normalized_eps > 0.5 and
            (ttm_eps <= 0 or ttm_eps < normalized_eps * 0.3)):
        # TTM 遠低於長期均值，改用 5 年均值計算目標價
        effective_eps = normalized_eps
        low_eps_warning = (
            f"TTM EPS {ttm_eps:.2f} 元遠低於常態水準"
            f"（近 5 年均 EPS {normalized_eps:.2f} 元），"
            f"估值已改用常態化 EPS 計算，現價 P/E 僅供參考"
        )
    elif ttm_eps <= 0.5 and (normalized_eps is None or normalized_eps <= 0.5):
        # TTM 和長期均值都極低，P/E 估值架構在此失效
        effective_eps = ttm_eps
        norm_str = f"近 5 年均 {normalized_eps:.2f} 元" if normalized_eps is not None else "歷史資料不足"
        low_eps_warning = (
            f"EPS 長期偏低（TTM {ttm_eps:.2f} 元，{norm_str}），"
            f"P/E 估值模型不適用——現價反映市場對未來獲利的預期，"
            f"以下目標價僅供格局參考，不代表合理買點"
        )
    elif (normalized_eps is not None and normalized_eps > 0.5 and
          ttm_eps > normalized_eps * 3):
        # TTM 遠高於長期均值，可能處於獲利高峰，目標價偏樂觀
        effective_eps = ttm_eps
        norm_expensive = round(normalized_eps * expensive_pe, 2)
        low_eps_warning = (
            f"TTM EPS {ttm_eps:.2f} 元顯著高於長期均值（近 5 年均 {normalized_eps:.2f} 元），"
            f"目前可能處於獲利高峰。若 EPS 回歸均值，以均值計算昂貴價約 {norm_expensive} 元，"
            f"目標價已依現行 TTM EPS 計算，高峰期估值偏樂觀"
        )
    else:
        effective_eps = ttm_eps

    # 合併兩種警告（低 EPS 優先顯示）
    combined_warning = (
        f"{low_eps_warning}；{warning}" if (low_eps_warning and warning)
        else low_eps_warning or warning
    )

    if effective_eps <= 0 or current_price <= 0:
        status = "無法計算"
    elif current_price <= effective_eps * cheap_pe:
        status = "便宜"
    elif current_price <= effective_eps * fair_pe:
        status = "合理"
    else:
        status = "昂貴"

    def r(v): return round(float(v), 2)

    # EPS 為負時，負值乘以正 P/E 倍數會得到無意義的負數目標價，
    # 且倍數越大價格越低，導致便宜/合理/昂貴順序顛倒。
    # 此情況 P/E 模型不適用（status 已標為「無法計算」），目標價一律留空。
    has_target = effective_eps > 0

    return {
        "stock_id":        stock_id,
        "ttm_eps":         r(ttm_eps),
        "normalized_eps":  r(normalized_eps) if normalized_eps is not None else None,
        "cheap_pe":        r(cheap_pe),
        "fair_pe":         r(fair_pe),
        "expensive_pe":    r(expensive_pe),
        "cheap_price":     r(effective_eps * cheap_pe) if has_target else None,
        "fair_price":      r(effective_eps * fair_pe) if has_target else None,
        "expensive_price": r(effective_eps * expensive_pe) if has_target else None,
        "current_price":   r(current_price),
        "status":          status,
        "warning":         combined_warning,
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
            # 估值失效（長期虧損、資料不足等）：清除既有目標價。
            # 若僅跳過，資料庫會永久殘留上次算出的舊值，且不再有任何機制修正。
            try:
                supabase.table("valuations").update({
                    "cheap_price": None, "fair_price": None, "expensive_price": None,
                    "status": "無法計算",
                }).eq("stock_id", stock_id).execute()
                print(f"  [{idx}/{total}] {stock_id} -> 無法計算，已清除舊目標價")
            except Exception as e:
                print(f"  [{idx}/{total}] {stock_id} -> 清除舊目標價失敗: {e}")
            skipped += 1

    print(f"\n完成：成功 {success} 支，跳過 {skipped} 支")


if __name__ == "__main__":
    run()
