"""
backtest_yield.py — 「便宜 × 高殖利率」訊號回測

回答上榜單前必須先問的問題：把「高殖利率」疊在「便宜」上，報酬會變好還是變差？

金融、貿易百貨、塑膠、紡織這些高殖利率的大本營，正好是 backtest_valuation.py
測出「便宜訊號無效甚至為負」的產業。直接做榜單等於把價值陷阱從另一扇門放回來，
故先回測、後決定要不要上線。

## 方法（沿用 backtest_valuation.py 的面板與防 look-ahead 設計）

- 殖利率 = 過去 12 個月「已除息」的每股現金股利 ÷ 當時股價
  用 `ex_date` 判定可得性——除息已經發生的事，不存在偷看未來。
- 高殖利率 = 每個月末的**橫斷面**前 20%（與「便宜＝歷史第 20 百分位」對稱）。
  不用固定門檻（如 >5%），否則低利率年份全市場入選、高利率年份全數落榜。
- 穩定配息 = 當期、12 個月前、24 個月前的 TTM 現金股利皆 > 0（連三年有配）。
  資料表只有現金／股票股利兩欄，無法辨識「一次性配發」（處分資產、資本公積），
  連續性是現有資料能做到的最接近的替代品——**不是**等價物，判讀時須留意。

## 分子必須換算股數基準

每股股利與 EPS、每股淨值一樣，是「當時股數」下的數字，配股後股數變多、每股股利
變小，而分母的股價已除權還原到最新股數基準。分子不換算，過去的殖利率會被系統性
低估，配股頻繁的公司尤其嚴重。此處沿用 backtest_valuation.share_factor_table()。
"""

import json
import os
import sys
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

import backtest_valuation as bt

TOP_YIELD = 0.80        # 高殖利率 = 橫斷面前 20%
TTM_MONTHS = 12         # 殖利率的股利累計期
MIN_INDUSTRY_N = 30     # 分產業表的最少樣本數（與主回測一致）

# 上線成榜單的組合。前端顯示的實績必須對應榜單的實際篩選條件，
# 不可拿「P/E 便宜」或「高殖利率單獨」的數字頂替——那是別的策略的成績單。
RANK_GROUP = "P/E 便宜 × 高殖利率"


# ------------------------------------------------------------ 殖利率面板

def ttm_dividend_panel(dividends: pd.DataFrame, factors: pd.DataFrame,
                       dates: list[str]) -> pd.DataFrame:
    """
    月末 TTM 每股現金股利面板（已換算到最新股數基準）。
    以除息月份歸戶後滾動 12 個月加總；滿 12 個月前為 NaN，不以部分期間充數。
    """
    div = dividends.copy()
    div["ex_date"] = pd.to_datetime(div["ex_date"])
    div["cash_dividend"] = pd.to_numeric(div["cash_dividend"], errors="coerce")
    div = div.dropna(subset=["ex_date", "cash_dividend"])
    div = div[div["cash_dividend"] > 0].sort_values("ex_date")

    # 除息日對應到「當時最近一期已知的股數因子」，對不到者維持原值（因子 1）
    f = factors.sort_values("quarter_end_date").rename(columns={"quarter_end_date": "ex_date"})
    div = pd.merge_asof(div, f, on="ex_date", by="stock_id", direction="backward")
    div["amount"] = div["cash_dividend"] * div["factor"].fillna(1.0)

    div["m"] = div["ex_date"].dt.to_period("M")
    monthly = div.pivot_table(index="m", columns="stock_id", values="amount", aggfunc="sum")

    idx = pd.PeriodIndex(pd.to_datetime(dates), freq="M")
    # 完整月序列補 0（該月沒除息 = 股利 0，不是缺值），再滾動加總
    monthly = monthly.reindex(idx.union(monthly.index)).fillna(0.0).sort_index()
    ttm = monthly.rolling(TTM_MONTHS, min_periods=TTM_MONTHS).sum().reindex(idx)
    return ttm.set_axis(dates)


