"""
每日股價更新腳本（每個交易日收盤後執行）

只需 3 次 API 呼叫即可取得全市場收盤價（TWSE + TPEx 上櫃 + TPEx 興櫃）。
更新邏輯：
  1. 取得當日全市場收盤價（上市 + 上櫃 + 興櫃）
  2. 寫入 daily_prices 資料表
  3. 快速更新 valuations 現價與狀態（不重算歷史 P/E，只用現有區間）

與 calculate_valuation.py 的分工：
  - 本腳本（每日）：只更新現價與狀態
  - calculate_valuation.py（每季）：重算歷史 P/E 區間（EPS 有更新時才需要）
"""

import os
import sys
import requests
from datetime import date, datetime, timezone
from dotenv import load_dotenv
from supabase import create_client

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
sys.stderr.reconfigure(encoding="utf-8", line_buffering=True)
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

TWSE_URL = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
TPEX_URL = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes"
ESB_URL  = "https://www.tpex.org.tw/openapi/v1/tpex_esb_latest_statistics"


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
        print(f"  TPEx 上櫃取得失敗: {e}")
        return {}


def fetch_esb_prices() -> dict[str, float]:
    """興櫃（第三市場）最新成交價，以 LatestPrice 為主、Average 為備"""
    try:
        data = requests.get(ESB_URL, timeout=30).json()
        result = {}
        for r in data:
            code = str(r.get("SecuritiesCompanyCode", "")).strip()
            if not code:
                continue
            price = clean_price(r.get("LatestPrice")) or clean_price(r.get("Average"))
            if price:
                result[code] = price
        return result
    except Exception as e:
        print(f"  TPEx 興櫃取得失敗: {e}")
        return {}


def upsert_batch(table, rows, batch_size=500):
    for i in range(0, len(rows), batch_size):
        supabase.table(table).upsert(rows[i:i + batch_size]).execute()


# 各估值模型的 (便宜價欄位, 合理價欄位, 狀態欄位)
STATUS_MODELS = [
    ("cheap_price",      "fair_price",      "status"),
    ("pb_cheap_price",   "pb_fair_price",   "pb_status"),
    ("ps_cheap_price",   "ps_fair_price",   "ps_status"),
    ("pfcf_cheap_price", "pfcf_fair_price", "pfcf_status"),
    ("yield_cheap_price","yield_fair_price","yield_status"),
]

_STATUS_COLS = "stock_id," + ",".join(
    col for model in STATUS_MODELS for col in model[:2]
)


def judge_status(price: float, cheap, fair) -> str:
    """
    以現價比對「已算好的」目標價，判定便宜/合理/昂貴。

    刻意不重算「基準值 × 倍數」：calculate_valuation.py 在 TTM EPS 失真時
    會改用常態化 EPS 當基準，此處若自行重算會得出不同答案並覆蓋掉正確結果。
    目標價本身即為單一真相來源。

    非正數目標價代表基準值為負（如虧損股），該模型不適用；
    此處主動擋掉，避免尚未重算的舊資料被誤判為「昂貴」。
    """
    if cheap is None or fair is None or cheap <= 0 or fair <= 0:
        return "無法計算"
    if price <= cheap:
        return "便宜"
    if price <= fair:
        return "合理"
    return "昂貴"


def update_valuations(prices: dict[str, float]):
    """
    快速更新估值現價與狀態（P/E + P/B + P/S + P/FCF + 殖利率）。
    只比對現價與既有目標價，不重算歷史區間（那是 calculate_valuation.py 的職責）。
    """
    sids = list(prices.keys())
    existing = []
    # 批次讀取（IN 查詢每批最多 100 個 id）
    for i in range(0, len(sids), 100):
        batch = sids[i:i + 100]
        resp = (supabase.table("valuations")
                .select(_STATUS_COLS)
                .in_("stock_id", batch).execute())
        existing.extend(resp.data)

    # updated_at 欄位的 DEFAULT NOW() 只在 INSERT 時生效，UPDATE 不會自動變動，
    # 需明確帶入，否則前端顯示的「最後更新」會永遠停在建置日期。
    now = datetime.now(timezone.utc).isoformat()

    updates = []
    for row in existing:
        sid   = row["stock_id"]
        price = prices.get(sid)
        if not price or price <= 0:
            continue

        # 現價一律更新（含虧損股），各模型狀態依其目標價各自判定
        update = {"stock_id": sid, "current_price": round(price, 2), "updated_at": now}
        for cheap_col, fair_col, status_col in STATUS_MODELS:
            update[status_col] = judge_status(price, row.get(cheap_col), row.get(fair_col))
        updates.append(update)

    upsert_batch("valuations", updates)
    print(f"估值狀態更新：{len(updates)} 支")


def run():
    today = date.today().strftime("%Y-%m-%d")
    print(f"=== 每日股價更新：{today} ===\n")

    # 1. 取得當日收盤價
    print("取得上市股票收盤價（TWSE）...")
    twse = fetch_twse_prices()
    print(f"  {len(twse)} 支")

    print("取得上櫃股票收盤價（TPEx 上櫃）...")
    tpex = fetch_tpex_prices()
    print(f"  {len(tpex)} 支")

    print("取得興櫃股票收盤價（TPEx 興櫃）...")
    esb = fetch_esb_prices()
    print(f"  {len(esb)} 支")

    # 三市場合併，優先順序：TWSE > TPEx 上櫃 > 興櫃
    all_prices = {**esb, **tpex, **twse}

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
