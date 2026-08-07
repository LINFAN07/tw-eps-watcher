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
HORIZON     = 12            # 與 by_industry 一致：持有 12 個月
SPLIT_YEARS = (2021, 2022, 2023)   # 三個切點都要通過才算延續，見 PERSIST_MIN
MIN_SAMPLE  = 30            # 兩個半期都要達到才納入（與 by_industry 門檻一致）
THRESH      = 3             # 超額 ≥ +3pp 稱「領先」、≤ −3pp 稱「落後」（與 EXCESS_THRESHOLD 一致）
MODELS      = ("P/E", "P/B", "P/S", "P/FCF")

# 判定「產業排名會延續」的 Spearman 下限。首跑實測 P/E ~0、P/B ~+0.1、P/FCF ~0，
# 唯獨 P/S +0.45~0.62——0.3 落在這個明顯的斷點上，不是為了讓 P/S 通過而挑的。
# 三個切點都要達標：單一切點的相關性對切點位置很敏感（同 backtest_discount_bands
# 的教訓：同一組資料換個切點結論就翻面）。
PERSIST_MIN = 0.3


def load() -> tuple[pd.DataFrame, pd.DataFrame]:
    def read(name):
        df = pd.read_csv(os.path.join(RESULTS_DIR, name), dtype={"stock_id": str})
        return df[df["horizon"] == HORIZON].copy()
    return read("signals.csv"), read("universe.csv")


def with_half(df: pd.DataFrame, split_year: int) -> pd.DataFrame:
    """依切點標記早／晚半期。切點是參數而非常數——三個切點要在同一次執行裡跑完"""
    out = df.copy()
    out["half"] = out["date"].str[:4].astype(int).lt(split_year).map({True: "早", False: "晚"})
    return out


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


def report(name: str, df: pd.DataFrame) -> float | None:
    """印出該模型的持續性檢驗，回傳 Spearman 相關性（組合數過少時回 None）"""
    print(f"\n{'='*60}\n{name}（{len(df)} 個產業組合，兩半期各 ≥{MIN_SAMPLE} 筆）")
    if len(df) < 4:
        print("  組合數過少，無法可靠檢驗持續性")
        if len(df):
            print(df[["industry", "早超額", "晚超額"]].round(2).to_string(index=False))
        return None

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
    return spear


def export_persistence(spearman: dict[str, list[float | None]]) -> None:
    """
    把「哪些模型的產業排名會延續」輸出成 frontend/lib/oosPersistence.ts。

    為什麼要有這一步：這個判斷原本只存在兩個地方——本腳本結尾的一段 print，
    以及 `lib/backtest.caveatFor()` 裡手寫的 `model === 'ps'`。兩者之間沒有
    任何機制；資料再累積兩年後 P/S 的延續性可能翻掉，而沒有東西會提醒重跑，
    前端也照樣宣告「這個排名相對可信」。

    做法同 expensiveStats.ts：機器產生的判定放這裡，手寫的措辭留在前端，
    前端比對兩者。不一致時**退回保守的那一句**（OOS_CAVEAT，不延續），
    而不是隱藏——說「別當預測」永遠是安全的，說「相對可信」才需要證據。
    """
    key = {"P/E": "pe", "P/B": "pb", "P/S": "ps", "P/FCF": "pfcf"}
    lines = []
    for model, values in spearman.items():
        ok = [v for v in values if v is not None]
        persists = len(ok) == len(SPLIT_YEARS) and all(v >= PERSIST_MIN for v in ok)
        shown = ", ".join("null" if v is None else f"{v:.2f}" for v in values)
        lines.append(f"  {key[model]}: {{ persists: {str(persists).lower()}, "
                     f"spearman: [{shown}] }},")

    path = os.path.join(os.path.dirname(__file__), "..", "frontend", "lib", "oosPersistence.ts")
    with open(path, "w", encoding="utf-8") as f:
        f.write(
            "// 由 scripts/audit_oos_persistence.py 產生，請勿手動編輯。重跑會覆寫此檔。\n"
            "// persists = 三個切點的 Spearman 都 ≥ "
            f"{PERSIST_MIN}（切點 {'／'.join(map(str, SPLIT_YEARS))}）。\n"
            "// 手寫的措辭在 backtest.ts；那裡會比對本檔，不一致時退回保守警語。\n\n"
            "export const OOS_PERSISTENCE = {\n" + "\n".join(lines) + "\n} as const\n"
        )
    print(f"\n已輸出 {path}")


def main():
    signals, universe = load()
    spearman: dict[str, list[float | None]] = {m: [] for m in MODELS}

    for split in SPLIT_YEARS:
        print(f"\n{'#'*60}\n# 切點 {split}（前期 < {split}、後期 ≥ {split}）\n{'#'*60}")
        sig, uni = with_half(signals, split), with_half(universe, split)
        for model in MODELS:
            spearman[model].append(report(model, excess_table(sig[sig["model"] == model], uni)))

    print(f"\n{'='*60}\n三切點彙總（Spearman，判定門檻 ≥{PERSIST_MIN} 且三段全過）：")
    for model, values in spearman.items():
        shown = " / ".join("—" if v is None else f"{v:+.2f}" for v in values)
        ok = [v for v in values if v is not None]
        verdict = ("延續 → OOS_CAVEAT_PS"
                   if len(ok) == len(SPLIT_YEARS) and all(v >= PERSIST_MIN for v in ok)
                   else "不延續 → OOS_CAVEAT")
        print(f"  {model:6s} {shown:24s} {verdict}")
    print("延續的是產業間的『相對排名』，非絕對報酬——四個模型的便宜股整體仍輸 0050。")

    export_persistence(spearman)


if __name__ == "__main__":
    main()
