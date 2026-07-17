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

# 上市：使用官網 rwd 端點，而非 openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL。
# 後者是 T-1 的批次檔（實測當日晚間 9 點仍回傳前一交易日資料），
# 會讓排程把前一日收盤價寫成當日價格。官網端點則有當日資料。
TWSE_URL = "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX"
TPEX_URL = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes"
ESB_URL  = "https://www.tpex.org.tw/openapi/v1/tpex_esb_latest_statistics"

# 官網 rwd 端點會擋掉沒有 User-Agent 的請求
UA = {"User-Agent": "Mozilla/5.0"}


def clean_price(s) -> float | None:
    """移除千分位逗號並轉 float，非數字或零回傳 None"""
    try:
        v = float(str(s).replace(",", "").strip())
        return v if v > 0 else None
    except (ValueError, TypeError):
        return None


def roc_to_iso(raw) -> str | None:
    """民國日期（1150717）轉西元（2026-07-17）"""
    text = str(raw).strip()
    if len(text) != 7 or not text.isdigit():
        return None
    return f"{int(text[:3]) + 1911:04d}-{text[3:5]}-{text[5:7]}"


def fetch_twse_prices() -> tuple[str | None, dict[str, float]]:
    """
    上市收盤價。回傳 (資料日期, {股票代碼: 收盤價})。

    日期一律取自 API 回應，不用系統當日：交易所的資料日期未必等於今天
    （休市、來源延遲皆會造成落差），用系統日期蓋章會把舊價寫成今日價。
    """
    today = date.today().strftime("%Y%m%d")
    try:
        resp = requests.get(TWSE_URL, params={"date": today, "type": "ALL", "response": "json"},
                            headers=UA, timeout=30).json()
    except Exception as e:
        print(f"  TWSE 取得失敗: {e}")
        return None, {}

    if resp.get("stat") != "OK":
        # 休市時為「很抱歉，沒有符合條件的資料!」，端點自身即可判斷交易日
        print(f"  TWSE 無資料：{resp.get('stat')}")
        return None, {}

    table = next((t for t in resp.get("tables", []) if "每日收盤行情" in str(t.get("title", ""))), None)
    if not table:
        print("  TWSE 回應中找不到每日收盤行情表")
        return None, {}

    fields = table.get("fields", [])
    try:
        i_code, i_close = fields.index("證券代號"), fields.index("收盤價")
    except ValueError:
        print(f"  TWSE 欄位不如預期: {fields}")
        return None, {}

    date_str = resp.get("date", "")
    iso = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}" if len(date_str) == 8 else None

    prices = {}
    for row in table.get("data", []):
        code = str(row[i_code]).strip()
        price = clean_price(row[i_close])
        if code and price:
            prices[code] = price
    return iso, prices


def fetch_tpex_prices() -> tuple[str | None, dict[str, float]]:
    """上櫃收盤價。回傳 (資料日期, {股票代碼: 收盤價})"""
    try:
        data = requests.get(TPEX_URL, timeout=30).json()
    except Exception as e:
        print(f"  TPEx 上櫃取得失敗: {e}")
        return None, {}

    iso = roc_to_iso(data[0].get("Date")) if data else None
    prices = {str(r.get("SecuritiesCompanyCode", "")).strip(): p
              for r in data if (p := clean_price(r.get("Close")))}
    return iso, prices


def fetch_esb_prices() -> tuple[str | None, dict[str, float]]:
    """
    興櫃（第三市場）最新成交價。回傳 (資料日期, {股票代碼: 最新成交價})。

    只採用 LatestPrice，不以 Average（加權均價）頂替：
    兩者是不同的指標，混著存進 close_price 會讓同一支股票的歷史序列基準不一致。
    當日無成交者（LatestPrice 為 0）直接不給價格，而非填補——沒有成交就是沒有價格。
    """
    try:
        data = requests.get(ESB_URL, timeout=30).json()
    except Exception as e:
        print(f"  TPEx 興櫃取得失敗: {e}")
        return None, {}

    iso = roc_to_iso(data[0].get("Date")) if data else None
    prices = {}
    for r in data:
        code = str(r.get("SecuritiesCompanyCode", "")).strip()
        price = clean_price(r.get("LatestPrice"))
        if code and price:
            prices[code] = price
    return iso, prices


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
    print(f"=== 每日股價更新：{date.today()} ===\n")

    # 1. 取得各市場收盤價（各自帶有來源標記的資料日期）
    print("取得上市股票收盤價（TWSE）...")
    twse_date, twse = fetch_twse_prices()
    print(f"  {len(twse)} 支，資料日期 {twse_date or '無'}")

    print("取得上櫃股票收盤價（TPEx 上櫃）...")
    tpex_date, tpex = fetch_tpex_prices()
    print(f"  {len(tpex)} 支，資料日期 {tpex_date or '無'}")

    print("取得興櫃股票收盤價（TPEx 興櫃）...")
    esb_date, esb = fetch_esb_prices()
    print(f"  {len(esb)} 支，資料日期 {esb_date or '無'}")

    sources = [(twse_date, twse), (tpex_date, tpex), (esb_date, esb)]
    if not any(d and p for d, p in sources):
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

    # 3. 寫入 daily_prices，每個市場用自己的資料日期
    #    （各交易所的發布時程不同，硬套系統日期會讓價格落在錯誤的交易日）
    price_rows = []
    for src_date, prices in sources:
        if not src_date or not prices:
            continue
        price_rows += [{"stock_id": sid, "date": src_date, "close_price": p}
                       for sid, p in prices.items() if sid in known]

    print(f"\n符合資料庫的股票：{len(price_rows)} 筆")
    upsert_batch("daily_prices", price_rows)
    print("收盤價寫入完成")

    # 供估值使用的現價：同一支股票若多個來源都有，取資料日期較新者
    all_prices: dict[str, tuple[str, float]] = {}
    for src_date, prices in sources:
        if not src_date:
            continue
        for sid, p in prices.items():
            if sid in known and (sid not in all_prices or src_date > all_prices[sid][0]):
                all_prices[sid] = (src_date, p)

    # 4. 快速更新估值現價與狀態
    print("\n更新估值...")
    update_valuations({sid: p for sid, (_, p) in all_prices.items()})

    print("\n完成！")


if __name__ == "__main__":
    run()
