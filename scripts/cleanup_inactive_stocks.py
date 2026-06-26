"""
清除下市/停牌股票腳本（一次性執行）

邏輯：
  1. 從 TWSE、TPEx 上櫃、TPEx 興櫃 3 個 API 取得今日有報價的股票清單
  2. 和資料庫的 stocks 比對，找出完全不在任何市場的股票
  3. 從 valuations 刪除這些股票（排行榜和個股頁不再顯示）
  4. stocks / eps_quarterly / daily_prices 保留，不刪歷史資料

注意：此腳本只在交易日執行（週一至週五）
"""

import os
import sys
import requests
from dotenv import load_dotenv
from supabase import create_client

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

TWSE_URL = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
TPEX_URL = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes"
ESB_URL  = "https://www.tpex.org.tw/openapi/v1/tpex_esb_latest_statistics"


def clean_code(s) -> str | None:
    """回傳 4 位數字代碼，否則回 None"""
    c = str(s).strip()
    return c if c.isdigit() and len(c) == 4 else None


def fetch_active_codes() -> set[str]:
    """取得三個市場今日有報價的股票代碼"""
    active = set()
    sources = [
        (TWSE_URL,  "Code"),
        (TPEX_URL,  "SecuritiesCompanyCode"),
        (ESB_URL,   "SecuritiesCompanyCode"),
    ]
    for url, field in sources:
        try:
            data = requests.get(url, timeout=30).json()
            codes = {clean_code(r.get(field)) for r in data if clean_code(r.get(field))}
            print(f"  {url.split('/')[-1]}: {len(codes)} 支")
            active |= codes
        except Exception as e:
            print(f"  警告：{url.split('/')[-1]} 取得失敗 ({e})")
    return active


def fetch_db_stock_ids() -> list[str]:
    all_ids, offset = [], 0
    while True:
        resp = supabase.table("stocks").select("stock_id").range(offset, offset + 999).execute()
        all_ids.extend(r["stock_id"] for r in resp.data)
        if len(resp.data) < 1000:
            break
        offset += 1000
    return all_ids


def delete_valuations_batch(stock_ids: list[str]):
    """分批從 valuations 刪除（IN 查詢每批 100 筆）"""
    for i in range(0, len(stock_ids), 100):
        batch = stock_ids[i:i + 100]
        supabase.table("valuations").delete().in_("stock_id", batch).execute()


def run():
    print("=== 清除下市/停牌股票 ===\n")

    print("取得今日市場報價清單...")
    active = fetch_active_codes()
    print(f"\n三市場合計活躍股票：{len(active)} 支\n")

    if len(active) < 500:
        print("活躍股票數異常偏少（可能今日休市），中止執行")
        return

    print("取得資料庫股票清單...")
    db_ids = fetch_db_stock_ids()
    print(f"資料庫：{len(db_ids)} 支\n")

    inactive = [sid for sid in db_ids if sid not in active]
    print(f"不在任何市場的股票：{len(inactive)} 支")
    if inactive:
        print("前 20 筆：", inactive[:20])

    # 確認是否要刪除
    ans = input(f"\n確認從 valuations 刪除這 {len(inactive)} 支股票？(y/N): ").strip().lower()
    if ans != "y":
        print("取消。")
        return

    print("\n刪除中...")
    delete_valuations_batch(inactive)
    print(f"完成！已從 valuations 移除 {len(inactive)} 支下市/停牌股票。")
    print("（stocks / eps_quarterly / daily_prices 歷史資料保留）")


if __name__ == "__main__":
    run()