def yield_masks(adj: pd.DataFrame, ttm_div: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """回傳（高殖利率、高殖利率且連三年有配息）兩個布林面板"""
    div = ttm_div.reindex(index=adj.index, columns=adj.columns)
    yld = (div / adj).where(div > 0)          # 兩者同為最新股數基準，比值即真實殖利率

    high = yld.ge(yld.quantile(TOP_YIELD, axis=1), axis=0) & yld.notna()
    # 當期 / 12 個月前 / 24 個月前的 TTM 股利皆 > 0
    steady = (div > 0) & (div.shift(12) > 0) & (div.shift(24) > 0)
    return high, high & steady


# ------------------------------------------------------------ 統計

def evaluate(adj: pd.DataFrame, groups: dict[str, pd.DataFrame]) -> pd.DataFrame:
    parts = []
    for label, mask in groups.items():
        df = pd.concat([bt.forward_returns(adj, h, mask) for h in bt.HORIZONS],
                       ignore_index=True)
        if not df.empty:
            parts.append(bt.summarize(df, label))
    return pd.concat(parts, ignore_index=True)


def by_industry(adj: pd.DataFrame, mask: pd.DataFrame, model: str,
                ind_base: pd.Series, industry: pd.Series) -> pd.DataFrame:
    """持有 12 個月、分產業的超額報酬（對照組為同產業母體中位數）"""
    df = bt.forward_returns(adj, 12, mask)
    if df.empty:
        return pd.DataFrame()
    df["industry"] = df["stock_id"].map(industry)
    out = (df.assign(贏=lambda d: d["ret"] > d["bench"])
             .groupby("industry")
             .agg(樣本數=("ret", "size"),
                  報酬中位數=("ret", lambda s: s.median() * 100),
                  勝過0050=("贏", lambda s: s.mean() * 100))
             .reset_index())
    out.insert(0, "model", model)
    out["同業母體"] = out["industry"].map(ind_base)
    out["超額"] = out["報酬中位數"] - out["同業母體"]
    return out[out["樣本數"] >= MIN_INDUSTRY_N].round(2)


def export_frontend(overall: pd.DataFrame, ind: pd.DataFrame, dates: list[str]) -> None:
    """
    產生前端用的統計檔。獨立於 backtestStats.ts：
    那支由 backtest_valuation.py 整檔覆寫，兩邊共用一個檔會互相蓋掉。

    只輸出榜單真正會顯示的三組對照，不輸出 P/B 與「連三年配息」變體——
    榜單沒做那些，檔案裡放著只會被誤用。
    """
    def rows(df):
        return ",\n".join("  " + json.dumps(r, ensure_ascii=False) for r in df.to_dict("records"))

    ov = (overall[overall["組別"].isin([RANK_GROUP, "P/E 便宜", "全市場等權（對照）"])]
          .rename(columns={"組別": "group", "樣本數": "n", "報酬中位數": "median",
                           "報酬平均": "mean", "0050同期中位": "bench",
                           "勝率%": "winRate", "正報酬率%": "positiveRate"}))
    bi = (ind[ind["model"] == RANK_GROUP].drop(columns=["model"])
          .rename(columns={"樣本數": "n", "報酬中位數": "median", "勝過0050": "winRate",
                           "同業母體": "peer", "超額": "excess"}))

    ts = f"""// 由 scripts/backtest_yield.py 產生，請勿手動編輯。
// 重跑回測後此檔會被覆寫；判讀邏輯寫在 lib/yieldBacktest.ts。

export interface YieldOverallRow {{
  horizon: number; group: string; n: number
  median: number; mean: number; bench: number; winRate: number; positiveRate: number
}}

export interface YieldIndustryRow {{
  industry: string; n: number
  median: number; winRate: number; peer: number; excess: number
}}

/** 榜單的篩選條件，也是 OVERALL 中代表榜單本身的那一組 */
export const YIELD_RANK_GROUP = '{RANK_GROUP}'

/** 回測期間取自資料本身的第一與最後一個月末交易日 */
export const YIELD_BACKTEST_PERIOD = {{ from: '{dates[0]}', to: '{dates[-1]}', months: {len(dates)} }}

/** 分產業結果的持有期（月） */
export const YIELD_HORIZON = 12

export const YIELD_OVERALL: YieldOverallRow[] = [
{rows(ov)}
]

/** 僅含 {RANK_GROUP} 的分產業實績 */
export const YIELD_BY_INDUSTRY: YieldIndustryRow[] = [
{rows(bi)}
]
"""
    path = os.path.join(os.path.dirname(__file__), "..", "frontend", "lib", "backtestYieldStats.ts")
    with open(path, "w", encoding="utf-8") as f:
        f.write(ts)
    print(f"前端統計檔已更新：{os.path.normpath(path)}")


def main():
    data = bt.load_all()
    dates = data["dates"]

    print("組裝面板…")
    adj = bt.adjusted_price_matrix(data["prices"], data["dividends"], data["factors"], dates)
    factors = bt.share_factor_table(data["bvps"])
    eps_ttm = bt.fundamental_matrix(data["eps"],  "eps",                  dates, 4,    factors)
    bvps    = bt.fundamental_matrix(data["bvps"], "book_value_per_share", dates, None, factors)
    ttm_div = ttm_dividend_panel(data["dividends"], factors, dates)

    high, steady = yield_masks(adj, ttm_div)
    # cheap_mask 第二個回傳值是折價倍數，本腳本只看訊號本身
    pe_cheap, _ = bt.cheap_mask(adj, eps_ttm, bt.PE_MIN, bt.PE_MAX)
    pb_cheap, _ = bt.cheap_mask(adj, bvps,    bt.PB_MIN, bt.PB_MAX)
    print(f"  月數 {len(dates)}、股票 {adj.shape[1]} 支、"
          f"高殖利率訊號 {int(high.sum().sum())} 格")

    print("回測中…")
    groups = {
        "高殖利率（單獨）":        high,
        "高殖利率＋連三年配息":    steady,
        "P/E 便宜":               pe_cheap,
        RANK_GROUP:               pe_cheap & high,
        "P/E 便宜 × 高殖利率＋連三年": pe_cheap & steady,
        "P/B 便宜":               pb_cheap,
        "P/B 便宜 × 高殖利率":     pb_cheap & high,
        "P/B 便宜 × 高殖利率＋連三年": pb_cheap & steady,
    }
    uni = bt.universe_returns(adj)
    overall = pd.concat([bt.summarize(uni, "全市場等權（對照）"),
                         evaluate(adj, groups)], ignore_index=True)

    industry = data["stocks"].set_index("stock_id")["industry"]
    uni["industry"] = uni["stock_id"].map(industry)
    ind_base = uni[uni["horizon"] == 12].groupby("industry")["ret"].median() * 100

    ind = pd.concat([by_industry(adj, groups[m], m, ind_base, industry)
                     for m in [RANK_GROUP, "P/B 便宜 × 高殖利率"]],
                    ignore_index=True).sort_values(["model", "超額"], ascending=[True, False])

    os.makedirs(bt.OUT_DIR, exist_ok=True)
    overall.to_csv(os.path.join(bt.OUT_DIR, "yield_overall.csv"), index=False, encoding="utf-8-sig")
    ind.to_csv(os.path.join(bt.OUT_DIR, "yield_by_industry.csv"), index=False, encoding="utf-8-sig")
    export_frontend(overall, ind, dates)

    pd.set_option("display.unicode.east_asian_width", True, "display.width", 220)
    print("\n=== 整體結果（報酬單位 %）===")
    print(overall.to_string(index=False))
    print("\n=== 便宜 × 高殖利率，分產業（持有 12 個月，樣本 ≥30）===")
    print(ind.to_string(index=False))
    print(f"\n結果已寫入 {bt.OUT_DIR}")
    print("提醒：母體不含已下市股票，結果偏樂觀；未計交易成本；一次性配發無法辨識。")


if __name__ == "__main__":
    main()
