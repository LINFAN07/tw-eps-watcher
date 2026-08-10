"""
季度 EPS 更新腳本（財報季期間執行）

台灣上市櫃公司財報申報截止日：
  Q1（3月底）：5月15日前
  Q2（6月底）：8月14日前
  Q3（9月底）：11月14日前
  Q4 / 年報 ：隔年3月31日前

執行時機：財報季期間每週跑一次（由 GitHub Actions 排程）。
邏輯：
  1. 判斷本季財報季正在申報的季別（target_quarter）
  2. 跳過「資料庫已有該季 EPS」的股票——不呼叫 FinMind，直接略過
  3. 對其餘股票從 FinMind 取得最新 EPS，有新季度**或既有季度的值變了**
     （公司更正申報）就寫入 eps_quarterly
  4. 對有更新的股票呼叫 calculate_valuation，重算歷史 P/E 區間與估值

關於步驟 2：FinMind 免費版每次呼叫需間隔 6.5 秒，全市場 2,300+ 支跑完約 4.2 小時。
若每次都全部重抓，財報季每週一次仍會快速消耗 GitHub Actions 額度
（私有 repo 免費額度為 2,000 分鐘／月）。
跳過已取得的股票後，越接近季末已申報者越多，執行時間逐次遞減。
"""

import argparse
import os
import sys
import time
import requests
from datetime import date, timedelta
from dotenv import load_dotenv
from supabase import create_client
import calculate_valuation as cv
import finmind_client as fm

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
sys.stderr.reconfigure(encoding="utf-8", line_buffering=True)
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

FINMIND_TOKEN = os.getenv("FINMIND_TOKEN")
SUPABASE_URL  = os.getenv("SUPABASE_URL")
SUPABASE_KEY  = os.getenv("SUPABASE_KEY")

FINMIND_API   = "https://api.finmindtrade.com/api/v4/data"
CALL_INTERVAL = 6.5

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


def finmind_get(dataset, stock_id, start_date) -> list:
    """委派給共用客戶端：抓取失敗會拋 FinMindError，不以空清單掩蓋故障"""
    return fm.fetch(dataset, stock_id, start_date, FINMIND_TOKEN)


def get_all_stock_ids() -> list[str]:
    """
    取得所有股票代碼（分頁）。

    order 不可省：無排序的多次分頁查詢，Postgres 不保證跨頁順序一致，會重複或遺漏
    （見 CLAUDE.md 平台限制）。順序穩定也是 --after 斷點續傳成立的前提。
    """
    all_ids, offset = [], 0
    while True:
        resp = (supabase.table("stocks").select("stock_id")
                .order("stock_id").range(offset, offset + 999).execute())
        all_ids.extend(r["stock_id"] for r in resp.data)
        if len(resp.data) < 1000:
            break
        offset += 1000
    return all_ids


def get_latest_eps_dates() -> dict[str, str]:
    """取得資料庫中每支股票最新的 EPS 季度日期 {stock_id: date}"""
    # 用 Supabase 的 group-by 等效做法：每支股票取最新一筆
    all_rows, offset = [], 0
    while True:
        resp = (supabase.table("eps_quarterly")
                .select("stock_id, quarter_end_date")
                .order("quarter_end_date", desc=True)
                .range(offset, offset + 999).execute())
        all_rows.extend(resp.data)
        if len(resp.data) < 1000:
            break
        offset += 1000

    # 每支股票只保留最新日期
    latest = {}
    for row in all_rows:
        sid = row["stock_id"]
        if sid not in latest:
            latest[sid] = row["quarter_end_date"]
    return latest


def get_recent_eps(start_date: str) -> dict[tuple[str, str], float]:
    """
    查詢視窗內既有的 EPS {(stock_id, 季末日): eps}，用來偵測更正申報。

    只載入視窗內的季度（約 2 季 × 2,400 支），不是整張表。
    """
    existing, offset = {}, 0
    while True:
        resp = (supabase.table("eps_quarterly")
                .select("stock_id, quarter_end_date, eps")
                .gte("quarter_end_date", start_date)
                .order("stock_id").order("quarter_end_date")
                .range(offset, offset + 999).execute())
        existing.update({(r["stock_id"], r["quarter_end_date"]): float(r["eps"])
                         for r in resp.data})
        if len(resp.data) < 1000:
            break
        offset += 1000
    return existing


