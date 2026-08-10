"""
backtest_filter_compare.py — 排行榜「改前端前後」的淨效果對比

backtest_roe_filter.py 與 backtest_margin_filter.py 已分別證明兩個品質濾網
（ROE≥15%、營業利益率≥10%）各自都在降報酬、增風險。這支腳本把前端**完整的**
篩選鏈搬到 point-in-time 回測上，直接比較使用者實際會看到的兩個版本：

  情境 A（現狀）：永久排除虧損 + ROE≥15% + 利益率≥10% + 排除KY + 排除帶寬發散
  情境 B（建議）：永久排除虧損 +                       排除KY + 排除帶寬發散

除了報酬與下檔，額外報「月均入選檔數」——那是使用者真正看到的榜單規模，
用來確認關掉品質濾網不會讓榜單爆量到無法使用。

篩選邏輯逐條對齊 frontend/components/CheapLeaderboardClient.tsx 的 beforeDiffuse：
- 永久排除虧損：roe<0 或 margin<0（NaN 不算虧損，保留）
- filterRoe：(roe ?? 0) >= 15 → roe 未知者被擋
- filterMargin：margin>=10；margin 未知時金融豁免、非金融擋
- excludeKY：股名含 -KY
- excludeDiffuse：帶寬 (expensive−cheap)/fair > 1.14（lib/bandStability THRESHOLDS.pe[1]）
"""

import os
import sys
import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

import backtest_valuation as bt
from backtest_margin_filter import quarterly_revenue

HORIZON = 12
DIFFUSE_HI = 1.14                       # lib/bandStability.ts THRESHOLDS.pe[1]
FIN_KW = ("金融", "保險", "銀行", "證券")


def pe_bands(adj, base, lo, hi):
    """回傳當前倍數與 cheap/fair/expensive 三條 expanding 百分位帶"""
    base = base.reindex(columns=adj.columns).where(base > 0)
    mult = (adj / base).where(lambda m: (m >= lo) & (m <= hi))
    q = lambda p: mult.expanding(min_periods=bt.MIN_SAMPLE).quantile(p)
    return mult, q(bt.PCT_CHEAP), q(0.50), q(PCT80)


PCT80 = 0.80


def bcast(sr: pd.Series, like: pd.DataFrame) -> pd.DataFrame:
    """把每股一個布林值，沿月份廣播成與 like 同形的面板"""
    v = sr.reindex(like.columns).fillna(False).values
    return pd.DataFrame(np.repeat(v[None, :], len(like.index), axis=0),
                        index=like.index, columns=like.columns)


def summarize(adj, mask, label) -> dict:
    df = bt.forward_returns(adj, HORIZON, mask)
    if df.empty:
        return None
    r = df["ret"]
    return {
        "版本":        label,
        "樣本數":      len(df),
        "報酬中位數%": round(r.median() * 100, 2),
        "報酬平均%":   round(r.mean() * 100, 2),
        "正報酬率%":   round((r > 0).mean() * 100, 1),
        "勝過0050%":   round((df["ret"] > df["bench"]).mean() * 100, 1),
        "最慘10%報酬%": round(r.quantile(0.10) * 100, 2),
        "賠逾30%":     round((r < -0.30).mean() * 100, 1),
        "賠逾50%":     round((r < -0.50).mean() * 100, 1),
    }


def main():
    data = bt.load_all()
    dates = data["dates"]

    print("讀取損益表與月營收…")
    income = bt._cached("income", lambda: bt._paged(
        "income_statement_quarterly", "stock_id,quarter_end_date,operating_income", "stock_id"))
    mrev = bt._cached("monthly_revenue", lambda: bt._paged(
        "monthly_revenue", "stock_id,year_month,revenue", "stock_id"))

    print("組裝面板…")
    adj = bt.adjusted_price_matrix(data["prices"], data["dividends"], data["factors"], dates)
    factors = bt.share_factor_table(data["bvps"])
    eps_ttm = bt.fundamental_matrix(data["eps"],  "eps",                  dates, True, factors)
    bvps    = bt.fundamental_matrix(data["bvps"], "book_value_per_share", dates, False, factors)

    mult, cheap, fair, exp = pe_bands(adj, eps_ttm, bt.PE_MIN, bt.PE_MAX)
    is_cheap = (mult <= cheap) & mult.notna()
    width = (exp - cheap) / fair
    diffuse = width > DIFFUSE_HI

    roe = ((eps_ttm / bvps.where(bvps > 0)) * 100).reindex(index=adj.index, columns=adj.columns)
    ttm_op  = bt.fundamental_matrix(income, "operating_income",  dates, True)
    ttm_rev = bt.fundamental_matrix(quarterly_revenue(mrev), "quarterly_revenue", dates, True)
    margin = (ttm_op / ttm_rev.where(ttm_rev > 0) * 100).reindex(index=adj.index, columns=adj.columns)

    stocks = data["stocks"].set_index("stock_id")
    fin_b = bcast(stocks["industry"].map(lambda s: any(k in str(s) for k in FIN_KW)), adj)
    ky_b  = bcast(stocks["name"].map(lambda s: "-KY" in str(s)), adj)

    # 逐條對齊前端 beforeDiffuse
    loss       = (roe < 0) | (margin < 0)                       # NaN→False，不算虧損
    roe_ge15   = roe >= 15                                      # NaN→False（前端 ?? 0）
    margin_ok  = (margin >= 10) | (margin.isna() & fin_b)       # 未知時金融豁免
    keep       = is_cheap & ~loss & ~ky_b & ~diffuse
    maskA = keep & roe_ge15 & margin_ok                         # 現狀：四濾網
    maskB = keep                                               # 建議：關品質濾網
    maskB_extra = maskB & ~maskA                               # 改版後新增可見的股

    print(f"  月數 {len(dates)}、股票 {adj.shape[1]} 支")
    print("回測中…")

    rows = [r for r in [
        summarize(adj, is_cheap, "便宜全體（無任何濾網）"),
        summarize(adj, maskA, "A · 現狀（四濾網全開）"),
        summarize(adj, maskB, "B · 建議（關兩個品質濾網）"),
        summarize(adj, maskB_extra, "  └ B 比 A 多出的那批"),
    ] if r]
    out = pd.DataFrame(rows)

    # 月均入選檔數：近 12 個月平均，貼近使用者現在看到的榜單規模
    def monthly_count(mask):
        return round(mask.iloc[-12:].sum(axis=1).mean(), 1)
    counts = pd.DataFrame([
        {"版本": "A · 現狀（四濾網全開）",      "月均入選檔數": monthly_count(maskA)},
        {"版本": "B · 建議（關兩個品質濾網）",  "月均入選檔數": monthly_count(maskB)},
    ])

    os.makedirs(bt.OUT_DIR, exist_ok=True)
    out.to_csv(os.path.join(bt.OUT_DIR, "filter_compare.csv"), index=False, encoding="utf-8-sig")

    pd.set_option("display.unicode.east_asian_width", True, "display.width", 250)
    print(f"\n=== 改前端前後對比（便宜股，持有 {HORIZON} 個月）===")
    print(out.to_string(index=False))
    print("\n=== 榜單規模（近 12 個月月均入選檔數）===")
    print(counts.to_string(index=False))
    print(f"\n結果已寫入 {bt.OUT_DIR}/filter_compare.csv")
    print("提醒：母體不含已下市股票，下檔為低估；統計為全入選池，非前 50 名。")


if __name__ == "__main__":
    main()
