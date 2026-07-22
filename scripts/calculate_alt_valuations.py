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
from price_adjust import back_adjust   # 除權息即時還原（不儲存，見 price_adjust.py）
from periodicity import report_window   # 季報／半年報的期數判定（四處共用）
import ex_factors                      # 除權息還原因子（整表快取，避免逐股查詢）

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
sys.stderr.reconfigure(encoding="utf-8", line_buffering=True)
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

# 各模型合理倍數範圍（超出者視為資料異常，不納入百分位計算）
PB_MIN,   PB_MAX   = 0.1, 50.0
PS_MIN,   PS_MAX   = 0.1, 200.0
PFCF_MIN, PFCF_MAX = 0.1, 200.0

MIN_PB_QUARTERS  = 8   # P/B：至少 2 年季度資料
MIN_PS_MONTHS    = 24  # P/S：至少 2 年月營收（TTM 需 12 個月，再加 12 個月用於計算 PS 序列）
MIN_PFCF_QTRS    = 8   # P/FCF：至少 2 年季度資料
MIN_YIELD_MONTHS = 36  # 殖利率：至少 3 年月資料（需涵蓋多個配息週期）


# 各模型的輸出欄位（數值欄位, 狀態欄位）。
# 模型從「可計算」變成「不適用」時，必須把舊值寫回 null，
# 否則上次算出的數字會永久殘留（例如 FCF 轉負後仍顯示舊的 P/FCF 目標價）。
MODEL_FIELDS = {
    "pb":    (["pb_book_value", "pb_cheap_pb", "pb_fair_pb", "pb_expensive_pb",
               "pb_cheap_price", "pb_fair_price", "pb_expensive_price"], "pb_status"),
    "ps":    (["ps_revenue_per_share", "ps_cheap_ps", "ps_fair_ps", "ps_expensive_ps",
               "ps_cheap_price", "ps_fair_price", "ps_expensive_price"], "ps_status"),
    "pfcf":  (["pfcf_per_share", "pfcf_cheap_pfcf", "pfcf_fair_pfcf", "pfcf_expensive_pfcf",
               "pfcf_cheap_price", "pfcf_fair_price", "pfcf_expensive_price"], "pfcf_status"),
    "yield": (["yield_ttm_div", "yield_cheap_yield", "yield_fair_yield", "yield_expensive_yield",
               "yield_cheap_price", "yield_fair_price", "yield_expensive_price"], "yield_status"),
}


def cleared(model: str) -> dict:
    """模型不適用時要寫入的欄位值：數值全部 null，狀態標為「無法計算」"""
    cols, status_col = MODEL_FIELDS[model]
    return {**{c: None for c in cols}, status_col: "無法計算"}


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


def fetch_dividends(stock_id: str) -> list[tuple[str, float, float]]:
    """
    該股除權息 (除權息日, 現金股利, 股票股利)，供即時還原用。
    配股必須一起取——只還原現金股利會在配股日留下數十個百分點的假跌幅。
    注意：殖利率模型（calculate_yield）另行只取現金股利，那是刻意的，
    殖利率的本質是現金報酬，不該把配股計入。
    """
    rows = _fetch_paged("dividends", {"stock_id": stock_id},
                        "ex_date,cash_dividend,stock_dividend")
    return [(r["ex_date"], float(r["cash_dividend"] or 0), float(r.get("stock_dividend") or 0))
            for r in rows]


def fetch_prices(stock_id: str) -> pd.DataFrame:
    rows = _fetch_paged("daily_prices", {"stock_id": stock_id}, "date,close_price")
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["date"]        = df["date"].astype(str)
    df["close_price"] = pd.to_numeric(df["close_price"])
    df = df.sort_values("date").reset_index(drop=True)
    # adj_price：除權息即時還原（不儲存），供 P/B / P/S / P/FCF 的「歷史倍數分布」使用，
    # 避免除息機械性下跌被當成估值變化。現價與殖利率一律用原始 close_price
    # （殖利率本質是實際價 vs 股利，還原會虛增歷史殖利率）。
    df["adj_price"]   = back_adjust(df["date"].tolist(), df["close_price"].tolist(),
                                    fetch_dividends(stock_id),
                                    ex_factors.for_stock(supabase, stock_id))
    return df


# 季末月份 → 該年度第幾季
QUARTER_INDEX = {"03": 1, "06": 2, "09": 3, "12": 4}


