"""
audit_oos_premium_bands.py — 「P/E 溢價 2~3 倍」那條線索的樣本外檢驗

## 要驗什麼

2026-08-06 的昂貴訊號回測（`backtest_expensive.py`）整體失敗——四個模型的同月
超額全為正，「昂貴」沒有選股能力。但溢價（現價 ÷ 昂貴價）分層後，2~3 倍那一格
同月超額 −3.64%、71.1% 的月份為負，看起來是真的差。

這條線索有兩個理由不能直接拿來用：
  1. **不單調**——>3 倍反而回到 −1.44%。真的估值訊號應該越貴越差。
  2. **事後翻找**——一次測了 6 個分層，挑最好看的那個當結論。

本腳本用樣本外檢驗判它生死。

## 兩道測試（第二道才是真的）

**寬鬆**：固定用 2~3 倍這一帶，看前後期符號是否都為負。
  這道測試仍在使用「事後挑好的答案」，通過了也只能說「沒有立刻自相矛盾」。

**嚴格（真正的樣本外）**：前期**讓資料自己挑出最差的帶**——複製當初的挑選程序
  ——再拿那一帶到後期驗證。這才會暴露「最差的帶會不會換一格」。
  三個切點（2021／2022／2023），沿用 `audit_oos_persistence.py` 對產業實績的做法。

## 判準（先訂再看結果，避免又一次事後解釋）

嚴格測試中**三個切點都選出「2~3 倍」且該帶的後期同月超額為負** → 通過，可談前端。
任一切點選出別的帶，或選對了但後期超額轉正 → 否決，把結論寫回 CLAUDE.md 結案。

## 為什麼用「同月超額」而非直接比報酬

與 `backtest_expensive.py` 同一個理由：昂貴訊號擠在多頭月份，直接比跨期母體
會把行情誤讀成選股能力。同月對照讓兩組吃到相同行情。

## 已知限制

- 切成前後期後，每格的月數只剩 30~45 個月，估計本身就更吵。這是樣本外檢驗
  的固有代價，不是缺陷——但它意味著「通過」的門檻要看符號一致性，不是看點估計。
- 倖存者偏差同 `backtest_expensive.py`，方向使昂貴組報酬偏樂觀（結論只能單向採信）。
"""

import os
import sys
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

import backtest_valuation as bt
import backtest_expensive as be

SPLIT_YEARS = [2021, 2022, 2023]   # 前期 < Y、後期 ≥ Y（依訊號發生月份切）

# 不重疊的三個窗口。切點法的後期窗口層層包含（≥2021 ⊇ ≥2022 ⊇ ≥2023），
# 「三次樣本外都為負」其實接近同一份資料量三次，不是三個獨立證據。
# 這組窗口互不重疊，才問得出「這個帶在每個年代都差，還是只在某個年代差」。
DISJOINT_WINDOWS = [("2019~2020", 2019, 2020), ("2021~2022", 2021, 2022),
                    ("2023~2025", 2023, 2025)]
MIN_SIGNALS = 100                  # 單一帶在單一期別的最少訊號數，不足則不評
MIN_MONTHS  = 12                   # 單一帶在單一期別的最少月數（同月超額的樣本）
TARGET_BAND = "溢價 2~3 倍"        # 被檢驗的那條線索


def band_excess(df: pd.DataFrame, uni_m: pd.Series) -> pd.DataFrame:
    """
    逐溢價帶算同月超額。

    超額本身一律經 `be.excess_stats()`——定義若哪天要改（例如改用平均而非中位），
    兩邊各刻一份就會安靜地給出不同答案。這裡只在它之上疊自己的樣本門檻。

    樣本不足者留 NaN 而非略過：「沒得評」要看得見，否則表格會少一列而不知為何。
    """
    rows = []
    for name, lo, hi in be.PREMIUM_BANDS:
        sub = df[(df["premium"] >= lo) & (df["premium"] < hi)]
        core = be.excess_stats(sub, uni_m)
        months = core.pop("_excess")
        enough = len(sub) >= MIN_SIGNALS and len(months) >= MIN_MONTHS
        rows.append({
            "分層":       name,
            "樣本數":     len(sub),
            "月數":       len(months),
            "同月超額%":  core["同月超額%"]    if enough else float("nan"),
            "負月%":      core["超額為負月%"] if enough else float("nan"),
        })
    return pd.DataFrame(rows)


