"""
更正申報回補：對「與交易所對不上」的股票重抓 FinMind，把更正後的 EPS 寫回。

## 為什麼需要這支

`eps_quarterly` 是全專案唯一「寫入後就永遠不再重抓」的財報資料表。
`download_balance_sheet.py` / `download_income_statement.py` / `download_cash_flows.py`
每次執行都重抓 10 年並 upsert，公司事後更正財報會自動修好；
只有 EPS 為了省時間做了跳過優化——`quarterly_eps_update.py` 會略過
「資料庫已有本季 EPS」的股票（全市場重抓要 4.2 小時，財報季每週一次
會吃光私有 repo 每月 2,000 分鐘的額度）。

那支腳本 2026-07-27 補上了更正偵測，但它只對「本季還沒入庫」的股票生效——
已申報的股票在呼叫 FinMind 之前就被跳過了，而那正是會發生更正的族群。
**2026-07-27 事故**：1591 駿吉-KY 的 2026Q1 EPS 停在 -0.08，官方已更正為 -1.18
（官方淨利 -44,821 千元 ÷ 38,048 千股 = -1.178 驗算，官方為真），
是 `audit_external.py` 逐筆比對交易所才發現的，而稽核只會報告、不會修。

## 做法：偵測免費，重抓精準

偵測沿用 `audit_external.eps_compare()`——交易所綜合損益表整批端點，
30 秒跑完全市場，不花任何 FinMind 額度。只對被點名的那幾支呼叫 FinMind
（6.5 秒／支），數量級是數十支而非 2,400 支。

## 三種結果必須分開，不可混為一談

  1. **FinMind 的值與我們不同** → 真的是更正申報，寫回並重算估值。
  2. **FinMind 與我們一致，但都與交易所不同** → 兩個來源本身分歧，
     **不寫**。此時把交易所的累計值換算成單季塞進來，等於在同一條歷史序列裡
     混用兩個來源（違反「不得以另一個指標頂替」），而且我們無從判斷誰對。
     只列報，讓 `audit_external.py` 繼續紅燈，由人去看。
     實例：3521 的 2026Q2，我們與 FinMind 都是累計 2.10，交易所 1.96。
  3. **抓取失敗** → 以 exit 1 結束（誠信原則第 5 條）。

## 盲區（不要以為跑綠燈就沒有更正遺漏）

  - **只看得到當期**。交易所財報端點一進新財報季就切到新季別，
    「三年前某季被更正」這條路徑完全看不到。
  - **興櫃看不到**。`INCOME_ENDPOINTS` 只有上市 `_L` 與上櫃 `_O`。
  - **交易所自己也可能沒更正**。這條防線驗的是「兩個來源說法一致」，
    不是「數字是真的」。兩邊一起錯就一起沉默。
  - **容差內的更正看不到**。差距在 `EPS_TOLERANCE` 以內的小幅更正不會被點名。

用法：
  python scripts/refetch_restated_eps.py            # 偵測並寫回
  python scripts/refetch_restated_eps.py --dry-run  # 只印出會做什麼，不寫入
"""

import argparse
import os
import sys
import time

from dotenv import load_dotenv
from supabase import create_client

sys.path.insert(0, os.path.dirname(__file__))
import finmind_client as fm   # noqa: E402（純 requests，import 無資料庫副作用）

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
sys.stderr.reconfigure(encoding="utf-8", line_buffering=True)
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

FINMIND_TOKEN = os.getenv("FINMIND_TOKEN")

CALL_INTERVAL = 6.5          # FinMind 免費版速率限制
EPS_EPSILON   = 0.005        # 小於此視為同值（EPS 揭露到小數點後兩位）


def candidates(recs: list[dict]) -> dict[str, str]:
    """
    不符明細 → {股票代碼: 該重抓的起始日}。

    交易所給的是年初至今累計值，所以累計對不上時，出錯的可能是該會計年度的
    **任何一季**——必須把整個年度都抓回來比對，只抓被點名的那一季會漏掉
    「Q1 被更正、但差異顯示在 Q2 累計」的情形。
    """
    starts: dict[str, str] = {}
    for r in recs:
        year_start = f"{r['quarter_end_date'][:4]}-01-01"
        sid = r["stock_id"]
        starts[sid] = min(starts.get(sid, year_start), year_start)
    return starts


def restatements(fresh: list[dict], existing: dict[tuple[str, str], float]) -> list[dict]:
    """
    FinMind 這次回傳的季度中，哪幾季的值與資料庫不同（＝更正申報）。

    取不到既有值時以自身為預設 → 差為 0，因此**新季度不會被算成更正**。
    那是 `quarterly_eps_update.py` 的職責，這支只管「既有的值變了」；
    兩支都寫入同一張表，界線混掉會讓「更正了幾筆」這個數字失去意義。
    """
    return [r for r in fresh
            if abs(existing.get((r["stock_id"], r["quarter_end_date"]), r["eps"]) - r["eps"])
            > EPS_EPSILON]


