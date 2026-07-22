"""
排程稽核：確認每支腳本都真的會被執行，而不是「寫好了卻沒掛上」。

這個專案踩過兩次同型的坑：
  1. 品質指標重算腳本沒進 workflow，畫面長期顯示舊值
  2. patch_nonop_warning.py 從未被排程，業外收支警告自一次性回填後就沒再更新，
     而排行榜正依該欄位排除股票（2026-07-21 發現並補掛）

這類缺陷不會報錯、沒有任何症狀，只會讓資料悄悄停在過去，
唯一能發現它的方法就是主動比對「有哪些腳本」與「排程實際跑哪些腳本」。

發現問題時 exit 1，由 workflow 的失敗通知寄信。
"""

import re
import sys
from pathlib import Path

import yaml

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

ROOT = Path(__file__).resolve().parent.parent
WF_DIR = ROOT / ".github" / "workflows"

# 不需掛排程的腳本，每一項都要能說出理由。
# 新增腳本時若忘了掛排程，這裡沒列到就會被抓出來——這正是本稽核的目的，
# 所以請勿為了讓稽核通過而隨手把新腳本加進白名單。
NO_SCHEDULE_OK = {
    # 一次性初始化（新環境才跑）
    "init_download.py":               "新環境初始化，跑一次",
    "backfill_industry.py":           "一次性補產業別",
    "backfill_eps_from_income.py":    "由 quarterly_eps.yml 條件式呼叫",
    "backfill_last_seen.py":          "一次性回填 last_seen_date；日常維護由 daily_price_update.mark_delisted 負責",
    "patch_par_value.py":             "一次性修正面額寫死造成的每股淨值與股數錯誤；日常由 download_balance_sheet.py 用正確面額寫入",
    # 共用模組，非可執行工作
    "finmind_client.py":              "共用模組",
    "price_adjust.py":                "共用純函式模組",
    # 手動維運工具
    "cleanup_inactive_stocks.py":     "手動清理下市股",
    "backtest_valuation.py":          "回測，需要時手動跑",
    "test_download.py":               "開發測試用",
    # 已被取代的舊 patch 腳本（欄位改由下列腳本產生，依「不刪既有死碼」原則保留）
    "patch_low_eps_warning.py":       "warning 欄位已由 calculate_valuation.py 產生",
    "patch_peak_eps_warning.py":      "warning 欄位已由 calculate_valuation.py 產生",
    "patch_yield_valuation.py":       "yield_* 欄位已由 calculate_alt_valuations.py 產生",
    # 被其他腳本內部呼叫，不會出現在 workflow 的 `python xxx.py`
    "download_monthly_revenue.py":    "由 update_fundamentals.py 內部呼叫",
}
# 注意：已經掛在 workflow 上的腳本【不要】列進上面的白名單。
# 白名單只列「本來就不該有排程」的；若把已排程的也列進去，
# 未來它被移出排程時稽核會保持沉默，等於在保險絲上並聯一條銅線。


def scripts_in(text: str) -> list[str]:
    """
    抓出 workflow 實際執行的腳本。兩種寫法都要涵蓋：
    `python scripts/x.py`，以及搭配 `working-directory: scripts` 的 `python x.py`
    （quarterly_eps.yml 用後者；只比對前者會誤判它「不執行任何腳本」）。
    """
    return re.findall(r"python\s+(?:scripts/)?([\w_]+\.py)", text)


def main() -> int:
    scheduled: dict[str, list[str]] = {}
    problems: list[str] = []

    for wf in sorted(WF_DIR.glob("*.yml")):
        text = wf.read_text(encoding="utf-8")
        try:
            doc = yaml.safe_load(text)
        except yaml.YAMLError as e:
            # 語法錯的 workflow 會被 GitHub 靜默忽略，不會有任何通知
            problems.append(f"{wf.name}: YAML 無法解析 — {e}")
            continue

        # PyYAML 會把 YAML 的 on: 當成布林 True，這是有名的坑
        triggers = doc.get("on", doc.get(True, {})) or {}
        crons = [s.get("cron") for s in (triggers.get("schedule") or [])]
        has_dispatch = "workflow_dispatch" in triggers
        found = scripts_in(text)

        for s in found:
            scheduled.setdefault(s, []).append(wf.name)

        print(f"{wf.name}: cron={crons or '無'} 手動={'有' if has_dispatch else '無'} "
              f"腳本={', '.join(found) or '無'}")

        if not crons and not has_dispatch:
            problems.append(f"{wf.name}: 既無 cron 也無 workflow_dispatch，永遠不會執行")
        for c in crons:
            if len((c or "").split()) != 5:
                problems.append(f"{wf.name}: cron '{c}' 欄位數不是 5")
        for s in found:
            if not (ROOT / "scripts" / s).exists():
                problems.append(f"{wf.name}: 引用了不存在的腳本 {s}")
        if found and "SUPABASE_URL" not in text:
            problems.append(f"{wf.name}: 執行腳本但未帶 SUPABASE_URL")
        if "if: failure()" not in text:
            problems.append(f"{wf.name}: 缺少失敗通知（if: failure()），失敗會靜默")

    orphans = [p.name for p in sorted((ROOT / "scripts").glob("*.py"))
               if p.name not in scheduled and p.name not in NO_SCHEDULE_OK]
    for name in orphans:
        problems.append(f"{name}: 沒有被任何 workflow 執行，且不在豁免清單——"
                        f"若它負責維護某個資料欄位，該欄位將永遠停在最後一次手動執行的值")

    print(f"\n已掛排程 {len(scheduled)} 支、豁免 {len(NO_SCHEDULE_OK)} 支、"
          f"孤兒 {len(orphans)} 支")

    if problems:
        print("\n❌ 排程稽核發現問題：")
        for p in problems:
            print(f"  - {p}")
        return 1

    print("✅ 排程稽核通過")
    return 0


if __name__ == "__main__":
    sys.exit(main())
