"""
backtest_roe_filter.py — 排行榜的「ROE≥15%」品質濾網到底擋掉了什麼？

前一個回測（backtest_quality.py）發現：把 ROE≥15% 濾網套在便宜股上，
報酬中位數從 7.29% 掉到 5.43%。但報酬不是全部——濾網的理由可能是
「避開會大賠的地雷」，用一點報酬換下檔安全。這個腳本就是要驗證這件事：

  濾網擋掉的是「賺錢的機會」，還是「賠錢的風險」？

作法：把「P/E 便宜」的股票按當時 point-in-time ROE 分層，比較每一層的
報酬**與下檔風險**（賠超過 30%／50% 的比率、最慘 10% 的報酬）。
若低 ROE 層的大賠率明顯較高，濾網就是有價值的（換來安全）；
若各層大賠率差不多、只是中位報酬不同，濾網就是純扣分。

沿用 backtest_valuation.py 的面板與防 look-ahead 設計。持有 12 個月。
ROE 未知（無 EPS 或淨值）者前端一律擋掉，故單獨列出，驗證這個預設對不對。
"""

import os
import sys
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

import backtest_valuation as bt

HORIZON = 12    # 持有月數，聚焦單一期別以看清風險分布


def summarize_risk(adj: pd.DataFrame, mask: pd.DataFrame, label: str) -> dict:
    """單組的報酬與下檔風險。空組回傳 None。"""
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
        "最慘10%報酬%": round(r.quantile(0.10) * 100, 2),   # 下檔：第 10 百分位
        "賠逾30%":     round((r < -0.30).mean() * 100, 1),
        "賠逾50%":     round((r < -0.50).mean() * 100, 1),
    }


def main():
    data = bt.load_all()
    dates = data["dates"]

    print("組裝面板…")
    adj = bt.adjusted_price_matrix(data["prices"], data["dividends"], data["factors"], dates)
    factors = bt.share_factor_table(data["bvps"])
    eps_ttm = bt.fundamental_matrix(data["eps"],  "eps",                  dates, True,    factors)
    bvps    = bt.fundamental_matrix(data["bvps"], "book_value_per_share", dates, False, factors)

    is_cheap, _ = bt.cheap_mask(adj, eps_ttm, bt.PE_MIN, bt.PE_MAX)
    roe = (eps_ttm / bvps.where(bvps > 0)) * 100
    roe = roe.reindex(index=adj.index, columns=adj.columns)

    print(f"  月數 {len(dates)}、股票 {adj.shape[1]} 支")
    print("回測中…")

    # 各層都限定在「便宜」股之內——濾網就是套在便宜榜上做二次篩
    has_roe = roe.notna()
    groups = {
        "便宜全體（有 ROE）":        is_cheap & has_roe,
        "  ROE 未知（前端擋掉）":     is_cheap & ~has_roe,
        "  ROE < 0（虧損）":         is_cheap & (roe < 0),
        "  ROE 0~8%":               is_cheap & (roe >= 0) & (roe < 8),
        "  ROE 8~15%":              is_cheap & (roe >= 8) & (roe < 15),
        "  ROE ≥ 15%（濾網保留）":   is_cheap & (roe >= 15),
        "濾網擋掉的全部（<15 或未知）": is_cheap & ~(roe >= 15),
    }

    rows = [r for r in (summarize_risk(adj, m, label) for label, m in groups.items()) if r]
    out = pd.DataFrame(rows)

    os.makedirs(bt.OUT_DIR, exist_ok=True)
    out.to_csv(os.path.join(bt.OUT_DIR, "roe_filter.csv"), index=False, encoding="utf-8-sig")

    pd.set_option("display.unicode.east_asian_width", True, "display.width", 240)
    print(f"\n=== 便宜股按 ROE 分層（持有 {HORIZON} 個月）===")
    print(out.to_string(index=False))
    print(f"\n結果已寫入 {bt.OUT_DIR}/roe_filter.csv")
    print("提醒：母體不含已下市股票，故『賠逾50%』等下檔數字是低估的（真實風險更高）。")


if __name__ == "__main__":
    main()