def db_eps(supabase, stock_ids: list[str], since: str) -> dict[tuple[str, str], float]:
    """取回這批股票在視窗內的既有單季 EPS，用來比對 FinMind 有沒有變。"""
    existing: dict[tuple[str, str], float] = {}
    for i in range(0, len(stock_ids), 100):
        chunk = stock_ids[i:i + 100]
        offset = 0
        while True:
            rows = (supabase.table("eps_quarterly")
                    .select("stock_id, quarter_end_date, eps")
                    .in_("stock_id", chunk).gte("quarter_end_date", since)
                    .order("stock_id").order("quarter_end_date")
                    .range(offset, offset + 999).execute().data)
            existing.update({(r["stock_id"], r["quarter_end_date"]): float(r["eps"])
                             for r in rows if r["eps"] is not None})
            if len(rows) < 1000:
                break
            offset += 1000
    return existing


def run(dry_run: bool = False):
    # audit_external 一 import 就 create_client，資料庫連線也在這裡才建立：
    # tests/test_restated_eps.py 要在【沒有資料庫密鑰】的 CI 步驟 import 本檔的
    # candidates()／restatements() 兩個純函式——這些搬回模組層級的話，本機有
    # .env 照樣全綠，只有 CI 會在 import 階段死（2026-08-10 首次排程即如此）。
    import audit_external as ax
    supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

    print("=== 更正申報回補 ===")
    if dry_run:
        print("（--dry-run：只偵測，不寫入）")

    _, _, recs = ax.eps_compare()
    if not recs:
        print("\n沒有與交易所不符的季度，無須重抓。")
        return

    targets = candidates(recs)
    print(f"\n交易所比對出 {len(recs)} 筆不符，涉及 {len(targets)} 支股票"
          f"（預估 {len(targets) * CALL_INTERVAL / 60:.1f} 分鐘）：")
    for r in recs:
        print(f"  {r['stock_id']} {r['quarter_end_date']}："
              f"我們累計 {r['ours']} vs 交易所 {r['theirs']}")

    since    = min(targets.values())
    existing = db_eps(supabase, sorted(targets), since)

    restated: list[str] = []      # 真的是更正申報，已寫回
    divergent: list[str] = []     # FinMind 與我們一致，但都與交易所不同
    tracker = fm.FailureTracker("更正申報回補")

    print()
    for idx, (sid, start) in enumerate(sorted(targets.items()), 1):
        # 單支失敗不中斷整批，但收尾 tracker.finish() 會讓工作以 exit 1 結束
        try:
            raw = fm.fetch("TaiwanStockFinancialStatements", sid, start, FINMIND_TOKEN)
        except fm.FinMindError as e:
            tracker.record(sid, e)
            time.sleep(CALL_INTERVAL)
            continue

        changed = restatements(fm.eps_rows(sid, raw), existing)

        if not changed:
            # FinMind 說的跟我們一樣 → 分歧在 FinMind 與交易所之間，我們無從裁決。
            # 拿交易所的累計值回推單季塞進來會讓同一條序列混用兩個來源，不做。
            divergent.append(sid)
            print(f"  [{idx}/{len(targets)}] {sid} -> FinMind 與我們一致，來源分歧（不寫入）")
            time.sleep(CALL_INTERVAL)
            continue

        detail = "；".join(
            f"{r['quarter_end_date']} "
            f"{existing.get((sid, r['quarter_end_date']), '無')}→{r['eps']}"
            for r in changed)
        if not dry_run:
            # 只寫變動的那幾季，不是整批 fresh：同一次呼叫可能夾帶尚未入庫的新季度，
            # 那歸 quarterly_eps_update.py 管。寫入範圍與上面印出的 detail 一致，
            # 日誌才等於實際發生的事。
            supabase.table("eps_quarterly").upsert(changed).execute()
        print(f"  [{idx}/{len(targets)}] {sid} -> "
              f"{'會寫入更正' if dry_run else '更正申報'}：{detail}")
        restated.append(sid)
        time.sleep(CALL_INTERVAL)

    if restated and not dry_run:
        # 到用時才 import：它會拉 pandas/numpy 且 import 當下即 create_client，
        # 「無不符」與 --dry-run 兩條常見路徑都不必付這個成本（延後理由同函式開頭）
        import calculate_valuation as cv
        print(f"\n{len(restated)} 支有更正，重算估值...")
        cv.run(restated)

    print(f"\n更正並寫回 {len(restated)} 支；來源分歧未處理 {len(divergent)} 支")
    if divergent:
        # 刻意不 exit 1：這不是可以靠重抓修好的問題，而 audit_external.py
        # 已經會為同一批股票紅燈。這裡再叫一次只是同一件事響兩個鈴。
        print(f"  來源分歧（FinMind 與交易所不合，須人工判斷）：{', '.join(divergent)}")

    tracker.finish()   # 有任何抓取失敗就 exit 1，觸發通知


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="只偵測不寫入")
    run(**vars(ap.parse_args()))
