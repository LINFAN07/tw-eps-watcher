"""
backtest_revenue_growth.py — 「連續 N 個月營收年增為正」訊號回測

回答做榜之前必須先答的問題：**照「營收連續成長」挑股，過去十年贏得了大盤嗎？**

排行榜在本專案等於推薦（`pe_reliable`、`pb_reliable`、`delisted_at` 那些過濾即為此
存在），而「連續 N 月營收年增為正」是一個選股訊號。依既有規矩——高估榜就是這樣
被否決的（`backtest_expensive.py`）——沒有實證支持的訊號不放推薦位。

## 與便宜／昂貴回測共用什麼

母體、除權還原、月末抽樣、`forward_returns`、`universe_returns` 全部沿用
`backtest_valuation.py` 的同一份實作，只換訊號定義。分成兩份實作會在往後任一次
修正時安靜地分岔——這個專案在 `report_window` 與 `decumulate` 兩處付過這個代價。

## 防 look-ahead

某月營收於**次月 10 日前**才公告，站在月末只能用到上上月為止。
故「月 M 的年增率」可用日設為 M+1 的月末交易日，與
`backtest_valuation.revenue_ttm_ps_matrix` 的處理完全一致。

## 為什麼主判準是「同月超額」而不是「贏不贏全市場等權」

營收成長訊號會**擠在景氣擴張的月份**——全市場一起成長時，符合「連續 N 月正成長」
的股票會暴增。拿這些集中在擴張期的訊號去比「橫跨十年所有月份」的母體中位數，
比到的是行情不是選股能力。故每個月算「訊號組中位 − 同月全市場等權中位」，
再取月度超額的中位數。同一個月的兩組吃到完全相同的行情，時點集中就無害了。
（同 `backtest_expensive.py` 的判準，理由相同。）

## 判準（先訂再看，不得看完數字再改）

要做榜，以下四項**全部**要過：

  1. **主判準**：持有 12 個月的同月超額中位數 ≥ +1.5%
     （與昂貴回測的 ≤ −1.5% 對稱，量級取自該次校準）
  2. **持有期一致**：6／12／24 個月三個持有期的同月超額都 > 0
  3. **切點穩定**：三個滾動切點（2021／2022／2023）的**後段**都 > 0
     ——驗「前段看到的東西後段還在不在」
  4. **年代穩定**：三個**互不重疊**的年代窗口都 > 0
     ——滾動切點的後段層層包含（≥2021 ⊇ ≥2022 ⊇ ≥2023），等於同一份資料量三次；
     驗「這是不是只屬於某個年代」一定要用不重疊窗口。
     這一條是 `audit_oos_premium_bands.py` 的教訓，不可省。

另記錄**單調性**（N 越長超額應該越好）作為佐證，但不列為門檻：
N 越長樣本越少，噪音本來就會變大。

## 結論（2026-08-09 首次執行）：**四項全數未通過，不做榜**

同月超額中位（%），母體 2,464 支、122 個月末切點：

| 連續月數 | 平均符合 | 持有 6 個月 | 持有 12 個月 | 持有 24 個月 |
| --- | --- | --- | --- | --- |
| 3 | 554 支（32.4%） | +0.49 | **−0.18** | −2.01 |
| 6 | 325 支（19.0%） | −0.06 | −1.45 | −4.39 |
| 12 | 133 支（7.7%） | +0.32 | −0.85 | −7.19 |

三個持有期的勝過 0050 比率全在 41.8~50.0%，沒有一格贏過擲硬幣。
**持有 24 個月呈現乾淨的反單調**——連續成長越久，之後兩年越差
（−2.01 → −4.39 → −7.19）。持有 6 與 12 個月則毫無型態，
故只能說「沒有正效果」，不宜宣稱「成長越久越糟」是一條規律。

**先確認過不是實作錯**（`紅燈未必是資料錯` 的教訓）：年增率面板與手算逐筆相符、
可用日無 look-ahead（月末 2026-07-31 用的是 2026-06 營收）、
符合比率 32.4%／19.0%／7.7% 量級合理、台積電近 12 個月末選中 11 次。

**也確認過不是下市股造成的**：回測母體含 120 支已標記下市者（4.9%，見下），
排除後主判準由 −0.18% 變成 **−0.38%**——方向對訊號更不利，且差距 0.20pp
遠不足以跨過 +1.5% 的門檻。結論不受此瑕疵影響。

## 已知偏誤（與便宜／昂貴回測同源，但方向不同，不可照抄那邊的說法）

- **倖存者偏差在這裡是雙向的**，不像昂貴回測那樣單向，故不可直接套用那邊的推論：
    · 2026 年初一次性清掉的下市股完全不在母體 → 母體中位被抬高 → 超額被**低估**
    · 現存 120 支已標記下市者仍在母體，價格凍結後報酬近乎 0 → 母體中位被壓低
      → 超額被**高估**（實測此項值 0.20pp，見上）
  兩者相互抵銷，淨方向不明。因此本結論的可信度來自「四項判準全數落空」與
  「所有格子都貼近或低於零」，不是來自單一數字。
- **`backtest_valuation.py` 沒有過濾 `delisted_at`**（檔頭那句「已移除下市股」
  指的是一次性清理，不是持續過濾）。這影響的是**全部**回測，不只本支，
  但修掉會連動改變 `overall.csv`／`by_industry.csv`／`/backtest` 頁與
  `lib/backtestStats.ts` 的線上數字，需另案決定。
- 月採樣近似、無交易成本、樣本自 2016-06 起（月營收需再往前 12 個月建基期）。

## 輸出

backtest_results/revenue_growth_overall.csv    N × 持有期的整體與同月超額
backtest_results/revenue_growth_stability.csv  切點與年代窗口的穩定性

**不覆寫** overall.csv / by_industry.csv / signals.csv / 任何 frontend/lib/*.ts。
"""