def main():
    data = bt.load_all()
    print("組裝面板…")
    panels = bt.build_panels(data)
    adj = panels["adj"]

    # P/E 昂貴訊號與溢價倍數，定義與 backtest_expensive.py 完全相同（共用同一函式）
    mask, premium = bt.percentile_mask(adj, panels["eps_ttm"], bt.PE_MIN, bt.PE_MAX,
                                       be.PCT_EXPENSIVE, "expensive")
    sig = bt.forward_returns(adj, be.MAIN_HORIZON, mask)
    sig["premium"] = pd.MultiIndex.from_arrays(
        [sig["date"], sig["stock_id"]]).map(premium.stack())
    sig = sig.dropna(subset=["premium"])

    # 只要 12 個月這一個持有期；走 universe_returns 會連 6/24 個月一起算完再丟掉
    uni = bt.forward_returns(adj, be.MAIN_HORIZON)

    sig["year"] = sig["date"].str[:4].astype(int)
    uni_year = uni["date"].str[:4].astype(int)
    print(f"  訊號 {len(sig)} 筆，{sig['year'].min()}~{sig['year'].max()}")

    # ---------------------------------------------------------------- 全期基準
    all_uni_m = uni.groupby("date")["ret"].median()
    pd.set_option("display.unicode.east_asian_width", True, "display.width", 220)
    print("\n=== 全期（供對照，這就是當初翻出線索的那張表）===")
    print(band_excess(sig, all_uni_m).to_string(index=False))

    verdicts = []
    for y in SPLIT_YEARS:
        early_sig, late_sig = sig[sig["year"] < y], sig[sig["year"] >= y]
        early_uni = uni[uni_year < y].groupby("date")["ret"].median()
        late_uni  = uni[uni_year >= y].groupby("date")["ret"].median()

        early = band_excess(early_sig, early_uni)
        late  = band_excess(late_sig,  late_uni)

        print(f"\n{'='*72}\n切點 {y}：前期 < {y}（{len(early_sig)} 筆）、後期 ≥ {y}（{len(late_sig)} 筆）")
        merged = early.merge(late, on="分層", suffixes=("_前", "_後"))
        print(merged.to_string(index=False))

        # 嚴格測試：前期讓資料自己挑最差的帶（可評者中同月超額最小者）
        evaluable = early.dropna(subset=["同月超額%"])
        if evaluable.empty:
            print("  前期沒有任何帶達到樣本門檻，此切點無法檢驗")
            verdicts.append((y, None, None, None))
            continue
        picked = evaluable.loc[evaluable["同月超額%"].idxmin(), "分層"]
        late_row = late[late["分層"] == picked].iloc[0]
        oos = late_row["同月超額%"]

        print(f"  前期選出最差的帶：**{picked}**"
              f"（前期超額 {evaluable['同月超額%'].min():+.2f}%）")
        if pd.isna(oos):
            print(f"  後期該帶樣本不足（{int(late_row['樣本數'])} 筆 / {int(late_row['月數'])} 月），無法驗證")
        else:
            print(f"  後期同月超額：{oos:+.2f}%（負月 {late_row['負月%']}%）"
                  f" → {'延續為負 ✓' if oos < 0 else '轉正 ✗'}")
        verdicts.append((y, picked, oos, late_row["負月%"]))

    # ------------------------------------------------- 不重疊窗口（獨立證據）
    print(f"\n{'='*72}\n=== 不重疊窗口：「{TARGET_BAND}」在每個年代都差嗎？ ===")
    print("切點法的後期窗口層層包含，這一段才是互相獨立的證據")
    disjoint = []
    for label, y0, y1 in DISJOINT_WINDOWS:
        w_sig = sig[(sig["year"] >= y0) & (sig["year"] <= y1)]
        w_uni = uni[(uni_year >= y0) & (uni_year <= y1)].groupby("date")["ret"].median()
        tbl = band_excess(w_sig, w_uni)
        row = tbl[tbl["分層"] == TARGET_BAND].iloc[0]
        disjoint.append({"窗口": label, **{k: row[k] for k in
                         ["樣本數", "月數", "同月超額%", "負月%"]}})
        print(f"\n--- {label} ---")
        print(tbl.to_string(index=False))
    dj = pd.DataFrame(disjoint)
    print(f"\n「{TARGET_BAND}」在三個不重疊窗口：")
    print(dj.to_string(index=False))
    dj_all_neg = bool((dj["同月超額%"] < 0).all())
    print(f"  每個年代都為負：{'是' if dj_all_neg else '否 → 這不是穩定的估值規律，是特定年代的現象'}")

    # ---------------------------------------------------------------- 總結
    print(f"\n{'='*72}\n判準：三個切點都選出「{TARGET_BAND}」且後期超額為負 → 通過")
    # verdicts 每個切點必有一筆（無法檢驗者記為 None），故 all() 不會因空集合為真
    picked_all = [p for _, p, _, _ in verdicts if p]
    stable   = all(p == TARGET_BAND for _, p, _, _ in verdicts)
    negative = all(pd.notna(o) and o < 0 for _, _, o, _ in verdicts)

    print(f"  前期選出的帶：{picked_all}")
    print(f"  帶是否穩定為「{TARGET_BAND}」：{'是' if stable else '否'}")
    print(f"  後期是否都為負：{'是' if negative else '否'}")
    print(f"  不重疊窗口每個年代都為負：{'是' if dj_all_neg else '否'}")
    passed = stable and negative and dj_all_neg
    print(f"\n結論：{'通過，可談前端' if passed else '**否決** —— 這條線索不成立，寫回 CLAUDE.md 結案'}")

    if out_rows := [{"切點": y, "前期選出的帶": p, "後期同月超額%": o, "後期負月%": n}
                    for y, p, o, n in verdicts if p]:
        path = os.path.join(bt.OUT_DIR, "expensive_bands_oos.csv")
        pd.DataFrame(out_rows).to_csv(path, index=False, encoding="utf-8-sig")
        print(f"\n結果已寫入 {path}")
    print("提醒：母體不含已下市股票，昂貴組報酬被系統性高估；結論只能單向採信。")


if __name__ == "__main__":
    main()
