"""
backtest_margin_filter.py — 排行榜的「營業利益率≥10%」品質濾網擋掉了什麼？

延續 backtest_roe_filter.py 的問題，換成另一個品質濾網。同樣要分辨：
濾網擋掉的是「賺錢的機會」還是「賠錢的風險」？

## 線上定義（calculate_quality_metrics.py）

  營業利益率 = TTM 營業利益 ÷ TTM 營收 × 100

回測必須用同一個定義，否則又是「線上一套、回測一套」（殖利率那次的教訓）。
- 分子 TTM 營業利益：income_statement_quarterly 的 operating_income，滾動加總。
- 分母 TTM 營收：monthly_revenue（月營收，元）歸季加總成季營收後，同樣滾動加總。
兩者都用 backtest_valuation.fundamental_matrix，共用季末對齊、申報可用日與半年報
判定（2 期 vs 4 期），確保分子分母同期。利益率是比值，不需股數換算。

## 已知近似（寫下盲區，符合資料誠信原則）

- 半年報公司（營業利益只揭露 6/12 月）：分子用 2 期（全年）、分母若月營收完整
  則用 4 季（全年），期間長度一致；但兩者「最新可得截止點」可能不同步
  （月營收更新快、半年報更新慢）。這類公司在 P/E 便宜股中屬少數，視為雜訊。
- 月營收不足整季（缺月）者，該季不計入，避免半季營收壓低分母、虛增利益率。
- 無月營收的公司（多為金融股、部分興櫃）利益率為 NaN，前端對非金融一律擋掉、
  金融豁免；本腳本先看整體數值分層，未知組另計。
"""

import os
import sys
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

import backtest_valuation as bt

HORIZON = 12

# 月份 → 該季季末月（民國/西元無關，只看月份分組）
_Q_END_MONTH = {1: 3, 2: 3, 3: 3, 4: 6, 5: 6, 6: 6,
                7: 9, 8: 9, 9: 9, 10: 12, 11: 12, 12: 12}
FINANCIAL_KW = ("金融", "保險", "銀行", "證券")


def quarterly_revenue(mr: pd.DataFrame) -> pd.DataFrame:
    """月營收（元）歸季加總。只保留完整 3 個月的季，避免缺月壓低分母。"""
    df = mr.copy()
    df["ym"] = pd.to_datetime(df["year_month"])
    df["revenue"] = pd.to_numeric(df["revenue"], errors="coerce")
    df = df.dropna(subset=["revenue"])
    qm = df["ym"].dt.month.map(_Q_END_MONTH)
    df["quarter_end_date"] = (pd.to_datetime(
        dict(year=df["ym"].dt.year, month=qm, day=1)) + pd.offsets.MonthEnd(0))
    agg = (df.groupby(["stock_id", "quarter_end_date"])["revenue"]
             .agg(quarterly_revenue="sum", months="count").reset_index())
    return agg[agg["months"] == 3][["stock_id", "quarter_end_date", "quarterly_revenue"]]


def summarize_risk(adj: pd.DataFrame, mask: pd.DataFrame, label: str) -> dict:
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
    eps_ttm = bt.fundamental_matrix(data["eps"], "eps", dates, 4, factors)

    qrev = quarterly_revenue(mrev)
    # 利益率是比值，不傳 factors（分子分母皆為公司總額，非每股）
    ttm_op  = bt.fundamental_matrix(income, "operating_income",  dates, 4)
    ttm_rev = bt.fundamental_matrix(qrev,   "quarterly_revenue", dates, 4)
    margin = (ttm_op / ttm_rev.where(ttm_rev > 0) * 100).reindex(index=adj.index, columns=adj.columns)

    is_cheap, _ = bt.cheap_mask(adj, eps_ttm, bt.PE_MIN, bt.PE_MAX)

    # 金融股：無月營收 → 利益率 NaN，前端豁免保留。標記出來以拆解「未知」組。
    industry = data["stocks"].set_index("stock_id")["industry"].reindex(adj.columns)
    is_fin = industry.map(lambda s: any(k in str(s) for k in FINANCIAL_KW))
    fin_cols = adj.columns[is_fin.fillna(False).values]

    has_m = margin.notna()
    unknown = is_cheap & ~has_m
    unknown_fin = unknown & pd.DataFrame(
        {c: (c in set(fin_cols)) for c in adj.columns}, index=adj.index)

    print(f"  月數 {len(dates)}、股票 {adj.shape[1]} 支")
    print("回測中…")

    groups = {
        "便宜全體（有利益率）":        is_cheap & has_m,
        "  利益率未知（其中金融）":     unknown_fin,
        "  利益率未知（非金融，前端擋）": unknown & ~unknown_fin,
        "  利益率 < 0（本業虧損）":     is_cheap & (margin < 0),
        "  利益率 0~10%":             is_cheap & (margin >= 0) & (margin < 10),
        "  利益率 ≥ 10%（濾網保留）":   is_cheap & (margin >= 10),
        "濾網擋掉的全部（<10 或未知）":  is_cheap & ~(margin >= 10),
    }

    rows = [r for r in (summarize_risk(adj, m, label) for label, m in groups.items()) if r]
    out = pd.DataFrame(rows)

    os.makedirs(bt.OUT_DIR, exist_ok=True)
    out.to_csv(os.path.join(bt.OUT_DIR, "margin_filter.csv"), index=False, encoding="utf-8-sig")

    pd.set_option("display.unicode.east_asian_width", True, "display.width", 250)
    print(f"\n=== 便宜股按營業利益率分層（持有 {HORIZON} 個月）===")
    print(out.to_string(index=False))
    print(f"\n結果已寫入 {bt.OUT_DIR}/margin_filter.csv")
    print("提醒：母體不含已下市股票，下檔數字為低估；半年報公司分子分母可能不同步（少數）。")


if __name__ == "__main__":
    main()
