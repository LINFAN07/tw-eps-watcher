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

# 建立 P/E 百分位帶所需的最少樣本數。序列改為週採樣後（見 to_weekly），
# 40 點 = 40 週 ≈ 10 個月；先前是 40 個交易日 ≈ 2 個月。
# 門檻等於收緊 5 倍，會使 31 支上市未滿 10 個月的新股改為「無法計算」——
# 這是刻意的：用不到一年的價格算出來的百分位帶不具參考性，
# 其中 18 支原本顯示「便宜」，比沒有估值更容易誤導。
MIN_PE_SAMPLES = 40


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


def fetch_dividends(stock_id: str) -> list[tuple[str, float, float]]:
    """
    該股除權息 (除權息日, 現金股利, 股票股利)，供即時還原用。
    配股必須一起取——只還原現金股利會在配股日留下數十個百分點的假跌幅。
    """
    rows = _fetch_paged("dividends", {"stock_id": stock_id},
                        "ex_date,cash_dividend,stock_dividend")
    return [(r["ex_date"], float(r["cash_dividend"] or 0), float(r.get("stock_dividend") or 0))
            for r in rows]


def fetch_official_factors(stock_id: str) -> dict[str, float]:
    """
    交易所公告的還原因子 {除權息日: 參考價 ÷ 前收盤價}。

    優先於股利自算——自算公式涵蓋不了現金增資與減資（見 price_adjust.py）。
    上櫃／興櫃只有當日資料、無歷史，那些日期查無官方值時自動回退自算。
    """
    rows = _fetch_paged("ex_right_factors", {"stock_id": stock_id},
                        "ex_date,prev_close,ref_price")
    return {r["ex_date"]: float(r["ref_price"]) / float(r["prev_close"])
            for r in rows if float(r["prev_close"] or 0) > 0}


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
                                  fetch_dividends(stock_id),
                                  fetch_official_factors(stock_id))
    df["date"] = pd.to_datetime(df["date"])
    return df


def filing_date(quarter_end: pd.Timestamp) -> pd.Timestamp:
    """
    財報在市場上真正可得的日期＝主管機關的申報期限。
    Q1→5/15、Q2→8/14、Q3→11/14、年報→次年 3/31；
    半年報公司（興櫃）6/30 的期限為 8/31，取較晚者以策保守。

    為什麼不能用季末日對齊：2018-04-01 不可能知道 2018Q1 的 EPS。
    以季末日對齊等於讓歷史 P/E 序列使用「當時還沒公布的財報」，
    那些點是算不出來的，卻被算了出來——屬於 look-ahead。

    2026-07-22 實測影響（20% 分位，即便宜價基準）：
      台積電 +0.6%、金融 +1.4%、配股大戶 +2.2%、興櫃半年報 −0.3%。
      幅度都在 3% 內，且沒有股票因樣本變短而失去估值——
      修這一項是為了【正確性】（消除 look-ahead），不是為了修正大偏差。

    ⚠️ 實作時的陷阱：不可直接把 eps 的 quarter_end_date 換成申報日。
    _eps_window() 靠季度月份是否為 {6,12} 判斷半年報，換日期後月份變成 {3,8}，
    半年報會被誤判為季報、TTM 從 2 期變 4 期（等於把 2 年當 1 年），
    序列大幅縮短、P/E 腰斬。首次評估即因此誤得「興櫃股差 −44.7%、
    約 32 支會失去估值」的結論。正確做法是保留 quarter_end_date 供週期判斷，
    只在對齊股價時使用申報日。
    """
    y, m = quarter_end.year, quarter_end.month
    return {3:  pd.Timestamp(y, 5, 15),
            6:  pd.Timestamp(y, 8, 31),
            9:  pd.Timestamp(y, 11, 14),
            12: pd.Timestamp(y + 1, 3, 31)}[m]


def share_factors(stock_id: str) -> pd.DataFrame:
    """
    各季的股數調整因子 = 當季股數 ÷ 最新股數，用來把歷史每股數值
    追溯換算到「最新股數基準」。

    為什麼需要：EPS 與每股淨值都是各季用【當時股數】申報的，配股後股數變多，
    同樣的獲利分給更多股，數值自然變小——財報並未追溯調整前期。
    而歷史股價已用除權還原換算到最新股數基準（見 price_adjust.py），
    若分母不跟著換算，P/E、P/B 會被系統性壓低。

    2026-07-22 實測 1436：配股前真實 P/E 6.90，只還原股價卻不調 EPS 會變成 4.86，
    使目標價憑空下修 28%。那不是揭露真相，是分子調了、分母沒調造成的新偏差。

    最新一季的因子必為 1，故「當前 TTM EPS」不受影響——
    目標價＝今天的 EPS ×（已換算基準的）歷史百分位，兩者自洽。

    P/S 與 P/FCF 不需要這個調整：它們的每股值本來就是用【最新】股數算出來的。
    """
    rows = _fetch_paged("balance_sheet_quarterly", {"stock_id": stock_id},
                        "quarter_end_date,shares_thousand")
    rows = [r for r in rows if r.get("shares_thousand")]
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["quarter_end_date"] = pd.to_datetime(df["quarter_end_date"])
    df = df.sort_values("quarter_end_date")
    latest = float(df.iloc[-1]["shares_thousand"])
    if latest <= 0:
        return pd.DataFrame()
    df["factor"] = df["shares_thousand"].astype(float) / latest
    return df[["quarter_end_date", "factor"]].reset_index(drop=True)


