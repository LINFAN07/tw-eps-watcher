"""
export_quality_stats.py — 產生 frontend/lib/backtestQualityStats.ts（Q4 品質濾網 + Q5 徽章）

## 為什麼要有這支

badges / roe_filter / margin_filter / filter_compare 四支回測與主回測
（backtest_valuation.py）分開、且都手動跑，很容易「只重跑一部分」造成數字漂移
——這正是「品質指標重算漏掛排程」踩過的坑。這支把三件事綁成單一指令：

    四支一起跑（子行程，任一失敗 check=True 即整支失敗）
      ↓
    一致性把關（badges 的「便宜全體」必須逐位元組等於 overall.csv 的 P/E 便宜 12m）
      ↓
    匯出 frontend/lib/backtestQualityStats.ts

只要有人重跑了主回測卻沒重跑這四支（或反之），把關就會失敗、不會產出半新半舊的 lib。
前端也保留一道 QUALITY_BASELINE 檢查（見 backtestQualityStats.ts），兩邊 lib 若失
同步就自動隱藏 Q4/Q5，寧可不顯示也不給錯數字。

重跑：`python scripts/export_quality_stats.py`
快速重匯（不重跑回測、直接用現有 CSV）：加 `--no-run`
"""

import argparse
import json
import os
import subprocess
import sys

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

import backtest_valuation as bt  # 只借用 OUT_DIR，確保與主回測輸出同一個資料夾

HERE = os.path.dirname(__file__)
LIB = os.path.join(HERE, "..", "frontend", "lib", "backtestQualityStats.ts")

# 四支回測腳本，依相依順序（badges 需要 margin 的營收工具，但各自獨立可跑）
SCRIPTS = ["backtest_roe_filter.py", "backtest_margin_filter.py",
           "backtest_badges.py", "backtest_filter_compare.py"]

# CSV 中文欄名 → 前端欄名（badges/roe/margin 用「組別」，filter_compare 用「版本」）
COLMAP = {
    "組別": "group", "版本": "group", "樣本數": "n",
    "報酬中位數%": "median", "報酬平均%": "mean", "正報酬率%": "positiveRate",
    "勝過0050%": "winRate", "最慘10%報酬%": "worst10", "賠逾30%": "loss30", "賠逾50%": "loss50",
}
COLS = ["group", "n", "median", "mean", "positiveRate", "winRate", "worst10", "loss30", "loss50"]


def run_all() -> None:
    """依序跑四支回測；任一非零退出即中止整個匯出（不容忍半套資料）"""
    for s in SCRIPTS:
        print(f"▶ 跑 {s} …")
        subprocess.run([sys.executable, os.path.join(HERE, s)], check=True)


def load(name: str) -> pd.DataFrame:
    df = pd.read_csv(os.path.join(bt.OUT_DIR, name), encoding="utf-8-sig").rename(columns=COLMAP)
    df["group"] = df["group"].str.strip()   # filter_compare 有縮排／樹狀符號，去掉前導空白
    return df[COLS]


def overall_pe12() -> tuple[int, float]:
    """主回測的 P/E 便宜 12 個月基準，作為一致性把關的錨點"""
    ov = pd.read_csv(os.path.join(bt.OUT_DIR, "overall.csv"), encoding="utf-8-sig")
    row = ov[(ov["組別"] == "P/E 便宜") & (ov["horizon"] == 12)].iloc[0]
    return int(row["樣本數"]), float(row["報酬中位數"])


def guard(badges: pd.DataFrame, base_n: int, base_med: float) -> None:
    """
    badges 的「便宜全體」用的是與主回測完全相同的便宜遮罩、無額外資料篩選，
    故其 (n, 中位) 必須等於 overall 的 P/E 便宜 12m。不等 → 兩者不同步 → 整支失敗。
    """
    b = badges[badges["group"] == "便宜全體"].iloc[0]
    if int(b["n"]) != base_n or abs(float(b["median"]) - base_med) > 1e-6:
        raise SystemExit(
            f"❌ 一致性把關失敗：badges 便宜全體 (n={int(b['n'])}, 中位={b['median']}%) "
            f"≠ overall P/E 便宜 12m (n={base_n}, 中位={base_med}%)。\n"
            "   代表徽章/濾網回測與主回測不同步，請先 `python scripts/backtest_valuation.py` "
            "再重跑本腳本。")


def rows_json(df: pd.DataFrame) -> str:
    return ",\n".join("  " + json.dumps(r, ensure_ascii=False) for r in df.to_dict("records"))


def export(badges, roe, margin, cmp_, base_n: int, base_med: float) -> None:
    ts = f"""// 由 scripts/export_quality_stats.py 產生，請勿手動編輯。
// Q4 品質濾網 + Q5 徽章的回測結果。重跑會覆寫此檔。
// 重跑：python scripts/export_quality_stats.py（會一起跑四支回測並做一致性把關）。

export interface QualityRow {{
  group: string; n: number; median: number; mean: number
  positiveRate: number; winRate: number; worst10: number; loss30: number; loss50: number
}}

/**
 * 便宜全體基準，等於 backtestStats.OVERALL 的「P/E 便宜」12 個月。
 * 前端以此對照兩份 lib 是否同步（見 lib/qualityBacktest.ts 的 isQualityInSync）——
 * 不同步時隱藏 Q4/Q5，寧可不顯示也不給過時數字。
 */
export const QUALITY_BASELINE = {{ n: {base_n}, median: {base_med} }}
export const QUALITY_HORIZON = 12

export const BADGES: QualityRow[] = [
{rows_json(badges)}
]

export const ROE_FILTER: QualityRow[] = [
{rows_json(roe)}
]

export const MARGIN_FILTER: QualityRow[] = [
{rows_json(margin)}
]

export const FILTER_COMPARE: QualityRow[] = [
{rows_json(cmp_)}
]
"""
    with open(LIB, "w", encoding="utf-8") as f:
        f.write(ts)
    print(f"前端統計檔已更新：{os.path.normpath(LIB)}")


def main() -> None:
    ap = argparse.ArgumentParser(description="匯出品質濾網/徽章回測到前端 lib")
    ap.add_argument("--no-run", action="store_true",
                    help="不重跑四支回測，直接用現有 CSV 匯出（僅供快速重匯，正式更新請勿用）")
    args = ap.parse_args()

    if not args.no_run:
        run_all()

    base_n, base_med = overall_pe12()
    badges = load("badges.csv")
    roe    = load("roe_filter.csv")
    margin = load("margin_filter.csv")
    cmp_   = load("filter_compare.csv")

    guard(badges, base_n, base_med)
    export(badges, roe, margin, cmp_, base_n, base_med)
    print(f"✓ 基準一致：便宜全體 n={base_n}, 中位={base_med}%")


if __name__ == "__main__":
    main()
