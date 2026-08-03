"""
初始下載腳本（只需執行一次）
下載全市場近 10 年的股票名冊、季度 EPS、日收盤價，寫入 Supabase。
預計總耗時：6 小時。中途中斷可重新執行，會從上次進度繼續。
"""

import os
import sys
import json
import time
from datetime import datetime, timedelta
from dotenv import load_dotenv
from supabase import create_client
import finmind_client as fm

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

FINMIND_TOKEN = os.getenv("FINMIND_TOKEN")
SUPABASE_URL  = os.getenv("SUPABASE_URL")
SUPABASE_KEY  = os.getenv("SUPABASE_KEY")

START_DATE    = (datetime.today() - timedelta(days=365 * 10)).strftime("%Y-%m-%d")
CALL_INTERVAL = 6.5
PROGRESS_FILE = os.path.join(os.path.dirname(__file__), "init_progress.json")
EPS_TYPES     = {"EPS", "BasicEPS", "EPSTaxExcluded"}

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


def upsert_batch(table, rows, batch_size=500):
    for i in range(0, len(rows), batch_size):
        supabase.table(table).upsert(rows[i:i + batch_size]).execute()


def load_progress():
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"eps_done": [], "prices_done": []}


def save_progress(progress):
    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump(progress, f, ensure_ascii=False)


def step1_download_stocks():
    print("=== 步驟 1：下載股票名冊 ===")
    # 名冊抓不到就無事可做；fetch 失敗會拋 FinMindError 讓整個工作 exit 1，
    # 不再用「回傳空清單」把故障偽裝成「沒有資料」。
    raw = fm.fetch("TaiwanStockInfo", None, None, FINMIND_TOKEN)

    seen, stocks = set(), []
    for item in raw:
        sid = str(item.get("stock_id", "")).strip()
        if sid.isdigit() and len(sid) == 4 and sid not in seen:
            seen.add(sid)
            stocks.append({"stock_id": sid, "name": item.get("stock_name", ""),
                           "market": fm.roster_market(item)})
    upsert_batch("stocks", stocks)
    print(f"✅ 完成：共 {len(stocks)} 支股票")
    return [s["stock_id"] for s in stocks]


# ── 步驟 2/3 共用：通用下載函式 ───────────────────────────

def _extract_eps(sid, raw):
    return [{"stock_id": sid, "quarter_end_date": r["date"], "eps": float(r["value"])}
            for r in raw if r.get("type") in EPS_TYPES and r.get("value") is not None]

def _extract_price(sid, raw):
    # FinMind 對「當日無成交」回傳 close = 0，那不是價格而是缺值。
    # 若照寫進資料庫，河流圖的月採樣會採到 0，畫出股價暴跌至零的假訊號
    # （實測 3629 有 31/122 個月採樣點為 0）。沒有成交就不該有記錄。
    return [{"stock_id": sid, "date": r["date"], "close_price": float(r["close"])}
            for r in raw if r.get("close") is not None and float(r["close"]) > 0]

def _download_step(label, dataset, table, progress_key, stock_ids, progress,
                   extract_fn, tracker):
    done      = set(progress[progress_key])
    remaining = [s for s in stock_ids if s not in done]
    total     = len(stock_ids)
    print(f"\n=== {label}（已完成 {len(done)}/{total}，剩餘 {len(remaining)} 支）===")
    if not remaining:
        print("✅ 跳過（已全數完成）")
        return
    for idx, sid in enumerate(remaining, 1):
        # 抓取失敗只記錄該支、不寫進度，讓它下次重跑時重試；
        # 絕不把故障當成空清單寫進去、並標記「已完成」而永久留下缺口。
        try:
            rows = extract_fn(sid, fm.fetch(dataset, sid, START_DATE, FINMIND_TOKEN))
        except fm.FinMindError as e:
            tracker.record(sid, e)
            print(f"  [{len(done) + idx}/{total}] {sid}：抓取失敗，稍後重試")
            time.sleep(CALL_INTERVAL)
            continue
        upsert_batch(table, rows)
        progress[progress_key].append(sid)
        save_progress(progress)
        print(f"  [{len(done) + idx}/{total}] {sid}：{len(rows)} 筆")
        time.sleep(CALL_INTERVAL)
    print("✅ 完成")


if __name__ == "__main__":
    print(f"開始時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"資料起始日：{START_DATE}\n")

    progress  = load_progress()
    stock_ids = step1_download_stocks()

    if stock_ids:
        # 單支失敗不中斷整批（避免數小時的下載因一次逾時全毀），
        # 但收尾時 tracker.finish() 若有任何失敗就 exit 1，觸發排程通知。
        tracker = fm.FailureTracker("初始下載")
        _download_step("步驟 2：下載季度 EPS", "TaiwanStockFinancialStatements",
                       "eps_quarterly", "eps_done", stock_ids, progress, _extract_eps, tracker)
        _download_step("步驟 3：下載日收盤價", "TaiwanStockPrice",
                       "daily_prices", "prices_done", stock_ids, progress, _extract_price, tracker)
        print(f"\n全部完成！結束時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        tracker.finish()
