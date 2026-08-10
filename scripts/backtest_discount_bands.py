"""
backtest_discount_bands.py — 折價倍數分層：pe_deep_discount 與 pb_reliable 的門檻依據

## 為什麼要有這支

`valuations.pe_deep_discount`（便宜價 > 現價 3 倍）與 `pb_reliable`（便宜價 ≤ 現價 2 倍）
是排行榜與推薦模型的過濾條件，兩個門檻不同是回測結果。但那次回測**沒有留下腳本**——
數字寫在 `frontend/lib/peReliability.ts` 的註解裡，`backtest_valuation.py` 只把折價
倍數記進長表「供事後分析」。等於門檻建在一次無法重現的分析上。

2026-08-06 修 TTM 視窗後必須重新校準（TTM 變了，便宜價跟著變，折價倍數也變），
才發現沒有東西可以重跑。這支就是把那次分析固定下來。

## 方法學（必須與當初一致，否則新舊數字不可比）

`frontend/lib/peReliability.ts` 記載的是「持有 12 個月，**逐月中位數的中位**」。
不是把所有訊號混在一起取中位——同一個月的訊號會一起受大盤影響，混池等於讓
訊號多的月份主導結果。故先對每個月取中位，再對月份取中位。
本腳本兩種都印，但判讀一律看逐月版（`月中位` 欄）。

## 判讀條件：全期為負 **且** 每一個切點的【後段】都為負

為什麼只要求後段：這是一道**前瞻性**濾網，要擋的是「從今天起買進會賠」。
用三個不同起點的近期窗口各驗一次，可以排除「只在某一段時間成立」的假象，
又不會因為十年前的市場結構不同而否決一個現在有效的訊號。

前段一併印出但不參與判定，因為它答的是另一個問題（這個效果是不是一直都在）。
2026-08-06 實測：P/B 的 2~3 倍組後段 −12.40 / −14.21 / −21.41，前段卻是
+0.28 / +0.91 / +1.45——**深度折價的傷害集中在近年，早年幾乎不存在**。
這不影響「現在該不該擋」的結論，但它是個要記住的事實：門檻建立在近期樣本上。

⚠️ 曾經用過兩個更嚴的版本，都不可行，寫下來以免有人改回去：
  - 「只看全期」：P/E 2~3 倍全期 −2.51%，會做出把門檻從 3 倍收到 2 倍的錯誤決定。
  - 「每段（含前段）都為負」：六格全部不通過，連現有兩個門檻依據的那兩格也不通過，
    等於什麼都判不出來。前段是巢狀區間（≤2021 ⊂ ≤2022 ⊂ ≤2023），不是獨立檢定。

**只看全期會做出錯誤決定**，這不是假設性的顧慮：2026-08-06 修完 TTM 後重跑，
P/E 的 2~3 倍組全期 −2.51%（原分析 +1.00%），照「全期為負就該擋」會把門檻
從 3 倍收到 2 倍。

**單一切點也不夠**——同一天的第二個教訓：切在 2022-05 得到 −5.69% / **+10.19%**
（不一致，不該改），切在 2021-05 得到 −1.76% / −3.25%（一致，該改）。
同一組資料、兩個切點、相反的結論。切點的選擇成了結論的來源，那不是證據。

故採 `audit_oos_persistence.py` 的做法：**多個切點，全部一致才算數**。
該組只有 151 檔獨立股票、488 筆逐月重疊觀測，本來就撐不起強結論。

## 盲區

- 多切點仍非嚴謹的樣本外檢驗，只是「對切點位置不敏感」的最低要求。
- 逐月重疊觀測會高估樣本量：488 筆只來自 151 檔股票，同一檔在相鄰月份高度相關。
  獨立股票數已一併印出，數字小的組別一律當成「證據不足」而非「證據為負」。
- 判讀只看符號，不看幅度。−0.1% 與 −10% 同樣算「負」，但前者可能只是雜訊。

用法：
  python scripts/backtest_discount_bands.py
"""

import os
import sys
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

import backtest_valuation as bt

HORIZON = 12
BANDS = [("折價 1~2 倍", 1.0, 2.0), ("折價 2~3 倍", 2.0, 3.0), ("折價 >3 倍", 3.0, float("inf"))]

# 與 audit_oos_persistence.py 相同的三個切點。固定年份而非「資料的中位月」——
# 中位月會隨資料範圍浮動，重跑時前後段的定義就變了，跨次結果無法比較。
CUTS = ["2021-12-31", "2022-12-31", "2023-12-31"]


