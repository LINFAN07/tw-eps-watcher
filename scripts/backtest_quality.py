"""
backtest_quality.py — 「優質 × 估值不昂貴」訊號回測

回答一個產品問題：該不該做「合理估值」排行榜？

直覺是「合理不是訊號、是沒有訊號」，但直覺要用數據驗。這裡把估值帶切成
便宜／合理／不昂貴，各自疊上「優質」（ROE≥15%）濾網，看哪一種組合在
歷史上真的贏過隨便買一支同類股。沿用 backtest_valuation.py 的面板與
防 look-ahead 設計，唯一新增的是 point-in-time 的 ROE。

## 品質的 point-in-time 定義

ROE = 當時可得的 TTM EPS ÷ 當時可得的每股淨值 × 100，與前端 calcRoe 同式。
兩者都已換算到最新股數基準，但 ROE 是比值、股數因子在分子分母相消，
故不受換算影響。虧損股 ROE 為負，自然被 ≥15% 濾掉。

## 估值帶的定義（與 calculate_valuation 的 status 對齊）

當前 P/E 倍數在歷史 expanding 百分位中的位置：
  ≤ 第 20 百分位          → 便宜
  第 20 ~ 80 百分位之間    → 合理
  ≥ 第 80 百分位          → 昂貴
「不昂貴」= 便宜 + 合理（≤ 第 80 百分位）。
"""

import os
import sys
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

import backtest_valuation as bt

ROE_MIN = 15.0          # 與前端品質篩選一致
PCT_EXPENSIVE = 0.80    # 昂貴 = 歷史倍數第 80 百分位
MIN_INDUSTRY_N = 30


def pe_bands(adj: pd.DataFrame, base: pd.DataFrame, lo: float, hi: float):
    """回傳（當前倍數, 便宜門檻, 昂貴門檻）三個面板，門檻皆為 expanding 百分位"""
    base = base.reindex(columns=adj.columns).where(base > 0)
    mult = (adj / base).where(lambda m: (m >= lo) & (m <= hi))
    cheap = mult.expanding(min_periods=bt.MIN_SAMPLE).quantile(bt.PCT_CHEAP)
    exp   = mult.expanding(min_periods=bt.MIN_SAMPLE).quantile(PCT_EXPENSIVE)
    return mult, cheap, exp


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


def main():
    data = bt.load_all()
    dates = data["dates"]

    print("組裝面板…")
    adj = bt.adjusted_price_matrix(data["prices"], data["dividends"], data["factors"], dates)
    factors = bt.share_factor_table(data["bvps"])
    eps_ttm = bt.fundamental_matrix(data["eps"],  "eps",                  dates, True,    factors)
    bvps    = bt.fundamental_matrix(data["bvps"], "book_value_per_share", dates, False, factors)

    mult, cheap, exp = pe_bands(adj, eps_ttm, bt.PE_MIN, bt.PE_MAX)
    valid         = mult.notna()
    is_cheap      = valid & (mult <= cheap)
    is_reasonable = valid & (mult > cheap) & (mult < exp)
    not_expensive = valid & (mult <= exp)          # 便宜 + 合理

    roe = (eps_ttm / bvps.where(bvps > 0)) * 100
    quality = roe >= ROE_MIN

    print(f"  月數 {len(dates)}、股票 {adj.shape[1]} 支")

    print("回測中…")
    groups = {
        "P/E 便宜":            is_cheap,
        "P/E 合理（單獨）":     is_reasonable,
        "優質（ROE≥15%）":     quality & valid,
        "優質 × P/E 便宜":     quality & is_cheap,
        "優質 × 不昂貴":       quality & not_expensive,
        "優質 × 合理":         quality & is_reasonable,
    }
    uni = bt.universe_returns(adj)
    overall = pd.concat([bt.summarize(uni, "全市場等權（對照）"),
                         evaluate(adj, groups)], ignore_index=True)

    industry = data["stocks"].set_index("stock_id")["industry"]
    uni["industry"] = uni["stock_id"].map(industry)
    ind_base = uni[uni["horizon"] == 12].groupby("industry")["ret"].median() * 100

    ind = pd.concat([by_industry(adj, groups[m], m, ind_base, industry)
                     for m in ["優質 × 不昂貴", "優質 × 合理"]],
                    ignore_index=True).sort_values(["model", "超額"], ascending=[True, False])

    os.makedirs(bt.OUT_DIR, exist_ok=True)
    overall.to_csv(os.path.join(bt.OUT_DIR, "quality_overall.csv"), index=False, encoding="utf-8-sig")
    ind.to_csv(os.path.join(bt.OUT_DIR, "quality_by_industry.csv"), index=False, encoding="utf-8-sig")

    pd.set_option("display.unicode.east_asian_width", True, "display.width", 220)
    print("\n=== 整體結果（報酬單位 %）===")
    print(overall.to_string(index=False))
    print("\n=== 優質×不昂貴／優質×合理，分產業（持有 12 個月，樣本 ≥30）===")
    print(ind.to_string(index=False))
    print(f"\n結果已寫入 {bt.OUT_DIR}")
    print("提醒：母體不含已下市股票，結果偏樂觀；未計交易成本。")


if __name__ == "__main__":
    main()
