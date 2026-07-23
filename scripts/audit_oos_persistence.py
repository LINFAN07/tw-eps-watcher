"""
audit_oos_persistence.py — 產業別實績的「樣本外持續性」檢驗

回答一個問題：回測算出的「某產業的便宜訊號超額報酬」，是可外推到未來的選股
依據，還是只描述過去、對未來沒有預測力？

## 方法（沿用 2026-07-22 對 P/E、P/B 的做法）

把持有 12 個月的訊號切成前半期（year ≤ 2021）與後半期（year ≥ 2022），
各自逐產業算「超額」＝該產業便宜訊號報酬中位數 − 同產業全體（universe）報酬中位數。
只留在**兩個半期都** ≥ MIN_SAMPLE 筆的 (模型, 產業) 組合，然後看：

  - 前期超額 vs 後期超額的相關性（Pearson、Spearman）——接近 0 或負值＝不延續
  - 符號翻轉：前期被標「落後」（超額 ≤ −THRESH）者，後期有多少仍落後 / 反轉領先
  - 前期「落後」組 vs「領先」組的後期超額中位數——若前者不低於後者，代表排名無用

資料來源：backtest_results/signals.csv 與 universe.csv（由 backtest_valuation.py 產生）。
"""

import os
import sys
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "backtest_results")
HORIZON    = 12       # 與 by_industry 一致：持有 12 個月
SPLIT_YEAR = 2022     # 前期 < 2022、後期 ≥ 2022
MIN_SAMPLE = 30       # 兩個半期都要達到才納入（與 by_industry 門檻一致）
THRESH     = 3        # 超額 ≥ +3pp 稱「領先」、≤ −3pp 稱「落後」（與 EXCESS_THRESHOLD 一致）


def load() -> tuple[pd.DataFrame, pd.DataFrame]:
    def read(name):
        df = pd.read_csv(os.path.join(RESULTS_DIR, name), dtype={"stock_id": str})
        df = df[df["horizon"] == HORIZON].copy()
        df["half"] = df["date"].str[:4].astype(int).lt(SPLIT_YEAR).map({True: "早", False: "晚"})
        return df
    return read("signals.csv"), read("universe.csv")


def excess_table(signals: pd.DataFrame, universe: pd.DataFrame) -> pd.DataFrame:
    """逐 (模型, 產業, 半期) 算超額；只保留兩半期都有 ≥MIN_SAMPLE 樣本的組合"""
    # 同產業母體中位數（逐半期），作為超額的基準
    uni_med = (universe.groupby(["industry", "half"])["ret"].median() * 100).rename("peer")

    g = signals.groupby(["model", "industry", "half"])
    tbl = pd.DataFrame({"n": g.size(), "sig_med": g["ret"].median() * 100}).reset_index()
    tbl = tbl.merge(uni_med.reset_index(), on=["industry", "half"], how="left")
    tbl["excess"] = tbl["sig_med"] - tbl["peer"]

    # 攤成早/晚兩欄，要求兩邊都達門檻
    wide = tbl.pivot(index=["model", "industry"], columns="half",
                     values=["excess", "n"])
    wide = wide[(wide[("n", "早")] >= MIN_SAMPLE) & (wide[("n", "晚")] >= MIN_SAMPLE)]
    out = pd.DataFrame({
        "早超額": wide[("excess", "早")],
        "晚超額": wide[("excess", "晚")],
        "早n":    wide[("n", "早")].astype(int),
        "晚n":    wide[("n", "晚")].astype(int),
    }).reset_index()
    return out


def report(name: str, df: pd.DataFrame) -> None:
    print(f"\n{'='*60}\n{name}（{len(df)} 個產業組合，兩半期各 ≥{MIN_SAMPLE} 筆）")
    if len(df) < 4:
        print("  組合數過少，無法可靠檢驗持續性")
        if len(df):
            print(df[["industry", "早超額", "晚超額"]].round(2).to_string(index=False))
        return

    pear = df["早超額"].corr(df["晚超額"], method="pearson")
    # Spearman ＝「排名後的 Pearson」，如此免裝 scipy
    spear = df["早超額"].rank().corr(df["晚超額"].rank(), method="pearson")
    print(f"  前後期相關性：Pearson {pear:+.2f}、Spearman {spear:+.2f}"
          "　（接近 0 或負＝排名不延續）")

    behind = df[df["早超額"] <= -THRESH]
    if len(behind):
        still = (behind["晚超額"] <= -THRESH).mean() * 100
        flip  = (behind["晚超額"] >= THRESH).mean() * 100
        print(f"  前期「落後」{len(behind)} 組 → 後期仍落後 {still:.0f}%、反轉領先 {flip:.0f}%"
              f"，後期超額中位數 {behind['晚超額'].median():+.2f}pp")
    ahead = df[df["早超額"] >= THRESH]
    if len(ahead):
        print(f"  前期「領先」{len(ahead)} 組 → 後期超額中位數 {ahead['晚超額'].median():+.2f}pp")


def main():
    signals, universe = load()
    for model in ["P/E", "P/B", "P/S", "P/FCF"]:
        df = excess_table(signals[signals["model"] == model], universe)
        report(model, df)

    print(f"\n{'='*60}\n2026-07-23 首跑結論（三切點 2021／2022／2023）：\n"
          "  P/E ~0、P/B ~+0.1、P/FCF ~0 → 不延續，用 OOS_CAVEAT\n"
          "  P/S +0.45~0.62 穩定為正 → 唯一延續，前端改用 OOS_CAVEAT_PS\n"
          "延續的是產業間的『相對排名』，非絕對報酬——四個模型的便宜股整體仍輸 0050。")


if __name__ == "__main__":
    main()
