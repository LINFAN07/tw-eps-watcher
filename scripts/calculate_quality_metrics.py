"""
品質指標計算腳本（TTM 營業利益率）
載入 income_statement_quarterly + monthly_revenue，
計算 TTM 營業利益率（%），寫入 valuations.operating_margin。

計算邏輯：
  期別         = periodicity.ttm_periods()（剛好涵蓋 12 個月的那幾期）
  TTM 營業利益 = 那幾期的 operating_income 加總（元）
  TTM 營收     = 同一段 12 個月的 monthly_revenue 加總（元）
  營業利益率   = TTM 營業利益 / TTM 營收 × 100

分子分母必須同期同長度，這是本腳本兩次事故的共同根源：

  - 分母曾借用 valuations.ps_revenue_per_share（P/S 模型的基準值）。那個欄位
    只在 P/S 算得出來時才有值，而 P/S 需要 12 個歷史點＝至少 23 個月營收。
    利益率本身只需要 12 個月，卻被 P/S 的歷史長度門檻連坐：132 檔資料齊全的
    公司（幾乎全是近兩年新上市）利益率是 null，其中 23 檔正掛在便宜狀態。
    實例 6955 邦睿生技，真實利益率 32.1%，畫面上顯示「—」。
  - 期數曾硬寫 4，沒問 periodicity。半年報公司只揭露 6/30 與 12/31，
    取 4 期等於把兩年營業利益除以一年營收，利益率高估一倍
    （同 CLAUDE.md 記載的 ttm_eps 事故，這裡是第五份自己另寫的實作）。
  - 改問 periodicity 之後，一度是問「頻率標籤」再自己往回數 w 期。那仍答不了
    揭露頻率改變的公司（2026-08-06，39 檔半年報轉季報），已改問 ttm_periods()
    直接拿「剛好 12 個月」的期別清單。分母的月份視窗必須跟著它的結尾走，
    不能各自錨在「最新」——ttm_periods 會為轉換期公司退回上一組完整 12 個月。

用法：
  python scripts/calculate_quality_metrics.py
"""

import os
import sys
import pandas as pd
from dotenv import load_dotenv
from supabase import create_client

from periodicity import ttm_periods, ttm_month_window   # TTM 視窗的單一來源

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))


def _fetch_paged(table: str, columns: str) -> list:
    """分頁取得 Supabase 資料（繞過 1000 筆上限）"""
    all_rows, offset = [], 0
    while True:
        resp = (supabase.table(table).select(columns)
                .order("stock_id").range(offset, offset + 999).execute())
        all_rows.extend(resp.data or [])
        if len(resp.data or []) < 1000:
            break
        offset += 1000
    return all_rows


def main():
    # ── 1. 載入損益表與月營收
    print("載入 income_statement_quarterly...")
    income_df = pd.DataFrame(_fetch_paged(
        "income_statement_quarterly", "stock_id,quarter_end_date,operating_income"))
    income_df["operating_income"] = pd.to_numeric(income_df["operating_income"], errors="coerce")
    income_df = income_df.dropna(subset=["operating_income"])
    print(f"  → {len(income_df)} 筆")

    print("載入 monthly_revenue...")
    rev_df = pd.DataFrame(_fetch_paged("monthly_revenue", "stock_id,year_month,revenue"))
    rev_df["revenue"] = pd.to_numeric(rev_df["revenue"], errors="coerce")
    rev_df = rev_df.dropna(subset=["revenue"])
    # year_month 存成 YYYY-MM-01，比對只用到年月
    rev_map: dict[str, dict[str, float]] = {}
    for sid, grp in rev_df.groupby("stock_id"):
        rev_map[sid] = dict(zip(grp["year_month"].str[:7], grp["revenue"].astype(float)))
    print(f"  → {len(rev_df)} 筆、{len(rev_map)} 支股票有月營收")

    # ── 2. 逐支計算
    print("計算 TTM 營業利益率...")
    results: dict[str, float] = {}
    skipped = {"期別有洞": 0, "無月營收": 0, "營收缺月": 0, "營收非正": 0}

    for stock_id, grp in income_df.groupby("stock_id"):
        ends = ttm_periods(grp["quarter_end_date"])
        if ends is None:
            skipped["期別有洞"] += 1
            continue
        ttm_op = float(grp[grp["quarter_end_date"].isin(ends)]["operating_income"].sum())

        months = rev_map.get(stock_id)
        if not months:
            skipped["無月營收"] += 1          # 多為金融股：無月營收申報義務
            continue
        # 分母必須跟著分子的視窗走：ttm_periods 可能退回上一組完整 12 個月
        # （轉換頻率的公司），營收若仍錨在「最新月份」就會與分子錯開
        window = ttm_month_window(months, ends[-1][:7])
        if window is None:
            skipped["營收缺月"] += 1
            continue
        ttm_rev = sum(months[m] for m in window)
        if ttm_rev <= 0:
            skipped["營收非正"] += 1
            continue

        # 保留真實比率，不 clamp、也不因超出範圍寫 null。
        #
        # 原本 clamp 到 ±999.99 以避開 DECIMAL(6,2) 溢位，但邊界值是【假數字】——
        # 使用者看到「-999.99%」會當成真實比率讀，實際上 6467 是 -18,375%。
        #
        # 曾考慮改寫 null，實測後否決：有 75 支比率 < -100%，其中 39 支 ROE ≥0
        # （本業大虧、靠業外撐住帳面獲利），排行榜正是靠「利益率 < 1」把它們擋掉。
        # 寫 null 會讓其中 14 支便宜股漏進榜單——那是最該被警示的類型。
        # 故改為放寬欄位（DECIMAL(10,2)）容納真實值，極端值的可讀性由前端處理。
        results[stock_id] = round(ttm_op / ttm_rev * 100, 2)

    extreme = sum(1 for v in results.values() if abs(v) > 100)
    print(f"  → 有效結果：{len(results)} 支（其中 {extreme} 支比率絕對值 >100%，"
          f"營收極小、本業大幅虧損，數值為真實值不做截斷）")
    print(f"  → 未計算：{skipped}")

    # ── 3. 寫入。算不出來的要主動寫回 null，否則舊值會永久殘留且再無機制修正
    #    （資料誠信原則第 4 條）。只寫真正變動的列，省下整批無謂的 UPDATE。
    print("寫入 valuations.operating_margin...")
    current = {r["stock_id"]: None if r["operating_margin"] is None else float(r["operating_margin"])
               for r in _fetch_paged("valuations", "stock_id,operating_margin")}
    changes = {sid: results.get(sid) for sid, old in current.items() if old != results.get(sid)}
    cleared = sum(1 for v in changes.values() if v is None)

    for i, (sid, margin) in enumerate(changes.items(), 1):
        supabase.table("valuations").update({"operating_margin": margin}).eq("stock_id", sid).execute()
        if i % 200 == 0:
            print(f"  已寫入 {i}/{len(changes)}")

    print(f"完成！{len(changes)} 支更新（其中 {cleared} 支寫回 null），"
          f"{len(current) - len(changes)} 支數值未變動未重寫")


if __name__ == "__main__":
    main()
