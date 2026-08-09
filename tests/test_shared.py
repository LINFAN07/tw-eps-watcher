"""
Python 端的共用案例驗證（另有 tests/test_shared.ts 讀同一份 JSON）。

為什麼要有這支：`price_adjust.back_adjust` 與 `frontend/lib/priceAdjust.ts`
的 backAdjust、`periodicity.report_window` 與 `frontend/lib/periodicity.ts`
的 reportWindow，都是同一套規則的兩份實作。檔頭寫著「兩邊必須同步修改」，
但 2026-07-22 一天之內就漂移了三次：

  - 期數判定跑出 6 期／8 期／全歷史三種答案
  - P/FCF 的視窗停在 8 期，註解卻宣稱與 P/E 一致
  - 稽核用 `months > {6,12}` 想表達「不是子集」，實際是真超集，判反了

人工逐行比對只能證明「比對的那一次」一致。兩邊讀同一份 fixture，
任一邊改壞就會有一邊紅。

跑法：python tests/test_shared.py
（不需 pytest，也不連資料庫——這裡驗的是純函式）
"""

import json
import os
import sys

# Windows 主控台預設 cp950，印 ✓／✗ 會炸（專案其他腳本一律先做這件事）
sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from price_adjust import back_adjust          # noqa: E402
from periodicity import (available_date, report_window,               # noqa: E402
                         ttm_month_window, ttm_periods)

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "shared_cases.json")
TOLERANCE = 0.01


def main() -> int:
    with open(FIXTURE, encoding="utf-8") as f:
        cases = json.load(f)

    failures = []

    print("=== back_adjust ===")
    for c in cases["back_adjust"]:
        ex_list = [(d, cash, stock) for d, cash, stock in c["ex_list"]]
        got = back_adjust(c["dates"], c["closes"], ex_list, c["official"])[0]
        ok = abs(got - c["expect_first"]) <= TOLERANCE
        print(f"  {'✓' if ok else '✗'} {c['name']}")
        if not ok:
            print(f"      得到 {got:.4f}，預期 {c['expect_first']}（{c['source']}）")
            failures.append(c["name"])

    print("\n=== report_window ===")
    for c in cases["report_window"]:
        got = report_window(c["quarter_ends"])
        ok = got == c["expect"]
        print(f"  {'✓' if ok else '✗'} {c['name']}")
        if not ok:
            print(f"      得到 {got}，預期 {c['expect']}（{c['source']}）")
            failures.append(c["name"])

    # ttm_periods 是 report_window 的下一層：後者只答「一年幾期」，
    # 答不了「哪幾期剛好 12 個月」。2026-08-06 修了 Python、漏了 TypeScript，
    # 43 支股票的河流圖因此用錯 TTM 三天無人察覺——這一段就是為此存在。
    print("\n=== ttm_periods ===")
    for c in cases["ttm_periods"]:
        got = ttm_periods(c["period_ends"])
        ok = got == c["expect"]
        print(f"  {'✓' if ok else '✗'} {c['name']}")
        if not ok:
            print(f"      得到 {got}，預期 {c['expect']}（{c['source']}）")
            failures.append(c["name"])

    print("\n=== ttm_month_window ===")
    for c in cases["ttm_month_window"]:
        got = ttm_month_window(c["available"], c["end_month"])
        ok = got == c["expect"]
        print(f"  {'✓' if ok else '✗'} {c['name']}")
        if not ok:
            print(f"      得到 {got}，預期 {c['expect']}（{c['source']}）")
            failures.append(c["name"])

    # 申報期限：兩邊給不同答案時，回測與訊號回放會對「那天算不算便宜」不一致
    print("\n=== available_date ===")
    for c in cases["available_date"]:
        got = available_date(c["period_end"])
        ok = got == c["expect"]
        print(f"  {'✓' if ok else '✗'} {c['name']}")
        if not ok:
            print(f"      得到 {got}，預期 {c['expect']}（{c['source']}）")
            failures.append(c["name"])

    total = sum(len(cases[k]) for k in
                ("back_adjust", "report_window", "ttm_periods", "ttm_month_window",
                 "available_date"))
    print(f"\n{total - len(failures)}/{total} 通過")
    if failures:
        print("失敗：" + "、".join(failures))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