def target_quarter(today: date) -> str | None:
    """
    目前財報季正在申報的季別（季末日）。
    依申報期限回推：Q1→5/15、Q2→8/14、Q3→11/14、Q4/年報→隔年3/31。
    非財報季回傳 None（此時全部股票都要查，因為無從判斷該跳過誰）。
    """
    m, y = today.month, today.year
    if m in (1, 2, 3):    return f"{y - 1}-12-31"   # 年報申報期
    if m in (4, 5):       return f"{y}-03-31"       # Q1
    if m in (7, 8):       return f"{y}-06-30"       # Q2
    if m in (10, 11):     return f"{y}-09-30"       # Q3
    return None


def report_output(**kv):
    """寫進 GITHUB_OUTPUT，供 workflow 決定要不要啟動接力 job、從哪裡接續"""
    path = os.getenv("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            for k, v in kv.items():
                f.write(f"{k}={v}\n")


def run(time_budget: float | None = None, after: str | None = None):
    """
    time_budget：抓取階段的時間預算（分鐘）。用完就停止抓取，但**照常執行重算**。
    after：只處理排序在此代碼【之後】的股票，供接力 job 從斷點續跑。

    為什麼需要 time_budget：GitHub Actions 單一 job 上限 6 小時，被砍時整個 job
    立即死亡，排在迴圈之後的 cv.run() 一步都不會執行——2026-08-10 就是這樣，
    2360/2436 支的 EPS 已寫入 eps_quarterly，估值卻全部停在舊值，
    而 cancelled 不觸發 `if: failure()`，連通知都沒有。
    主動收尾則能保證「抓到的一定重算」。

    為什麼還需要 after：光靠「已有本季資料就跳過」接不上——那只對【查到新資料】
    的股票生效，尚未申報的公司下一段會被原封不動重查一次。2026-08-10 實測：
    第一段處理 4 支後，第二段的待查數仍是 1973 而非 1969，第一段的工等於白做。
    """
    started    = time.monotonic()
    today      = date.today()
    start_date = (today - timedelta(days=180)).strftime("%Y-%m-%d")  # 查近 6 個月
    print(f"=== 季度 EPS 更新：{today} ===")
    print(f"查詢起始日：{start_date}")
    if time_budget:
        print(f"抓取時間預算：{time_budget:.0f} 分鐘（用完即收尾並重算，不強制砍斷）")

    all_ids      = get_all_stock_ids()
    latest_dates = get_latest_eps_dates()
    existing_eps = get_recent_eps(start_date)

    # 已有本季 EPS 的股票不必再問 FinMind，直接跳過（省下 6.5 秒／支）
    target = target_quarter(today)
    if target:
        stock_ids = [s for s in all_ids if latest_dates.get(s, "1900-01-01") < target]
        print(f"本季申報季別：{target}")
        print(f"已有該季資料而跳過：{len(all_ids) - len(stock_ids)} 支")
    else:
        stock_ids = all_ids
        print("非財報季，全部股票皆需查詢")

    # 斷點續跑：清單已依 stock_id 排序，字串比較即可切出「還沒輪到的那一段」
    if after:
        before = len(stock_ids)
        stock_ids = [s for s in stock_ids if s > after]
        print(f"接續上一段（{after} 之後）：略過已查過的 {before - len(stock_ids)} 支")

    total       = len(stock_ids)
    updated_ids = []
    tracker     = fm.FailureTracker("季度 EPS 更新")
    print(f"需查詢：{total} 支（預估 {total * CALL_INTERVAL / 60:.0f} 分鐘）\n")

    stopped_at, last_id = None, after or ""
    for idx, sid in enumerate(stock_ids, 1):
        # 時間預算用完就停止抓取，但不是中斷——底下的重算與 tracker.finish() 照跑
        if time_budget and (time.monotonic() - started) / 60 >= time_budget:
            stopped_at = idx - 1
            print(f"\n⏱ 時間預算用完，已處理 {stopped_at}/{total} 支"
                  f"（最後：{last_id or '無'}），剩餘 {total - stopped_at} 支交給接力 job")
            break
        last_id = sid

        # 單支失敗不中斷整批（4 小時的下載不該因一次逾時全毀），
        # 但結尾 tracker.finish() 會讓工作以失敗結束，避免缺漏無人知悉
        try:
            raw = finmind_get("TaiwanStockFinancialStatements", sid, start_date)
        except fm.FinMindError as e:
            tracker.record(sid, e)
            time.sleep(CALL_INTERVAL)
            continue

        new_eps = fm.eps_rows(sid, raw)

        if not new_eps:
            time.sleep(CALL_INTERVAL)
            continue

        # 比對是否有新季度（日期比資料庫最新的更晚）
        db_latest = latest_dates.get(sid, "1900-01-01")
        truly_new = [r for r in new_eps if r["quarter_end_date"] > db_latest]

        # 更正申報：日期不是新的，但值變了。這一趟 FinMind 呼叫本來就回傳近 6 個月
        # 的多個季度，過去只在「有新季度」時才寫入，等於白拿了資料卻丟掉——
        # 公司事後更正財報，資料庫就永久停在第一版數字，且沒有任何機制會修正它。
        # 2026-07-27 事故：1591 駿吉-KY 的 2026Q1 EPS 停在 -0.08，官方已更正為 -1.18
        # （用官方淨利 -44,821 千元 ÷ 38,048 千股 = -1.178 驗算，官方為真），
        # 是 audit_external.py 逐筆比對交易所才發現的。
        # 偵測不到的部分要說清楚：本季已入庫而被上面跳過的股票這一輪不會呼叫，
        # 也就驗不到；查詢視窗（近 180 天）以外的舊季度同樣看不到。
        # 取不到既有值時以自身為預設 → 差為 0，不會誤判成更正
        restated = [r for r in new_eps
                    if r not in truly_new
                    and abs(existing_eps.get((sid, r["quarter_end_date"]), r["eps"])
                            - r["eps"]) > 0.005]

        if truly_new or restated:
            supabase.table("eps_quarterly").upsert(new_eps).execute()
            parts = []
            if truly_new:
                parts.append(f"新季度 {[r['quarter_end_date'] for r in truly_new]}，"
                             f"EPS={[r['eps'] for r in truly_new]}")
            for r in restated:
                old = existing_eps[(sid, r["quarter_end_date"])]
                parts.append(f"更正申報 {r['quarter_end_date']} {old}→{r['eps']}")
            print(f"  [{idx}/{total}] {sid} -> {'；'.join(parts)}")
            updated_ids.append(sid)

        time.sleep(CALL_INTERVAL)

    # 對有更新的股票重算完整估值（含歷史 P/E 區間）。
    # 這一步必須在時間預算之外：抓了卻沒重算，等於 eps_quarterly 與 valuations
    # 不一致，而畫面上看不出來（2026-08-10 事故）
    if updated_ids:
        print(f"\n共 {len(updated_ids)} 支股票有新 EPS，重新計算估值...")
        cv.run(updated_ids)
    else:
        print("\n本次無新 EPS 資料。")

    report_output(remaining=total - stopped_at if stopped_at is not None else 0,
                  last_id=last_id)
    print("\n完成！")
    tracker.finish()   # 有任何抓取失敗就以 exit 1 結束，觸發通知


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--time-budget", type=float, default=None, metavar="分鐘",
                    help="抓取階段的時間預算；用完即停止抓取並收尾重算（預設不限）")
    ap.add_argument("--after", default=None, metavar="股票代碼",
                    help="只處理排序在此之後的股票，供接力 job 從斷點續跑")
    run(**vars(ap.parse_args()))
