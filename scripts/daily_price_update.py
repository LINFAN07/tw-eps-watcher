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
from collections import defaultdict
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


ABSENT_DAYS = 21   # 缺席超過這麼多個日曆日（約 15 個交易日）才判定下市


def mark_delisted(seen: set[str], known: set[str], data_date: str):
    """
    以「今天有沒有出現在交易所全市場清單」維護 stocks.last_seen_date / delisted_at。

    為什麼要這個欄位：下市股的價格永遠停在最後一個交易日，但目標價仍隨財報更新，
    折價越算越誇張，於是專門往排行榜頂端跑。2026-07-21 實測 2,448 檔中有 120 檔
    已下市，其中 6 檔佔據 P/E 便宜榜（前 6 名中 4 名）。

    設計取捨：
    - 用日曆日門檻而非「連續 N 次缺席」，因為排程本身可能漏跑（本 repo 的排程
      常態遲到，改過 cron 隔天甚至整天不觸發），用次數會把漏跑算成缺席。
    - 重新出現即清除 delisted_at：停牌復牌不需人工介入，也能自我修正誤判。
    - 呼叫端必須確認【所有市場都抓取成功】才呼叫——否則來源故障會被判成整批下市。
    """
    # 必須用 UPDATE 而非 upsert：upsert 會先嘗試 INSERT，而 stocks.name / market
    # 是 NOT NULL，只帶 stock_id 的列會在衝突解析前就違反約束。
    # 代碼清單分批送出，避免 URL 過長。
    today_seen = sorted(seen & known)
    for i in range(0, len(today_seen), 200):
        (supabase.table("stocks")
         .update({"last_seen_date": data_date, "delisted_at": None})
         .in_("stock_id", today_seen[i:i + 200]).execute())

    cutoff = (date.fromisoformat(data_date) - timedelta(days=ABSENT_DAYS)).isoformat()
    resp = (supabase.table("stocks")
            .update({"delisted_at": data_date})
            .lt("last_seen_date", cutoff)      # last_seen_date 為 NULL 者不受影響
            .is_("delisted_at", "null")
            .execute())
    if resp.data:
        print(f"  新標記下市 {len(resp.data)} 檔："
              f"{'、'.join(r['stock_id'] for r in resp.data[:10])}"
              f"{' …' if len(resp.data) > 10 else ''}")
    print(f"  在市 {len(today_seen)} 檔，缺席逾 {ABSENT_DAYS} 日者已標記下市")