import os
import sys

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

import backtest_valuation as bt

STREAKS      = [3, 6, 12]     # 連續正成長的月數
MAIN_STREAK  = 3              # 主判準看哪一個（門檻最低、樣本最多者）
MAIN_HORIZON = 12

EXCESS_FLOOR = 1.5            # 主判準門檻（%）
CUTPOINTS    = ["2021-05-31", "2022-05-31", "2023-05-31"]
ERAS         = 3              # 互不重疊的年代窗口數


def yoy_panel(revenue: pd.DataFrame, dates: list[str]) -> pd.DataFrame:
    """
    月營收年增率面板（列＝回測月末、欄＝股票，單位為倍數不是 %）。

    基期 ≤ 0 一律回 NaN——券商含評價損益、保險含投資損益、建設有退屋沖銷，
    單月為負是真實申報值，此時比率算得出來卻沒有意義（同 /api/revenue 的處理）。
    NaN 會讓該月不計入連續天數，而不是被當成「沒成長」。
    """
    df = revenue.copy()
    df["revenue"] = pd.to_numeric(df["revenue"], errors="coerce")
    df = df.dropna(subset=["revenue"])
    df["ym"] = pd.PeriodIndex(df["year_month"].astype(str).str[:7], freq="M")

    wide = df.pivot_table(index="ym", columns="stock_id", values="revenue", aggfunc="last")
    # 補齊連續月份，缺月留 NaN——不可 ffill，那會把「沒申報」變成「跟上個月一樣」
    wide = wide.reindex(pd.period_range(wide.index.min(), wide.index.max(), freq="M"))

    base = wide.shift(12)
    yoy = (wide / base.where(base > 0)) - 1.0

    # 可用日 = 次月的月末交易日（M→M+1 單射，直接改寫索引）。
    # 與 revenue_ttm_ps_matrix 相同的防 look-ahead 處理。
    date_of_month = {pd.Period(d, freq="M"): d for d in dates}
    yoy.index = pd.to_datetime([date_of_month.get(m + 1) for m in yoy.index])
    yoy = yoy[yoy.index.notna()]
    # 這裡刻意不用 _align_to_month_ends：它會 ffill，把上個月的年增率延用到本月，
    # 於是「連續 N 個月」可能其實是同一個月被數了 N 次。缺月就該中斷連續。
    return yoy.reindex(pd.to_datetime(dates)).set_axis(dates)


def streak_mask(yoy: pd.DataFrame, n: int) -> pd.DataFrame:
    """最近 n 個月都有年增率且都為正"""
    positive = (yoy > 0)                      # NaN > 0 為 False，不會誤算成正成長
    known    = yoy.notna()
    return (positive.rolling(n).sum() == n) & (known.rolling(n).sum() == n)


def monthly_excess(signal: pd.DataFrame, universe: pd.DataFrame, h: int) -> pd.Series:
    """每個月的「訊號組中位 − 同月全市場等權中位」（%）"""
    sig = signal[signal["horizon"] == h].groupby("date")["ret"].median()
    uni = universe[universe["horizon"] == h].groupby("date")["ret"].median()
    return ((sig - uni) * 100).dropna()


def describe(excess: pd.Series) -> dict:
    return {
        "同月超額中位": round(excess.median(), 2) if len(excess) else None,
        "負月比率%":    round((excess < 0).mean() * 100, 1) if len(excess) else None,
        "月數":         len(excess),
    }


