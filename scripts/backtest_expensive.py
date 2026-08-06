"""
backtest_expensive.py — 「昂貴」訊號回測（高估榜的 go/no-go 依據）

回答一個從未驗證過的問題：「照這個網站的『昂貴』訊號，過去十年該不該賣？」

`backtest_valuation.py` 只跑了 PCT_CHEAP=0.20 的多方，昂貴那一端完全沒驗過。
依「沒有實證支持的訊號不放推薦位」原則，高估榜要成立，必須先過這一關。

## 與便宜回測的唯一差異

訊號判定共用 `bt.percentile_mask()`，只換分位數（0.20 → 0.80）與方向
（`side='cheap'` → `'expensive'`）。其餘管線（防 look-ahead 的三道關卡、
除權還原、股數因子、半年報 TTM 期數判定）全部沿用同一份實作。

## 為什麼不能只看「昂貴組中位報酬 vs 全市場等權」

**昂貴訊號會擠在多頭月份**——價格創新高時，大多數股票自然坐在自己歷史
第 80 百分位之上（2026-08 實測：全市場 49% 被判昂貴）。拿這些集中在多頭的
訊號去比「橫跨十年所有月份」的母體中位數，比到的是行情不是選股能力，
而且方向對高估榜有利（多頭起漲點的樣本會拉高昂貴組報酬，看起來「昂貴也沒差」）。

故主要判準改用**同月對照**：每個月算「昂貴組中位報酬 − 同月全市場等權中位報酬」，
再取這些月度超額的中位數。同一個月的兩組吃到完全相同的行情，時點集中就無害了。
（`pe_deep_discount` 的門檻當初也是用「逐月中位數的中位」定的，作法一致。）

## 已知偏誤（方向對高估榜特別不利，不可略過）

- **倖存者偏差是單向的**：母體只含活到今天的公司（已移除約 198 檔下市股），
  而下市股多半是崩跌的。移除它們會抬高每一組的報酬，昂貴組尤甚。
  因此結論只能單向採信：
    · 昂貴組明顯較差 → 可信（真實情況只會更差）
    · 昂貴組沒特別差 → **不能**據此斷定訊號無效，也不能據此斷定它安全
- 其餘偏誤（月採樣近似、無交易成本、樣本自 2016-06 起）同 backtest_valuation.py。

## 結論（2026-08-06 首次執行）

**沒過。** P/E 昂貴持有 12 個月的同月超額是 **+1.86%**（門檻訂在 ≤ −1.5%），
12 個格子（4 模型 × 3 持有期）只有 P/B 24 個月是負的。被判昂貴的股票
接下來一年有近七成月份贏過大盤——那是動能，不是該賣的訊號。
唯一為負的是「溢價 2~3 倍」那一層（−3.64%、71% 月份為負），但不單調
（>3 倍回到 −1.44%）且屬事後翻找，要用需先做樣本外檢驗。

## 輸出

backtest_results/expensive_overall.csv  四模型 × 三持有期的整體與同月超額
backtest_results/expensive_bands.csv    P/E 溢價分層（檢查分母趨零的算術假象）

**不覆寫** overall.csv / by_industry.csv / frontend/lib/backtestStats.ts。
"""

import os
import sys
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

import backtest_valuation as bt

PCT_EXPENSIVE = 0.80    # 昂貴 = 歷史倍數第 80 百分位（與 calculate_valuation.py 一致）
MAIN_HORIZON  = 12      # 分層分析的持有月數

# 溢價（現價 ÷ 昂貴價）分層的邊界。audit_oos_premium_bands.py 也用這一份——
# 兩邊若各持一份，樣本外檢驗驗的就不是這裡報出來的那個帶。
PREMIUM_BANDS = [("溢價 1.0~1.5 倍", 1.0, 1.5), ("溢價 1.5~2 倍", 1.5, 2.0),
                 ("溢價 2~3 倍", 2.0, 3.0), ("溢價 >3 倍", 3.0, float("inf"))]


def excess_stats(sub: pd.DataFrame, uni_m: pd.Series) -> dict:
    """
    同月對照的核心統計（理由見模組說明）：訊號組與母體逐月相減再取中位數。

    uni_m = 該持有期的「每月全市場等權中位報酬」，由呼叫端算好傳入
    （它只隨 horizon 變化，與是哪個模型無關，不該每組重算）。
    """
    excess = (sub.groupby("date")["ret"].median() - uni_m).dropna()
    return {
        "樣本數":       len(sub),
        "訊號月數":     len(excess),
        "報酬中位數%":  round(sub["ret"].median() * 100, 2),
        "同月超額%":    round(excess.median() * 100, 2),      # ← 主要判準
        "超額為負月%":  round((excess < 0).mean() * 100, 1),  # 一致性：多少比例的月份確實較差
        "最慘10%報酬%": round(sub["ret"].quantile(0.10) * 100, 2),
        "_excess":      excess,   # 供呼叫端補算欄位，輸出前會移除
    }


def stats(df: pd.DataFrame, uni_m: pd.Series, label: str, horizon: int) -> dict | None:
    """單一模型 × 單一持有期的完整統計：同月超額 + 下檔風險。"""
    d = df[df["horizon"] == horizon]
    if d.empty:
        return None

    core = excess_stats(d, uni_m)
    excess, r = core.pop("_excess"), d["ret"]
    return {
        "組別":          label,
        "horizon":       horizon,
        **core,
        "同月母體中位%": round(uni_m.reindex(excess.index).median() * 100, 2),
        "正報酬率%":     round((r > 0).mean() * 100, 1),
        "勝過0050%":     round((d["ret"] > d["bench"]).mean() * 100, 1),
        "賠逾30%":       round((r < -0.30).mean() * 100, 1),
    }