def update_market(sources: list[tuple[str, str | None, dict]], current: dict[str, str]):
    """
    以「今天出現在哪個交易所的清單」維護 stocks.market。

    為什麼要這個欄位：原本 init_download.py 取 FinMind 的 `market_category`，
    但該資料集根本沒有這個欄位名（實際叫 `type`），fallback 讓全表 2,540 筆
    一律寫成「未知」。市場別缺席的代價是沉默的——沒有它，
    稽核無法分層抽樣（上市與上櫃的資料品質天差地遠，見 ex_right_factors
    的涵蓋率：上市 1,031/1,093 家回溯 2016 年，上櫃僅 83/887 家且只有 2025 年起），
    前端也無法讓使用者按市場篩選。

    以交易所清單為準而非 FinMind：這裡的三份清單就是市場別的定義本身，
    且每日更新已經抓好，回填不需要任何額外的 API 呼叫。
    轉板（興櫃 → 上櫃 → 上市）會自然反映，不需人工介入。

    同 mark_delisted，呼叫端必須確認【所有市場都抓取成功】——
    少一個市場就回填，等於把該市場的股票全部寫成錯誤的市場別或維持舊值。

    current 為 {股票代碼: 現有 market}，由呼叫端讀名冊時一併帶入
    （既要用它濾掉不在名冊的代碼，也要比對新舊值，不必為同一張表再掃一次）。
    """
    # 同一支只會出現在一個市場；真有重複時以清單順序（上市 > 上櫃 > 興櫃）為準
    latest = {}
    for market, _, prices in sources:
        for sid in prices:
            if sid in current:
                latest.setdefault(sid, market)

    # 只寫有變動的：每天無謂地 UPDATE 全表 2,400 列既浪費配額也蓋掉 updated_at 語意
    changed = defaultdict(list)
    for sid, market in latest.items():
        if current.get(sid) != market:
            changed[market].append(sid)

    if not changed:
        print("  市場別無變動")
        return

    # 必須用 UPDATE 而非 upsert：upsert 會先嘗試 INSERT，而 stocks.name 是 NOT NULL，
    # 只帶 stock_id 的列會在衝突解析前就違反約束。
    for market, sids in changed.items():
        for i in range(0, len(sids), 200):
            (supabase.table("stocks").update({"market": market})
             .in_("stock_id", sids[i:i + 200]).execute())
        moved = [s for s in sids if current.get(s) not in (None, "未知")]
        print(f"  {market}: {len(sids)} 檔"
              + (f"（其中 {len(moved)} 檔轉板：{'、'.join(moved[:5])}）" if moved else ""))


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
        # price_date 存來源自己回報的資料日期，不用系統日期
        update = {"stock_id": sid, "current_price": round(price, 2),
                  "price_date": src_date, "updated_at": now}
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
    for market, label, fetch in (("TWSE",     "上市（TWSE）", fetch_twse_prices),
                                 ("TPEx",     "上櫃（TPEx）", fetch_tpex_prices),
                                 ("Emerging", "興櫃（TPEx）", fetch_esb_prices)):
        print(f"取得{label}收盤價...")
        try:
            src_date, prices = fetch()
            print(f"  {len(prices)} 支，資料日期 {src_date or '無'}")
            # 市場別隨資料一起帶下去：抓取失敗時該來源不會進 sources，
            # 若靠迴圈順序推市場別會整批錯位。
            sources.append((market, src_date, prices))
        except FetchError as e:
            print(f"  ❌ {label} 抓取失敗：{e}")
            failed.append(label)

    if failed:
        print(f"\n❌ 以下來源抓取失敗，資料不完整：{'、'.join(failed)}")
        print("   已取得的部分仍會寫入，但工作將以失敗結束以觸發通知。")

    if not sources or not any(d and p for _, d, p in sources):
        if failed:
            sys.exit(1)          # 全部失敗 ≠ 休市，必須通報
        print("\n今日無交易資料（休市），結束。")
        return

    # 2. 過濾出資料庫中已有的股票（分頁繞過 1000 筆上限）
    #    順便帶回 market：update_market() 要比對新舊值才知道哪些需要寫，
    #    不然就是為了同一張表再掃一次全表。排序確保跨頁不重複、不遺漏。
    known_market, offset = {}, 0
    while True:
        resp = (supabase.table("stocks").select("stock_id,market")
                .order("stock_id").range(offset, offset + 999).execute())
        known_market.update({r["stock_id"]: r["market"] for r in resp.data})
        if len(resp.data) < 1000:
            break
        offset += 1000
    known = set(known_market)

    # 3. 寫入 daily_prices，每個市場用自己的資料日期
    #    （各交易所的發布時程不同，硬套系統日期會讓價格落在錯誤的交易日）
    price_rows = []
    for _, src_date, prices in sources:
        if not src_date or not prices:
            continue
        price_rows += [{"stock_id": sid, "date": src_date, "close_price": p}
                       for sid, p in prices.items() if sid in known]

    print(f"\n符合資料庫的股票：{len(price_rows)} 筆")
    upsert_batch("daily_prices", price_rows)
    print("收盤價寫入完成")

    # 供估值使用的現價：同一支股票若多個來源都有，取資料日期較新者
    all_prices: dict[str, tuple[str, float]] = {}
    for _, src_date, prices in sources:
        if not src_date:
            continue
        for sid, p in prices.items():
            if sid in known and (sid not in all_prices or src_date > all_prices[sid][0]):
                all_prices[sid] = (src_date, p)

    # 4. 下市偵測（只在所有市場都抓取成功時執行）
    #    少一個市場就做判定，等於把「來源故障」寫成「整個市場下市」——
    #    那比不做判定嚴重得多，故寧可跳過一天。
    if failed:
        print("\n有來源抓取失敗，跳過下市偵測與市場別回填（避免把故障誤判為下市）")
    else:
        print("\n下市偵測...")
        seen = {sid for _, _, prices in sources for sid in prices}
        mark_delisted(seen, known, max(d for _, d, _ in sources if d))

        print("\n市場別回填...")
        update_market(sources, known_market)

    # 5. 快速更新估值現價與狀態
    print("\n更新估值...")
    update_valuations(all_prices)

    if failed:
        print(f"\n❌ 部分來源抓取失敗（{'、'.join(failed)}），資料不完整。")
        sys.exit(1)

    print("\n完成！")


if __name__ == "__main__":
    run()
