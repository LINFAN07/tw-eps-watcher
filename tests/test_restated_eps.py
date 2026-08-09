"""
更正申報回補的分類邏輯驗證（純函式，不連資料庫、不呼叫 FinMind）。

為什麼要有這支：`refetch_restated_eps.py` 要在三種長得很像的情形之間做出
不同處置，判斷錯了不會報錯，只會安靜地寫錯資料或安靜地不寫：

  - 既有季度的值變了      → 更正申報，寫回
  - FinMind 說的跟我們一樣 → 來源分歧，**不可**寫（否則同一條序列混兩個來源）
  - 資料庫還沒有這一季    → 新季度，歸 quarterly_eps_update.py 管，這支不碰

第三項靠一個容易被改掉的小技巧達成：取不到既有值時**以自身為預設**，
差為 0 所以不會被當成更正。有人把它改成 `existing.get(key, 0)` 就會讓每一季
新資料都被記成「更正」，而畫面與日誌看起來完全正常。

跑法：python tests/test_restated_eps.py
"""

import os
import sys

# Windows 主控台預設 cp950，印 ✓／✗ 會炸（專案其他腳本一律先做這件事）
sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from refetch_restated_eps import candidates, restatements   # noqa: E402


def q(sid, date, eps):
    return {"stock_id": sid, "quarter_end_date": date, "eps": eps}


# (情境, FinMind 回傳, 資料庫既有, 預期被判為更正的季別)
CASES = [
    (
        "更正申報：既有季度的值變了（1591 的真實情形）",
        [q("1591", "2026-03-31", -1.18)],
        {("1591", "2026-03-31"): -0.08},
        ["2026-03-31"],
    ),
    (
        "來源分歧：FinMind 與我們一致（3521 的真實情形）",
        [q("3521", "2026-03-31", 2.12), q("3521", "2026-06-30", -0.02)],
        {("3521", "2026-03-31"): 2.12, ("3521", "2026-06-30"): -0.02},
        [],
    ),
    (
        "新季度不算更正：資料庫沒有這一季，歸 quarterly_eps_update 管",
        [q("2330", "2026-06-30", 15.0)],
        {},
        [],
    ),
    (
        "只挑真正變了的那一季，同批其餘不動",
        [q("9999", "2026-03-31", 1.00), q("9999", "2026-06-30", 2.50)],
        {("9999", "2026-03-31"): 1.00, ("9999", "2026-06-30"): 1.20},
        ["2026-06-30"],
    ),
    (
        "小於容差的差異不算更正（EPS 只揭露到小數點後兩位）",
        [q("9999", "2026-03-31", 1.001)],
        {("9999", "2026-03-31"): 1.00},
        [],
    ),
    (
        "跨過容差就算（0.01 是 EPS 的最小揭露單位，必須抓得到）",
        [q("9999", "2026-03-31", 1.01)],
        {("9999", "2026-03-31"): 1.00},
        ["2026-03-31"],
    ),
    (
        "更正成 0 也要抓到（不可用 falsy 判斷有沒有值）",
        [q("9999", "2026-03-31", 0.0)],
        {("9999", "2026-03-31"): 0.55},
        ["2026-03-31"],
    ),
]

# 交易所給的是年初至今累計，所以累計對不上時該重抓整個會計年度——
# 只抓被點名的那一季，會漏掉「Q1 被更正、差異顯示在 Q2 累計」。
CANDIDATE_CASES = [
    (
        "重抓起點回推到該會計年度年初",
        [{"stock_id": "3521", "quarter_end_date": "2026-06-30"}],
        {"3521": "2026-01-01"},
    ),
    (
        "同一支被點名多季時只呼叫一次，起點取最早",
        [{"stock_id": "1591", "quarter_end_date": "2026-06-30"},
         {"stock_id": "1591", "quarter_end_date": "2025-09-30"}],
        {"1591": "2025-01-01"},
    ),
]


def main() -> int:
    failures = []

    for label, fresh, existing, expected in CASES:
        got = sorted(r["quarter_end_date"] for r in restatements(fresh, existing))
        if got != sorted(expected):
            failures.append(f"{label}\n      預期 {sorted(expected)}，得到 {got}")
        else:
            print(f"  ✓ {label}")

    for label, recs, expected in CANDIDATE_CASES:
        got = candidates(recs)
        if got != expected:
            failures.append(f"{label}\n      預期 {expected}，得到 {got}")
        else:
            print(f"  ✓ {label}")

    total = len(CASES) + len(CANDIDATE_CASES)
    if failures:
        print(f"\n❌ {len(failures)}/{total} 個案例失敗：")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"\n✅ {total} 個案例全數通過")
    return 0


if __name__ == "__main__":
    sys.exit(main())
