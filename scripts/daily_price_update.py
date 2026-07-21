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
import time
import requests
from datetime import date, datetime, timedelta, timezone
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


class FetchError(Exception):
    """
    來源抓取失敗。

    必須與「休市所以沒資料」嚴格區分：前者是故障、要讓工作失敗並發通知，
    後者是正常狀況。2026-07-14 的事故即因兩者混為一談——
    TPEx 連線中斷（IncompleteRead），fetch 吞掉例外回傳空 dict，
    整個上櫃市場（約 900 支）當日沒有寫入，而工作回報「完成！」，
    缺口三天後才被跨來源比對發現。
    """


def get_json(url: str, retries: int = 3, **kwargs):
    """
    帶重試的 GET。全部重試失敗就拋 FetchError，不可回傳空值——
    一旦回傳空值，呼叫端就無法分辨「休市」與「抓取失敗」。
    """
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            return requests.get(url, timeout=30, **kwargs).json()
        except Exception as e:
            last_error = e
            print(f"  第 {attempt}/{retries} 次請求失敗：{e}")
            if attempt < retries:
                time.sleep(5)
    raise FetchError(f"{url} 連續 {retries} 次失敗：{last_error}")


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
    resp = get_json(TWSE_URL, params={"date": today, "type": "ALL", "response": "json"}, headers=UA)

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
    data = get_json(TPEX_URL)
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
    data = get_json(ESB_URL)
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


# 各估值模型的 (模型代號, 便宜價欄位, 合理價欄位, 狀態欄位)
STATUS_MODELS = [
    ("pe",    "cheap_price",      "fair_price",      "status"),
    ("pb",    "pb_cheap_price",   "pb_fair_price",   "pb_status"),
    ("ps",    "ps_cheap_price",   "ps_fair_price",   "ps_status"),
    ("pfcf",  "pfcf_cheap_price", "pfcf_fair_price", "pfcf_status"),
    ("yield", "yield_cheap_price","yield_fair_price","yield_status"),
]

# 狀態欄位也要讀回來：比對新舊才能記錄「今天跌進便宜區」的變動（status_changes）
_STATUS_COLS = "stock_id," + ",".join(
    col for model in STATUS_MODELS for col in model[1:]
)

# 狀態變動記錄的保留天數。容量吃緊，不可無限累積
STATUS_CHANGE_RETENTION_DAYS = 90


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


def record_status_changes(changes: list[dict], latest_date: str):
    """
    寫入狀態變動並清除保留期以外的舊記錄。

    這是附加功能：status_changes 表若尚未建立（schema.sql 未執行），
    只印警告而不中斷——股價與估值更新才是本工作的核心職責，
    不該因為快報功能未部署就讓整個每日更新失敗。
    """
    if not changes:
        print("估值狀態變動：0 筆")
        return
    try:
        upsert_batch("status_changes", changes)
        # 保留期以資料日期回推，不用系統時間（休市時兩者會脫節）
        cutoff = (date.fromisoformat(latest_date)
                  - timedelta(days=STATUS_CHANGE_RETENTION_DAYS)).isoformat()
        supabase.table("status_changes").delete().lt("date", cutoff).execute()
        print(f"估值狀態變動：{len(changes)} 筆（已清除 {cutoff} 前的記錄）")
    except Exception as e:
        print(f"⚠️  狀態變動記錄寫入失敗（不影響股價更新）：{str(e)[:150]}")
        print("    若尚未建立 status_changes 表，請執行 schema.sql 的對應段落")


def update_valuations(prices: dict[str, tuple[str, float]]):
    """
    快速更新估值現價與狀態（P/E + P/B + P/S + P/FCF + 殖利率）。
    只比對現價與既有目標價，不重算歷史區間（那是 calculate_valuation.py 的職責）。

    prices 的值為 (資料日期, 收盤價)：日期用於狀態變動記錄，
    各市場發布時程不同，必須用該股自己的資料日期而非系統日期。
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

    updates, changes = [], []
    for row in existing:
        sid = row["stock_id"]
        entry = prices.get(sid)
        if not entry:
            continue
        src_date, price = entry
        if not price or price <= 0:
            continue

        # 現價一律更新（含虧損股），各模型狀態依其目標價各自判定
        update = {"stock_id": sid, "current_price": round(price, 2), "updated_at": now}
        for model, cheap_col, fair_col, status_col in STATUS_MODELS:
            new_status = judge_status(price, row.get(cheap_col), row.get(fair_col))
            update[status_col] = new_status

            # 只記錄「便宜/合理/昂貴」之間的真實移動。
            # 與「無法計算」互轉是資料狀態改變（財報更新、模型失效），
            # 不是市場價格造成的變化，混進快報只會製造雜訊。
            old_status = row.get(status_col)
            if (old_status and old_status != new_status
                    and "無法計算" not in (old_status, new_status)):
                changes.append({
                    "stock_id": sid, "date": src_date, "model": model,
                    "from_status": old_status, "to_status": new_status,
                })
        updates.append(update)

    upsert_batch("valuations", updates)
    print(f"估值狀態更新：{len(updates)} 支")

    if updates:
        record_status_changes(changes, max(d for d, _ in prices.values()))


def run():
    print(f"=== 每日股價更新：{date.today()} ===\n")

    # 1. 取得各市場收盤價（各自帶有來源標記的資料日期）
    #    任一來源抓取失敗即讓整個工作失敗——少一個市場就是資料缺口，
    #    絕不可吞掉錯誤後回報成功（2026-07-14 上櫃缺口即因此三天無人知悉）。
    sources, failed = [], []
    for label, fetch in (("上市（TWSE）", fetch_twse_prices),
                         ("上櫃（TPEx）", fetch_tpex_prices),
                         ("興櫃（TPEx）", fetch_esb_prices)):
        print(f"取得{label}收盤價...")
        try:
            src_date, prices = fetch()
            print(f"  {len(prices)} 支，資料日期 {src_date or '無'}")
            sources.append((src_date, prices))
        except FetchError as e:
            print(f"  ❌ {label} 抓取失敗：{e}")
            failed.append(label)

    if failed:
        print(f"\n❌ 以下來源抓取失敗，資料不完整：{'、'.join(failed)}")
        print("   已取得的部分仍會寫入，但工作將以失敗結束以觸發通知。")

    if not sources or not any(d and p for d, p in sources):
        if failed:
            sys.exit(1)          # 全部失敗 ≠ 休市，必須通報
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
    update_valuations(all_prices)

    if failed:
        print(f"\n❌ 部分來源抓取失敗（{'、'.join(failed)}），資料不完整。")
        sys.exit(1)

    print("\n完成！")


if __name__ == "__main__":
    run()