def decumulate(df: pd.DataFrame, cols: tuple[str, ...]) -> pd.DataFrame:
    """
    還原「年初至今累計」為單季金額。

    台灣現金流量表以年度累計揭露（Q1 重置、逐季累加），
    例如台積電 2025 年營業現金流為 0.63→1.12→1.55→2.27 兆，
    直接四季相加會得到 5.57 兆，實際 TTM 僅約 2.3 兆。

    規則：該年度第一季直接採用；其餘季度減去同年度前一季。
    同年度前一季缺漏時無法還原，該筆剔除（避免產生錯誤數字）。
    """
    df = df.sort_values("quarter_end_date").reset_index(drop=True)
    df["_year"] = df["quarter_end_date"].str[:4]
    df["_qidx"] = df["quarter_end_date"].str[5:7].map(QUARTER_INDEX)
    df = df.dropna(subset=["_qidx"]).reset_index(drop=True)

    for col in cols:
        restored = []
        for _, row in df.iterrows():
            if row["_qidx"] == 1:
                restored.append(row[col])
                continue
            prev = df[(df["_year"] == row["_year"]) & (df["_qidx"] == row["_qidx"] - 1)]
            restored.append(row[col] - float(prev.iloc[0][col]) if not prev.empty else np.nan)
        df[col] = restored  # 迴圈結束後才寫回，確保相減用的是原始累計值

    return df.dropna(subset=list(cols)).drop(columns=["_year", "_qidx"]).reset_index(drop=True)


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
    rows = _fetch_paged("balance_sheet_quarterly", {"stock_id": stock_id},
                        "quarter_end_date,book_value_per_share,shares_thousand")
    if not rows:
        return {}

    bvps_df = pd.DataFrame(rows)
    bvps_df["quarter_end_date"]     = bvps_df["quarter_end_date"].astype(str)
    bvps_df["book_value_per_share"] = pd.to_numeric(bvps_df["book_value_per_share"])
    bvps_df = bvps_df[bvps_df["book_value_per_share"] > 0].sort_values("quarter_end_date").reset_index(drop=True)

    if len(bvps_df) < MIN_PB_QUARTERS:
        return {}

    # 歷史每股淨值換算到「最新股數基準」，與已除權還原的股價配套。
    # 每股淨值是各季用當時股數申報的，配股後股數變多、數值變小，財報不追溯調整；
    # 股價卻已還原到最新基準，分母不跟著換算，P/B 會被系統性壓低。
    # 實測 1436 的 P/E 因此被壓低 43%（同一個成因），詳見 calculate_valuation.share_factors。
    # 最新一季因子必為 1，故下方的 cur_bvps 不受影響。
    shares = pd.to_numeric(bvps_df["shares_thousand"], errors="coerce")
    latest_shares = shares.dropna().iloc[-1] if shares.notna().any() else None
    factor = (shares / latest_shares).fillna(1.0) if latest_shares and latest_shares > 0 \
        else pd.Series(1.0, index=bvps_df.index)
    bvps_df["adj_bvps"] = bvps_df["book_value_per_share"] * factor

    # 每季季末對應股價 → 計算歷史 P/B 序列
    pb_series = []
    for _, row in bvps_df.iterrows():
        bvps   = float(row["adj_bvps"])              # 已換算到最新股數基準
        q_date = row["quarter_end_date"]
        nearby = price_df[price_df["date"] <= q_date]
        if nearby.empty or bvps <= 0:
            continue
        price = float(nearby.iloc[-1]["adj_price"])   # 歷史 P/B 分布用還原價
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
    ps_series = []

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
            price = float(nearby.iloc[-1]["adj_price"])   # 歷史 P/S 分布用還原價
        else:
            price = float(month_prices.iloc[-1]["adj_price"])

        ps = price / rps
        if PS_MIN <= ps <= PS_MAX:
            ps_series.append(ps)

    # 同 P/FCF：基準值取「最新 12 個月」的 TTM 營收，不沿用迴圈殘留值
    latest_rps = float(rev_df.iloc[-12:]["revenue"].sum()) / (listed_shares * 1000)

    if len(ps_series) < 12 or latest_rps <= 0:
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

    # 原始資料為年度累計，必須先還原為單季金額才能加總出 TTM
    cf_df = decumulate(cf_df, ("operating_cf", "capex"))

    if len(cf_df) < MIN_PFCF_QTRS:
        return {}

    # FCF = 營業現金流 + 資本支出（capex 為負值，加法等於扣除）
    cf_df["fcf"] = cf_df["operating_cf"] + cf_df["capex"]

    # 半年報公司（興櫃）只有 6/12 月，固定取 4 期會把兩年當成 TTM。
    # 與 P/E 共用同一份判定——先前這裡自寫一份且視窗是 8 期，
    # 與 calculate_valuation 的 6 期不同步（註解卻宣稱一致）。
    w = report_window(cf_df["quarter_end_date"])

    pfcf_series = []

    for i in range(w - 1, len(cf_df)):
        ttm_fcf = float(cf_df.iloc[i - w + 1: i + 1]["fcf"].sum())
        # 現金流量表單位為元；listed_shares 單位為千股
        # 元 ÷ (千股 × 1000) = 元/股
        fcf_ps  = ttm_fcf / (listed_shares * 1000)
        if fcf_ps <= 0:  # 負 FCF 無意義，不納入百分位
            continue

        q_date = cf_df.iloc[i]["quarter_end_date"]
        nearby = price_df[price_df["date"] <= q_date]
        if nearby.empty:
            continue
        price = float(nearby.iloc[-1]["adj_price"])   # 歷史 P/FCF 分布用還原價

        pfcf = price / fcf_ps
        if PFCF_MIN <= pfcf <= PFCF_MAX:
            pfcf_series.append(pfcf)

    # 基準值必須取「最新一季」的 TTM FCF，不能沿用迴圈中最後一個為正的舊季度，
    # 否則近期 FCF 轉負的公司會用過期現金流算出目標價。
    # 最新 TTM FCF 為負代表 P/FCF 模型不適用，直接不給估值。
    latest_fcf_ps = float(cf_df.iloc[-w:]["fcf"].sum()) / (listed_shares * 1000)

    if len(pfcf_series) < MIN_PFCF_QTRS or latest_fcf_ps <= 0:
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


