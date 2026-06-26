"""
每日股價更新腳本（每個交易日收盤後執行）

只需 2 次 API 呼叫即可取得全市場收盤價（TWSE + TPEx OpenAPI 免費無限制）。
更新邏輯：
  1. 取得當日全市場收盤價
  2. 寫入 daily_prices 資料表
  3. 快速更新 valuations 現價與狀態（不重算歷史 P/E，只用現有區間）

與 calculate_valuation.py 的分工：
  - 本腳本（每日）：只更新現價與狀態
  - calculate_valuation.py（每季）：重算歷史 P/E 區間（EPS 有更新時才需要）
"""

import os
import sys
import requests
from datetime import date
from dotenv import load_dotenv
from supabase import create_client

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
sys.stderr.reconfigure(encoding="utf-8", line_buffering=True)
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

TWSE_URL = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
TPEX_URL = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes"


def clean_price(s) -> float | None:
    """移除千分位逗號並轉 float，非數字或零回傳 None"""
    try:
        v = float(str(s).replace(",", "").strip())
        return v if v > 0 else None
    except (ValueError, TypeError):
        return None


def fetch_twse_prices() -> dict[str, float]:
    try:
        data = requests.get(TWSE_URL, timeout=30).json()
        return {str(r.get("Code", "")).strip(): p
                for r in data if (p := clean_price(r.get("ClosingPrice")))}
    except Exception as e:
        print(f"  TWSE 取得失敗: {e}")
        return {}


def fetch_tpex_prices() -> dict[str, float]:
    try:
        data = requests.get(TPEX_URL, timeout=30).json()
        return {str(r.get("SecuritiesCompanyCode", "")).strip(): p
                for r in data if (p := clean_price(r.get("Close")))}
    except Exception as e:
        print(f"  TPEx 取得失敗: {e}")
        return {}


def upsert_batch(table, rows, batch_size=500):
    for i in range(0, len(rows), batch_size):
        supabase.table(table).upsert(rows[i:i + batch_size]).execute()


def update_valuations(prices: dict[str, float]):
    """
    快速更新估值現價與狀態。
    從 valuations 讀出既有 P/E 區間，搭配新收盤價重判便宜/合理/昂貴。
    """
    sids = list(prices.keys())
    existing = []
    # 批次讀取（IN 查詢每批最多 100 個 id）
    for i in range(0, len(sids), 100):
        batch = sids[i:i + 100]
        resp = (supabase.table("valuations")
                .select("stock_id,ttm_eps,cheap_pe,fair_pe,expensive_pe")
                .in_("stock_id", batch).execute())
        existing.extend(resp.data)

    updates = []
    for row in existing:
        sid       = row["stock_id"]
        price     = prices.get(sid)
        ttm_eps   = row.get("ttm_eps") or 0
        cheap_pe  = row.get("cheap_pe") or 0
        fair_pe   = row.get("fair_pe") or 0

        if not price or ttm_eps <= 0:
            continue

        if price <= ttm_eps * cheap_pe:
            status = "便宜"
        elif price <= ttm_eps * fair_pe:
            status = "合理"
        else:
            status = "昂貴"

        updates.append({"stock_id": sid, "current_price": round(price, 2), "status": status})

    upsert_batch("valuations", updates)
    print(f"估值狀態更新：{len(updates)} 支")


def run():
    today = date.today().strftime("%Y-%m-%d")
    print(f"=== 每日股價更新：{today} ===\n")

    # 1. 取得當日收盤價
    print("取得上市股票收盤價（TWSE）...")
    twse = fetch_twse_prices()
    print(f"  {len(twse)} 支")

    print("取得上櫃股票收盤價（TPEx）...")
    tpex = fetch_tpex_prices()
    print(f"  {len(tpex)} 支")

    # TWSE 與 TPEx 合併，若代碼重複以 TWSE 為準
    all_prices = {**tpex, **twse}

    if not all_prices:
        print("\n今日無交易資料（休市），結束。")
        return

    # 2. 過濾出資料庫中已有的股票（分頁繞過 1000 筆上限）
    known, offset = set(), 0
    while True:
        resp = supabase.table("stocks").select("stock_id").range(offset, offset + 999).execute()
        known.update(r["stock_id"] for r in resp.data)
        if len(resp.data) < 1000:
            break
        offset += 1000

    price_rows = [{"stock_id": sid, "date": today, "close_price": p}
                  for sid, p in all_prices.items() if sid in known]
    print(f"\n符合資料庫的股票：{len(price_rows)} 支")

    # 3. 寫入 daily_prices
    upsert_batch("daily_prices", price_rows)
    print("收盤價寫入完成")

    # 4. 快速更新估值現價與狀態
    print("\n更新估值...")
    known_prices = {r["stock_id"]: r["close_price"] for r in price_rows}
    update_valuations(known_prices)

    print("\n完成！")


if __name__ == "__main__":
    run()