def _monthly_median(df: pd.DataFrame) -> float | None:
    """逐月取中位再對月份取中位。同月的訊號一起受大盤影響，混池會讓訊號多的月份主導"""
    return None if df.empty else round(df.groupby("date")["ret"].median().median() * 100, 2)


def summarize(df: pd.DataFrame, label: str, cuts: list[str]) -> dict | None:
    """逐月中位數的中位為主；每個切點的前後兩段一併算出（判讀必看，見模組說明）"""
    if df.empty:
        return None
    row = {
        "組別":     label,
        "樣本數":   len(df),
        "獨立股票": df["stock_id"].nunique(),
        "月份數":   df["date"].nunique(),
        "月中位%":  _monthly_median(df),
        "混池中位%": round(df["ret"].median() * 100, 2),
        "勝過0050%": round((df["ret"] > df["bench"]).mean() * 100, 1),
        "賠逾30%":  round((df["ret"] < -0.30).mean() * 100, 1),
    }
    for cut in cuts:
        row[f"≤{cut[:7]}"] = _monthly_median(df[df["date"] <= cut])
        row[f">{cut[:7]}"] = _monthly_median(df[df["date"] > cut])
    return row


def main():
    data = bt.load_all()
    dates = data["dates"]

    print("組裝面板…")
    adj = bt.adjusted_price_matrix(data["prices"], data["dividends"], data["factors"], dates)
    factors = bt.share_factor_table(data["bvps"])
    bases = {
        "P/E": (bt.fundamental_matrix(data["eps"], "eps", dates, True, factors), bt.PE_MIN, bt.PE_MAX),
        "P/B": (bt.fundamental_matrix(data["bvps"], "book_value_per_share", dates, False, factors),
                bt.PB_MIN, bt.PB_MAX),
    }

    pd.set_option("display.unicode.east_asian_width", True, "display.width", 240)

    # 切點與 audit_oos_persistence.py 一致：固定年份而非「資料的中位月」。
    # 用中位月會讓切點隨資料範圍浮動，重跑時前後段的定義就變了、無法跨次比較。
    out_all, verdicts = [], []
    for model, (base, lo, hi) in bases.items():
        is_cheap, discount = bt.cheap_mask(adj, base, lo, hi)
        out_all.append(summarize(bt.forward_returns(adj, HORIZON, is_cheap),
                                 f"{model} 便宜全體", CUTS))
        for label, band_lo, band_hi in BANDS:
            mask = is_cheap & (discount >= band_lo) & (discount < band_hi)
            row = summarize(bt.forward_returns(adj, HORIZON, mask), f"  {model} {label}", CUTS)
            if row:
                out_all.append(row)
                verdicts.append((model, label, row))

    table = pd.DataFrame([r for r in out_all if r])
    print(f"\n=== 折價倍數分層（持有 {HORIZON} 個月，切點 {', '.join(CUTS)}）===")
    print(table.to_string(index=False))

    print("\n=== 判讀（該擋 = 全期為負【且】每個切點的後段都為負）===")
    for model, label, r in verdicts:
        later = {k: v for k, v in r.items() if k.startswith(">")}
        early_pos = [k for k, v in r.items() if k.startswith("≤") and v is not None and v >= 0]
        if any(v is None for v in later.values()):
            verdict = "證據不足（某個後段沒有觀測）"
        elif r["月中位%"] < 0 and all(v < 0 for v in later.values()):
            verdict = "✅ 該擋——全期與三個後段都為負"
            if early_pos:
                verdict += f"（但前段 {', '.join(early_pos)} 為正：效果集中在近年，非長期恆存）"
        elif r["月中位%"] < 0:
            pos = [k for k, v in later.items() if v >= 0]
            verdict = f"⚠️ 全期為負但後段不一致（{', '.join(pos)} 為正）→ 證據不足，不可據此改門檻"
        else:
            verdict = "該留——全期未為負"
        print(f"  {model} {label:8s}（{r['獨立股票']} 檔獨立股票）：{verdict}")

    os.makedirs(bt.OUT_DIR, exist_ok=True)
    path = os.path.join(bt.OUT_DIR, "discount_bands.csv")
    table.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"\n已寫入 {path}")
    print("要改 schema.sql 的門檻常數，必須是「✅ 該擋」而非「⚠️ 證據不足」。")


if __name__ == "__main__":
    main()