def apply_share_factors(df: pd.DataFrame, value_col: str, factors: pd.DataFrame) -> pd.Series:
    """
    把 df[value_col] 依各季股數因子換算到最新股數基準。
    股本季度與財報季度未必逐一對齊（興櫃為半年報），故用 merge_asof 向前對應；
    對應不到者維持原值（因子 1），不猜、不外插。
    """
    if factors.empty:
        return df[value_col].astype(float)
    merged = pd.merge_asof(
        df[["quarter_end_date", value_col]].sort_values("quarter_end_date"),
        factors, on="quarter_end_date", direction="backward",
    )
    return merged[value_col].astype(float) * merged["factor"].fillna(1.0).values


def _eps_window(eps_df: pd.DataFrame) -> int:
    """興櫃半年報只有 6/30 與 12/31，用 2 期；上市/上櫃季報用 4 期"""
    months = set(eps_df["quarter_end_date"].dt.month.unique())
    return 2 if months.issubset({6, 12}) else 4


def to_weekly(price_df: pd.DataFrame) -> pd.DataFrame:
    """
    把價格序列統一降成「每週最後一個交易日」。

    為什麼要在計算時再降一次，而不是資料庫裡有什麼就用什麼：
    daily_prices 為了看門狗、現價判定與跨來源比對，會保留近 3 個月的每日資料，
    更早則只留每週最後一個交易日（容量所需）。若直接混用這兩種密度，
    近 3 個月的點在 P/E 序列中的權重會被放大約 5 倍，整條估值帶被近期價格污染。

    2026-07-21 實測（台積電）：近期保日 + 早期週採樣使 P/E 中位數偏高 7.6%，
    長榮 33.8%、大田 18.9%，且有股票的便宜/合理/昂貴標籤因此翻轉。
    統一降成週之後，位移回到中位 0.59%、最大 1.70%。

    對已瘦身的舊資料，這個函式是 no-op（本來就一週一點）；
    它真正的作用是把近 3 個月的每日資料也拉齊到同一密度。
    """
    week = price_df["date"].dt.to_period("W")
    return (price_df.loc[price_df.groupby(week)["date"].idxmax()]
                    .sort_values("date").reset_index(drop=True))


def build_pe_series(eps_df: pd.DataFrame, price_df: pd.DataFrame,
                    factors: pd.DataFrame | None = None) -> pd.DataFrame:
    """
    用 merge_asof 向量化計算每週的 P/E，取代逐行迴圈。

    factors 給定時，歷史 EPS 會換算到最新股數基準——必須與「歷史股價已除權還原」
    配套，否則分子分母基準不一致（見 share_factors）。
    """
    price_df = to_weekly(price_df)   # 時間權重必須均勻，見 to_weekly
    w = _eps_window(eps_df)
    eps = eps_df.copy()
    # 先逐季換算再滾動加總：每季 EPS 各自對應自己那一季的股數，
    # 加總後即「近 w 季總獲利 ÷ 最新股數」，與現價的股數基準一致
    eps["adj_eps"] = apply_share_factors(eps, "eps", factors) if factors is not None \
        else eps["eps"].astype(float)
    eps["ttm_eps"] = eps["adj_eps"].rolling(w, min_periods=w).sum()
    eps = eps.dropna(subset=["ttm_eps"])

    # 以「財報實際可得日」而非季末日對齊股價，否則歷史 P/E 會用到當時尚未公布的
    # 財報（look-ahead）。半年報公司受影響最大，見 filing_date。
    eps["avail_date"] = eps["quarter_end_date"].map(filing_date)
    merged = pd.merge_asof(
        price_df.sort_values("date"),
        eps[["avail_date", "ttm_eps"]].rename(columns={"avail_date": "date"})
           .sort_values("date"),
        on="date", direction="backward",
    )
    merged = merged.dropna(subset=["ttm_eps"])
    merged = merged[merged["ttm_eps"] > 0].copy()
    merged["pe"] = merged["adj_price"] / merged["ttm_eps"]   # 歷史 P/E 分布用還原價
    return merged[(merged["pe"] >= PE_MIN) & (merged["pe"] <= PE_MAX)]


def compute_normalized_eps(eps_df: pd.DataFrame) -> float | None:
    """
    取近 5 年 EPS 算術平均作為常態化基準；不足 2 年資料回傳 None。

    回傳值的單位是「年度 EPS」，與 ttm_eps 同基準——所有呼叫端都拿它跟 TTM 比大小
    （× 3 判獲利高峰、× 0.3 判獲利谷底），或直接當成 TTM 的替代值乘上 P/E 倍數。
    eps_quarterly.eps 存的是「單季」值，季均必須先乘上一個 TTM 週期的期數（季報 4／
    半年報 2）才能年化，否則就是拿「平均每季賺多少」去跟「這一年賺多少」比。

    2026-07-21 事故：漏了這個 × w，季均被當年均用。判斷式 `ttm > normalized × 3`
    實際變成 `ttm > 年均 × 0.75`，只要今年沒比五年均衰退 25% 以上就被標成
    「獲利高峰、P/E 不可信」——全市場 633 檔中招（修正後僅 5 檔），儒鴻、豐泰
    這類獲利穩定的公司也被誤標，連帶被踢出便宜排行榜與推薦模型。
    """
    w = _eps_window(eps_df)
    recent = eps_df.tail(w * 5)["eps"].astype(float)
    if len(recent) < w * 2:
        return None
    return float(recent.mean()) * w   # 季（或半年）均 → 年化，與 ttm_eps 同單位


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

    series = build_pe_series(eps_df, price_df, share_factors(stock_id))
    if len(series) < MIN_PE_SAMPLES:
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
