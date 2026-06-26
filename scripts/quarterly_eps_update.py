"""
季度 EPS 更新腳本（財報季期間執行）

台灣上市櫃公司財報申報截止日：
  Q1（3月底）：5月15日前
  Q2（6月底）：8月14日前
  Q3（9月底）：11月14日前
  Q4 / 年報 ：隔年3月31日前

執行時機：財報季期間每天跑一次（由 GitHub Actions 排程）。
邏輯：
  1. 從 FinMind 取得最新 EPS
  2. 若有新季度資料（比資料庫中最新日期更新），寫入 eps_quarterly
  3. 對有更新的股票呼叫 calculate_valuation，重算歷史 P/E 區間與估值
  4. 印出有哪些股票更新了（供 GitHub Actions log 追蹤）
"""

import os
import sys
import time
import requests
from datetime import date, timedelta
from dotenv import load_dotenv
from supabase import create_client
import calculate_valuation as cv

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
    params = {"dataset": dataset, "data_id": stock_id,
              "start_date": start_date, "token": FINMIND_TOKEN}
    for attempt in range(3):
        try:
            data = requests.get(FINMIND_API, params=params, timeout=30).json()
            if data.get("status") == 200:
                return data.get("data", [])
            print(f"  API 異常: {data.get('msg', '未知')}")
        except Exception as e:
            print(f"  請求失敗（第 {attempt + 1} 次）: {e}")
        time.sleep(10)
    return []


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


def run():
    today      = date.today()
    start_date = (today - timedelta(days=180)).strftime("%Y-%m-%d")  # 查近 6 個月
    print(f"=== 季度 EPS 更新：{today} ===")
    print(f"查詢起始日：{start_date}\n")

    stock_ids   = get_all_stock_ids()
    latest_dates = get_latest_eps_dates()
    total        = len(stock_ids)
    updated_ids  = []

    for idx, sid in enumerate(stock_ids, 1):
        raw = finmind_get("TaiwanStockFinancialStatements", sid, start_date)

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


if __name__ == "__main__":
    run()
