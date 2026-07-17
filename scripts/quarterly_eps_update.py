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
  3. 對其餘股票從 FinMind 取得最新 EPS，有新季度就寫入 eps_quarterly
  4. 對有更新的股票呼叫 calculate_valuation，重算歷史 P/E 區間與估值

關於步驟 2：FinMind 免費版每次呼叫需間隔 6.5 秒，全市場 2,300+ 支跑完約 4.2 小時。
若每次都全部重抓，財報季每週一次仍會快速消耗 GitHub Actions 額度
（私有 repo 免費額度為 2,000 分鐘／月）。
跳過已取得的股票後，越接近季末已申報者越多，執行時間逐次遞減。
"""

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
EPS_TYPES     = {"EPS", "BasicEPS", "EPSTaxExcluded"}
CALL_INTERVAL = 6.5

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


def finmind_get(dataset, stock_id, start_date) -> list:
    """委派給共用客戶端：抓取失敗會拋 FinMindError，不以空清單掩蓋故障"""
    return fm.fetch(dataset, stock_id, start_date, FINMIND_TOKEN)


def get_all_stock_ids() -> list[str]:
    """取得所有股票代碼（分頁）"""
    all_ids, offset = [], 0
    while True:
        resp = supabase.table("stocks").select("stock_id").range(offset, offset + 999).execute()
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


def run():
    today      = date.today()
    start_date = (today - timedelta(days=180)).strftime("%Y-%m-%d")  # 查近 6 個月
    print(f"=== 季度 EPS 更新：{today} ===")
    print(f"查詢起始日：{start_date}")

    all_ids      = get_all_stock_ids()
    latest_dates = get_latest_eps_dates()

    # 已有本季 EPS 的股票不必再問 FinMind，直接跳過（省下 6.5 秒／支）
    target = target_quarter(today)
    if target:
        stock_ids = [s for s in all_ids if latest_dates.get(s, "1900-01-01") < target]
        print(f"本季申報季別：{target}")
        print(f"已有該季資料而跳過：{len(all_ids) - len(stock_ids)} 支")
    else:
        stock_ids = all_ids
        print("非財報季，全部股票皆需查詢")

    total       = len(stock_ids)
    updated_ids = []
    tracker     = fm.FailureTracker("季度 EPS 更新")
    print(f"需查詢：{total} 支（預估 {total * CALL_INTERVAL / 60:.0f} 分鐘）\n")

    for idx, sid in enumerate(stock_ids, 1):
        # 單支失敗不中斷整批（4 小時的下載不該因一次逾時全毀），
        # 但結尾 tracker.finish() 會讓工作以失敗結束，避免缺漏無人知悉
        try:
            raw = finmind_get("TaiwanStockFinancialStatements", sid, start_date)
        except fm.FinMindError as e:
            tracker.record(sid, e)
            time.sleep(CALL_INTERVAL)
            continue

        new_eps = [
            {"stock_id": sid, "quarter_end_date": r["date"], "eps": float(r["value"])}
            for r in raw
            if r.get("type") in EPS_TYPES and r.get("value") is not None
        ]

        if not new_eps:
            time.sleep(CALL_INTERVAL)
            continue

        # 比對是否有新季度（日期比資料庫最新的更晚）
        db_latest = latest_dates.get(sid, "1900-01-01")
        truly_new = [r for r in new_eps if r["quarter_end_date"] > db_latest]

        if truly_new:
            supabase.table("eps_quarterly").upsert(new_eps).execute()
            print(f"  [{idx}/{total}] {sid} -> 新季度 {[r['quarter_end_date'] for r in truly_new]}，EPS={[r['eps'] for r in truly_new]}")
            updated_ids.append(sid)

        time.sleep(CALL_INTERVAL)

    # 對有更新的股票重算完整估值（含歷史 P/E 區間）
    if updated_ids:
        print(f"\n共 {len(updated_ids)} 支股票有新 EPS，重新計算估值...")
        cv.run(updated_ids)
    else:
        print("\n本次無新 EPS 資料。")

    print("\n完成！")
    tracker.finish()   # 有任何抓取失敗就以 exit 1 結束，觸發通知


if __name__ == "__main__":
    run()