def main():
    data = bt.load_all()
    dates = data["dates"]

    print("組裝面板…")
    panels = bt.build_panels(data)
    adj = panels["adj"]
    yoy = yoy_panel(data["revenue"], dates).reindex(columns=adj.columns)
    universe = bt.universe_returns(adj)
    print(f"  月數 {len(dates)}（{dates[0]} ~ {dates[-1]}）、股票 {adj.shape[1]} 支")

    rows, stability, excess_by = [], [], {}
    for n in STREAKS:
        mask = streak_mask(yoy, n)
        print(f"\n連續 {n} 個月正成長：平均每月 {mask.sum(axis=1).mean():.0f} 支符合")
        for h in bt.HORIZONS:
            sig = bt.forward_returns(adj, h, mask=mask)
            if sig.empty:
                continue
            ex = monthly_excess(sig, universe, h)
            excess_by[(n, h)] = ex
            rows.append({
                "連續月數": n, "持有月數": h, "樣本數": len(sig),
                "報酬中位%": round(sig["ret"].median() * 100, 2),
                "勝過0050%": round((sig["ret"] > sig["bench"]).mean() * 100, 1),
                **describe(ex),
            })

    overall = pd.DataFrame(rows)

    # ---- 穩定性：滾動切點（後段）與互不重疊的年代窗口 ----
    main_ex = excess_by.get((MAIN_STREAK, MAIN_HORIZON), pd.Series(dtype=float))
    for cut in CUTPOINTS:
        for label, part in (("前段", main_ex[main_ex.index < cut]),
                            ("後段", main_ex[main_ex.index >= cut])):
            stability.append({"檢驗": f"切點 {cut[:7]}", "區段": label, **describe(part)})

    if len(main_ex):
        bounds = pd.qcut(range(len(main_ex)), ERAS, labels=False)
        for i in range(ERAS):
            part = main_ex[bounds == i]
            era = f"{part.index[0][:7]} ~ {part.index[-1][:7]}" if len(part) else "—"
            stability.append({"檢驗": "不重疊窗口", "區段": era, **describe(part)})

    stab = pd.DataFrame(stability)

    os.makedirs(bt.OUT_DIR, exist_ok=True)
    overall.to_csv(os.path.join(bt.OUT_DIR, "revenue_growth_overall.csv"),
                   index=False, encoding="utf-8-sig")
    stab.to_csv(os.path.join(bt.OUT_DIR, "revenue_growth_stability.csv"),
                index=False, encoding="utf-8-sig")

    pd.set_option("display.unicode.east_asian_width", True, "display.width", 220)
    print("\n=== 整體結果 ===")
    print(overall.to_string(index=False))
    print(f"\n=== 穩定性（連續 {MAIN_STREAK} 月、持有 {MAIN_HORIZON} 個月）===")
    print(stab.to_string(index=False))

    # ---- 判定：條件在檔頭先訂好，由程式印結論，不由人讀數字下判斷 ----
    # （backtest_discount_bands.py 的教訓：只看全期會做出錯誤決定）
    def positive(df, mask):
        vals = df[mask]["同月超額中位"].dropna()
        return len(vals) > 0 and (vals > 0).all()

    main_val = overall.loc[(overall["連續月數"] == MAIN_STREAK)
                           & (overall["持有月數"] == MAIN_HORIZON), "同月超額中位"]
    checks = {
        f"① 持有 12 個月同月超額 ≥ +{EXCESS_FLOOR}%":
            len(main_val) > 0 and main_val.iloc[0] >= EXCESS_FLOOR,
        "② 三個持有期的同月超額都 > 0":
            positive(overall, overall["連續月數"] == MAIN_STREAK),
        "③ 三個滾動切點的後段都 > 0":
            positive(stab, (stab["檢驗"].str.startswith("切點")) & (stab["區段"] == "後段")),
        "④ 三個不重疊年代窗口都 > 0":
            positive(stab, stab["檢驗"] == "不重疊窗口"),
    }
    print("\n=== 判定（判準寫在檔頭，先訂再看）===")
    for label, ok in checks.items():
        print(f"  {'✓' if ok else '✗'} {label}")
    passed = all(checks.values())
    print(f"\n結論：{'通過 → 可以做榜' if passed else '未通過 → 不做榜'}"
          f"（{sum(checks.values())}/{len(checks)} 項）")
    print("\n提醒：母體不含已下市股票，各組報酬都被抬高；未計交易成本。"
          "故「明顯較好」要打折看，「沒特別好」則可信。")


if __name__ == "__main__":
    main()
