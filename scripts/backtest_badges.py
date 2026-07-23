"""
backtest_badges.py — 便宜榜的「⭐頂級優質」「🔍潛力黑馬」徽章有沒有誤導？

前面幾支回測證明 ROE≥15%、利益率≥10% 兩個濾網【各自單獨】套在便宜股上會降報酬。
但徽章用的是兩者【交集】，且作用是「置頂＋正面標記」而非篩選，傷害形態未必相同，
不能直接套用——故單獨回測這兩個交集組的實際表現。

對照 frontend/components/CheapLeaderboardClient.tsx 的定義：
  頂級優質 isTopQuality = ROE≥15% 且 利益率≥10%
  潛力黑馬 isPotential  = 非KY 且 非頂級優質 且 利益率≥10% 且 ROE≥0
共識榜把頂級優質置頂、個股列給兩者正面色徽章——若這兩組報酬其實低於便宜全體，
置頂與正面標記就是把「經營品質好」誤讀成「投資報酬好」。

沿用 backtest_valuation 面板；利益率分母 TTM 營收取自 monthly_revenue 歸季，
與 calculate_quality_metrics 同定義（見 backtest_margin_filter）。持有 12 個月。
"""

import os
import sys
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

import backtest_valuation as bt
from backtest_margin_filter import quarterly_revenue

HORIZON = 12


def summarize_risk(adj, mask, label):
    df = bt.forward_returns(adj, HORIZON, mask)
    if df.empty:
        return None
    r = df["ret"]
    return {
        "組別":        label,
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
    eps_ttm = bt.fundamental_matrix(data["eps"],  "eps",                  dates, 4, factors)
    bvps    = bt.fundamental_matrix(data["bvps"], "book_value_per_share", dates, None, factors)

    is_cheap, _ = bt.cheap_mask(adj, eps_ttm, bt.PE_MIN, bt.PE_MAX)
    roe = ((eps_ttm / bvps.where(bvps > 0)) * 100).reindex(index=adj.index, columns=adj.columns)
    ttm_op  = bt.fundamental_matrix(income, "operating_income",  dates, 4)
    ttm_rev = bt.fundamental_matrix(quarterly_revenue(mrev), "quarterly_revenue", dates, 4)
    margin = (ttm_op / ttm_rev.where(ttm_rev > 0) * 100).reindex(index=adj.index, columns=adj.columns)

    stocks = data["stocks"].set_index("stock_id")
    import numpy as np
    ky_v = stocks["name"].map(lambda s: "-KY" in str(s)).reindex(adj.columns).fillna(False).values
    ky_b = pd.DataFrame(np.repeat(ky_v[None, :], len(adj.index), axis=0),
                        index=adj.index, columns=adj.columns)

    top       = (roe >= 15) & (margin >= 10)                       # ⭐ 頂級優質
    potential = (~ky_b) & (~top) & (margin >= 10) & (roe >= 0)     # 🔍 潛力黑馬
    neither   = is_cheap & ~top & ~potential

    print(f"  月數 {len(dates)}、股票 {adj.shape[1]} 支")
    print("回測中…")

    groups = {
        "便宜全體":              is_cheap,
        "  ⭐ 頂級優質（置頂＋正面標記）": is_cheap & top,
        "  🔍 潛力黑馬（正面標記）":     is_cheap & potential,
        "  兩者皆非（無徽章）":          neither,
    }
    rows = [r for r in (summarize_risk(adj, m, label) for label, m in groups.items()) if r]
    out = pd.DataFrame(rows)

    os.makedirs(bt.OUT_DIR, exist_ok=True)
    out.to_csv(os.path.join(bt.OUT_DIR, "badges.csv"), index=False, encoding="utf-8-sig")

    pd.set_option("display.unicode.east_asian_width", True, "display.width", 250)
    print(f"\n=== 便宜股的徽章分組（持有 {HORIZON} 個月）===")
    print(out.to_string(index=False))
    print(f"\n結果已寫入 {bt.OUT_DIR}/badges.csv")
    print("提醒：母體不含已下市股票，下檔為低估。")


if __name__ == "__main__":
    main()