def premium_bands(df: pd.DataFrame, premium: pd.DataFrame, base: pd.DataFrame,
                  uni_m: pd.Series) -> pd.DataFrame:
    """
    P/E 昂貴訊號按「溢價倍數」與「TTM EPS 絕對水準」分層。

    溢價倍數 = 現價 ÷ 昂貴價，訊號成立時必 ≥1，數字越大代表現價離昂貴價越遠。
    這個比值極大時，多半不是「漲得很貴」而是**分母趨近於零**：2026-08-06 實測
    1516 川飛 TTM EPS 僅 0.01 元，昂貴價因此算成 0.37 元、溢價 42.7 倍。
    它是 `pe_deep_discount` 的鏡像，但生產端沒有對應旗標——分層就是要決定該不該補。

    兩個問題一次回答：
      1. 溢價越高是不是越該賣？（若高溢價組報酬反而不差 → 算術假象不是訊號）
      2. 把 TTM EPS 趨近零的股票剔掉，訊號會不會變乾淨？

    df 為呼叫端已算好的 MAIN_HORIZON 長表，不重跑 forward_returns。
    """
    df = df.copy()
    idx = pd.MultiIndex.from_arrays([df["date"], df["stock_id"]])
    df["premium"] = idx.map(premium.stack())
    df["ttm_eps"] = idx.map(base.stack())
    df = df.dropna(subset=["premium"])

    def row(sub: pd.DataFrame, label: str) -> dict | None:
        if len(sub) < 30:
            return None
        core = excess_stats(sub, uni_m)
        core.pop("_excess")
        return {"分層": label, **core}

    rows = [row(df[(df["premium"] >= lo) & (df["premium"] < hi)], name)
            for name, lo, hi in PREMIUM_BANDS]
    # EPS 絕對水準：0.5 元是 calculate_valuation 判「EPS 長期偏低」的同一條線
    rows += [row(df[df["ttm_eps"] < 0.5], "（敏感度）TTM EPS < 0.5 元"),
             row(df[df["ttm_eps"] >= 0.5], "（敏感度）TTM EPS ≥ 0.5 元")]
    return pd.DataFrame([r for r in rows if r])


def main():
    data = bt.load_all()
    dates = data["dates"]

    print("組裝面板…")
    panels = bt.build_panels(data)
    adj = panels["adj"]
    print(f"  月數 {len(dates)}（{dates[0]} ~ {dates[-1]}）、股票 {adj.shape[1]} 支")

    uni = bt.universe_returns(adj)
    # 每月母體中位數只隨 horizon 變化，先算好三份供所有模型共用
    uni_median = {h: uni[uni["horizon"] == h].groupby("date")["ret"].median()
                  for h in bt.HORIZONS}

    print("回測中…")
    models = [
        ("P/E",   panels["eps_ttm"], bt.PE_MIN,   bt.PE_MAX),
        ("P/B",   panels["bvps"],    bt.PB_MIN,   bt.PB_MAX),
        ("P/S",   panels["ps"],      bt.PS_MIN,   bt.PS_MAX),
        ("P/FCF", panels["pfcf"],    bt.PFCF_MIN, bt.PFCF_MAX),
    ]
    rows, bands = [], pd.DataFrame()
    for name, base, lo, hi in models:
        mask, premium = bt.percentile_mask(adj, base, lo, hi, PCT_EXPENSIVE, "expensive")
        df = pd.concat([bt.forward_returns(adj, h, mask) for h in bt.HORIZONS],
                       ignore_index=True)
        if df.empty:
            print(f"  {name} 昂貴：無訊號")
            continue
        rows += [s for h in bt.HORIZONS
                 if (s := stats(df, uni_median[h], f"{name} 昂貴", h))]
        print(f"  {name} 昂貴：{len(df)} 筆訊號-報酬對")
        if name == "P/E":
            bands = premium_bands(df[df["horizon"] == MAIN_HORIZON], premium, base,
                                  uni_median[MAIN_HORIZON])

    overall = pd.DataFrame(rows)
    os.makedirs(bt.OUT_DIR, exist_ok=True)
    overall.to_csv(os.path.join(bt.OUT_DIR, "expensive_overall.csv"),
                   index=False, encoding="utf-8-sig")
    if not bands.empty:
        bands.to_csv(os.path.join(bt.OUT_DIR, "expensive_bands.csv"),
                     index=False, encoding="utf-8-sig")

    pd.set_option("display.unicode.east_asian_width", True, "display.width", 250)
    print("\n=== 昂貴訊號整體結果（報酬單位 %）===")
    print("主要判準是「同月超額%」：負得夠多才代表『昂貴』真的該賣")
    print(overall.to_string(index=False))
    if not bands.empty:
        print(f"\n=== P/E 昂貴：溢價分層（持有 {MAIN_HORIZON} 個月，樣本 ≥30）===")
        print(bands.to_string(index=False))
    print(f"\n結果已寫入 {bt.OUT_DIR}（未覆寫便宜回測的檔案）")
    print("提醒：母體不含已下市股票，昂貴組報酬被系統性高估；結論只能單向採信。")


if __name__ == "__main__":
    main()