# ─────────────── 殖利率估值帶 ───────────────

def calculate_yield(stock_id: str, price_df: pd.DataFrame, current_price: float) -> dict:
    rows = _fetch_paged("dividends", {"stock_id": stock_id}, "ex_date,cash_dividend")
    if not rows:
        return {}

    div_df = pd.DataFrame(rows)
    div_df["ex_date"]       = pd.to_datetime(div_df["ex_date"])
    div_df["cash_dividend"] = pd.to_numeric(div_df["cash_dividend"], errors="coerce")
    div_df = div_df[div_df["cash_dividend"] > 0].sort_values("ex_date").reset_index(drop=True)
    if div_df.empty:
        return {}

    # 月採樣：取每月最後一筆收盤價
    pf = price_df.copy()
    pf["date"] = pd.to_datetime(pf["date"])
    pf["ym"]   = pf["date"].dt.to_period("M")
    monthly    = pf.groupby("ym").last().reset_index()

    if len(monthly) < MIN_YIELD_MONTHS:
        return {}

    # 逐月計算 TTM 現金股利 → 殖利率序列
    yield_series = []
    for _, row in monthly.iterrows():
        p_date = row["date"]
        price  = float(row["close_price"])
        if price <= 0:
            continue
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
        "yield_cheap_yield":     round(cheap_yield     * 100, 4),  # 儲存為百分比
        "yield_fair_yield":      round(fair_yield      * 100, 4),
        "yield_expensive_yield": round(expensive_yield * 100, 4),
        "yield_cheap_price":     cheap_price,
        "yield_fair_price":      fair_price,
        "yield_expensive_price": expensive_price,
        "yield_status":          get_status(current_price, cheap_price, fair_price),
    }


# ─────────────── 主流程 ───────────────

def run(stock_ids: list[str] | None = None):
    all_stocks  = fetch_all_stocks()
    shares_map  = {s["stock_id"]: s.get("listed_shares") for s in all_stocks}

    if stock_ids is None:
        stock_ids = list(shares_map.keys())

    total                                       = len(stock_ids)
    success_pb = success_ps = success_pfcf = success_yield = 0
    print(f"開始計算替代估值，共 {total} 支股票")

    for idx, stock_id in enumerate(stock_ids, 1):
        try:
            price_df = fetch_prices(stock_id)
            if price_df.empty:
                print(f"  [{idx}/{total}] {stock_id} → 無股價資料，跳過")
                continue

            current_price  = float(price_df.iloc[-1]["close_price"])
            listed_shares  = shares_map.get(stock_id)

            # 模型算不出來時一律寫回 cleared()，確保舊值不會殘留
            pb = calculate_pb(stock_id, price_df, current_price)
            ps = calculate_ps(stock_id, price_df, current_price, listed_shares)
            pfcf = calculate_pfcf(stock_id, price_df, current_price, listed_shares)
            yld = calculate_yield(stock_id, price_df, current_price)

            success_pb    += bool(pb)
            success_ps    += bool(ps)
            success_pfcf  += bool(pfcf)
            success_yield += bool(yld)

            updates = {
                "stock_id": stock_id,
                **(pb   or cleared("pb")),
                **(ps   or cleared("ps")),
                **(pfcf or cleared("pfcf")),
                **(yld  or cleared("yield")),
            }
            supabase.table("valuations").upsert(updates).execute()

            pb_s   = pb.get("pb_status",    "—") if pb   else "—"
            ps_s   = ps.get("ps_status",    "—") if ps   else "—"
            pfcf_s = pfcf.get("pfcf_status","—") if pfcf else "—"
            yld_s  = yld.get("yield_status","—") if yld  else "—"
            print(f"  [{idx}/{total}] {stock_id} → P/B:{pb_s}  P/S:{ps_s}  P/FCF:{pfcf_s}  殖利率:{yld_s}")

        except Exception as e:
            print(f"  [{idx}/{total}] {stock_id} → 錯誤: {e}")
            traceback.print_exc()

    print(f"\n完成：P/B {success_pb} 支 ／ P/S {success_ps} 支 ／ P/FCF {success_pfcf} 支 ／ 殖利率 {success_yield} 支")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="計算替代估值模型（P/B、P/S、P/FCF）")
    parser.add_argument("stock_ids", nargs="*", help="指定股票代碼（留空則全市場）")
    args = parser.parse_args()
    run(args.stock_ids or None)
