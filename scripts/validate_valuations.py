"""
validate_valuations.py — 估值結果驗證（內部一致性 + 跨來源比對）

## A. 內部一致性（隨機抽樣 100 支）
  1. 價格順序：cheap < fair < expensive（P/E、P/B、P/S、P/FCF）
  2. status 與 current_price 的對應關係
  3. P/E 倍數在合理範圍（3–200）
  4. 替代模型倍數在合理範圍（P/B: 0.1–50，P/S / P/FCF: 0.1–200）
  5. ttm_eps > 0.5 但 cheap_price 為 null（矛盾空值）
  6. current_price > 0

## B. 跨來源比對（隨機抽樣 10 支 + 錨點股）
  7. 零價格（0 不是價格，是「無成交」偽裝成數字）
  8. 幽靈交易日（我們有、對照來源沒有 → 可能寫入了休市日）
  9. 同日價格不符（→ 日期位移或抓錯來源）

## C. 未還原的資本事件（全市場，近 30 天）
  10. 單日變動超過漲跌幅上限 ±10% 且無除權息記錄
      → 減資／面額分割／換發沒走除權除息公告，兩條還原路徑都接不到，
        歷史股價停在舊股數基準，估值帶整體位移。判準與盲區見該段開頭。

上市／上櫃以 FinMind 逐日比對；**興櫃另走一套判準**——它沒有官方收盤價，
與 FinMind 的差異只是同一個即時快照的不同取樣時點，逐角比對必然週期性誤報。
改以交易所公告的當日最高／最低區間判定，詳見 ESB_LIST_URL 上方的說明。

**為何需要 B**：A 只能驗「內部自洽」。資料是舊的、日期整批位移、單位錯了——
這些錯誤的數字彼此完全自洽，A 的規則會全部通過。
2026-07-17 發現的兩個重大缺陷（上市股價位移一個交易日、10 萬筆零價格）
就是 A 完全抓不到、靠人工跨來源比對才揪出來的。B 即是將該手法自動化。

參見 CLAUDE.md「資料誠信原則」。

發現 critical 問題時以 exit code 1 退出，觸發 GitHub Actions 失敗 Email 通知。
"""

import os
import sys
import time
import random
import requests
import urllib3
from collections import Counter
from datetime import date, timedelta
from dotenv import load_dotenv
from supabase import create_client

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

SAMPLE_SIZE = 100
# status 判斷容許 2% 誤差，避免浮點數舍入造成誤報
TOLERANCE = 0.02

# 跨來源比對：FinMind 免費版每次呼叫需間隔 6.5 秒，抽樣數需控制在合理耗時內
FINMIND_TOKEN     = os.getenv("FINMIND_TOKEN")
FINMIND_API       = "https://api.finmindtrade.com/api/v4/data"
CALL_INTERVAL     = 6.5
PRICE_SAMPLE_SIZE = 10
PRICE_WINDOW_DAYS = 15
# 錨點股：每次「必比」而非碰運氣被隨機抽到。
#
# 原本只有權值股——熟到能一眼看穿，系統性錯誤（整批日期位移、單位錯、來源抓錯）
# 會先在這些名字上露餡。但 2026-07-22 的事故證明這樣不夠：
# 除權還原漏做卻通過驗證，正因為當初挑的四支樣本中，
# 台積電／台塑／國泰金【配股次數為 0】，長榮只配過 0.5 元——
# 樣本裡根本不存在配股這個現象，怎麼驗都會過。
#
# 起因是「高殖利率股估值帶偏移」，問題意識是配息 → 挑了配息大戶 →
# 而成熟公司發現金、成長公司發股票，這個取樣角度系統性地排除了配股股票。
#
# 因此錨點股改為「每種會出事的性格各放一支」，而非清一色的熟面孔。
# 新增股票時請問：這支代表哪一種尚未被涵蓋的現象？
ANCHOR_STOCKS = [
    # 權值股：量級最容易用常識判斷
    "2330", "2317", "2454", "2882", "1301", "2412", "2603", "2891",
    # 連年配股：除權還原的極端案例（大樹近 10 年股本增幅 ≥15% 達 7 次）
    "6469", "2646",
    # 減資：股本反向變動，每股基準同樣會位移（宏亞 −20%、上曜 −31%）
    "1236", "1316",
    # 興櫃半年報：EPS 只有 6/12 兩期，TTM 須用 2 期而非 4 期
    "1260", "1293",
    # KY 股：海外財報結構不同
    "1256",
]
# 收盤價比對容許 1 分錢誤差（雙方四捨五入位數可能不同）
PRICE_EPSILON     = 0.011

# 興櫃改用「官方當日最高／最低區間」判定，不與 FinMind 逐角比對。
#
# 興櫃沒有官方收盤價：交易所歷史行情只公布最高／最低／均價，唯一的最後成交價
# 是 tpex_esb_latest_statistics 的【即時快照】，不是定版數字。FinMind 的興櫃資料
# 取自同一個快照（實證：其 open 等於交易所前一日均價、max/min 與官方逐筆相符），
# 差別只在取樣時點。
# 2026-07-27 抽樣 2026-07-23 的 8 支興櫃，3 支與 FinMind 不符且方向雙向
# （4553 我們 17.2／FinMind 16.95、7898 我們 393.5／FinMind 395.5），
# 每一筆都落在官方當日區間內。我們的快照取自台北 15:56，已在興櫃收盤 15:00 之後，
# 反而是較定版的一方。拿 FinMind 當基準只會週期性冒假 critical——
# 而誤報久了就會讓人連真警報一起忽略。
ESB_LIST_URL      = "https://www.tpex.org.tw/openapi/v1/tpex_esb_latest_statistics"
ESB_HISTORY_URL   = "https://www.tpex.org.tw/www/zh-tw/emerging/historical"
TPEX_HEADERS      = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.tpex.org.tw/"}
# TPEx 憑證缺 Subject Key Identifier，新版 OpenSSL 會拒絕；比照 audit_external.py
# 對 TPEx 端點關閉驗證（同一個既有取捨，不在這裡另闢一套）
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def fetch_all_stock_ids() -> list[str]:
    """分頁讀取所有 valuations 的 stock_id"""
    ids, page_size, offset = [], 1000, 0
    while True:
        resp = (supabase.table("valuations")
                .select("stock_id")
                .range(offset, offset + page_size - 1)
                .execute())
        ids.extend(r["stock_id"] for r in resp.data)
        if len(resp.data) < page_size:
            break
        offset += page_size
    return ids


def fetch_sample_rows(stock_ids: list[str]) -> list[dict]:
    """批次讀取抽樣股票的估值詳情"""
    rows = []
    cols = (
        "stock_id,current_price,status,"
        "ttm_eps,cheap_pe,fair_pe,expensive_pe,"
        "cheap_price,fair_price,expensive_price,"
        "pb_book_value,pb_cheap_pb,pb_fair_pb,pb_expensive_pb,"
        "pb_cheap_price,pb_fair_price,pb_expensive_price,pb_status,"
        "ps_revenue_per_share,ps_cheap_ps,ps_fair_ps,ps_expensive_ps,"
        "ps_cheap_price,ps_fair_price,ps_expensive_price,ps_status,"
        "pfcf_per_share,pfcf_cheap_pfcf,pfcf_fair_pfcf,pfcf_expensive_pfcf,"
        "pfcf_cheap_price,pfcf_fair_price,pfcf_expensive_price,pfcf_status"
    )
    for i in range(0, len(stock_ids), 100):
        batch = stock_ids[i:i + 100]
        resp = supabase.table("valuations").select(cols).in_("stock_id", batch).execute()
        rows.extend(resp.data)
    return rows


def check_price_order(sid: str, model: str, cheap, fair, expensive) -> list[tuple]:
    """驗證 cheap < fair < expensive，三值都不為 null 才檢查"""
    if None in (cheap, fair, expensive):
        return []
    if not (cheap < fair < expensive):
        return [(sid, "critical",
                 f"{model} 價格順序錯誤: cheap={cheap} fair={fair} expensive={expensive}")]
    return []


def check_status_consistency(sid: str, model: str, status: str | None,
                              cp: float | None, cheap, fair) -> list[tuple]:
    """驗證 status 與 current_price 的對應（允許 TOLERANCE 容差）"""
    if not status or cp is None or None in (cheap, fair):
        return []
    issues = []
    if status == "便宜" and cp > cheap * (1 + TOLERANCE):
        issues.append((sid, "critical",
                        f"{model} status=便宜 但 current_price={cp} > cheap_price={cheap}"))
    elif status == "合理":
        if cp < cheap * (1 - TOLERANCE) or cp > fair * (1 + TOLERANCE):
            issues.append((sid, "warning",
                           f"{model} status=合理 但 current_price={cp} 超出範圍 [{cheap}, {fair}]"))
    elif status == "昂貴" and cp < fair * (1 - TOLERANCE):
        issues.append((sid, "critical",
                        f"{model} status=昂貴 但 current_price={cp} < fair_price={fair}"))
    return issues


def check_multiplier_range(sid: str, label: str, val,
                            lo: float, hi: float) -> list[tuple]:
    if val is None:
        return []
    if not (lo <= val <= hi):
        return [(sid, "warning", f"{label}={val} 超出合理範圍 [{lo}, {hi}]")]
    return []


def validate(row: dict) -> list[tuple]:
    sid = row["stock_id"]
    cp  = row.get("current_price")
    issues = []

    # --- current_price > 0 ---
    if cp is not None and cp <= 0:
        issues.append((sid, "critical", f"current_price={cp} ≤ 0"))

    # --- P/E ---
    cheap_p = row.get("cheap_price")
    fair_p  = row.get("fair_price")
    exp_p   = row.get("expensive_price")
    issues += check_price_order(sid, "P/E", cheap_p, fair_p, exp_p)
    issues += check_status_consistency(sid, "P/E", row.get("status"), cp, cheap_p, fair_p)
    for col, lo, hi in [("cheap_pe", 3, 200), ("fair_pe", 3, 200), ("expensive_pe", 3, 200)]:
        issues += check_multiplier_range(sid, col, row.get(col), lo, hi)

    # 矛盾空值：P/E 帶算得出來（模型成立）且 TTM EPS 為正，就不該沒有目標價。
    #
    # cheap_pe 這個條件不可省。cheap_pe 為 null 代表 P/E 樣本不足、模型本來就
    # 不存在，那不是矛盾而是正常狀態——2026-07-28 起 calculate_valuation 對這種
    # 股票會把模型產物一律清成 null、只保留 ttm_eps 這個事實
    # （見 facts_only_result）。少了這個條件，全庫 56 列合法狀態會每週報 warning，
    # 而週期性誤報最後只會讓人連真警報一起忽略。
    ttm = row.get("ttm_eps")
    if ttm and ttm > 0.5 and row.get("cheap_pe") is not None and cheap_p is None:
        issues.append((sid, "warning",
                       f"ttm_eps={ttm} > 0.5 且有 P/E 帶，但 cheap_price 為 null"))

    # --- P/B ---
    issues += check_price_order(sid, "P/B",
                                row.get("pb_cheap_price"),
                                row.get("pb_fair_price"),
                                row.get("pb_expensive_price"))
    issues += check_status_consistency(sid, "P/B", row.get("pb_status"), cp,
                                       row.get("pb_cheap_price"), row.get("pb_fair_price"))
    for col in ("pb_cheap_pb", "pb_fair_pb", "pb_expensive_pb"):
        issues += check_multiplier_range(sid, col, row.get(col), 0.1, 50)

    # --- P/S ---
    issues += check_price_order(sid, "P/S",
                                row.get("ps_cheap_price"),
                                row.get("ps_fair_price"),
                                row.get("ps_expensive_price"))
    issues += check_status_consistency(sid, "P/S", row.get("ps_status"), cp,
                                       row.get("ps_cheap_price"), row.get("ps_fair_price"))
    for col in ("ps_cheap_ps", "ps_fair_ps", "ps_expensive_ps"):
        issues += check_multiplier_range(sid, col, row.get(col), 0.1, 200)

    # --- P/FCF ---
    issues += check_price_order(sid, "P/FCF",
                                row.get("pfcf_cheap_price"),
                                row.get("pfcf_fair_price"),
                                row.get("pfcf_expensive_price"))
    issues += check_status_consistency(sid, "P/FCF", row.get("pfcf_status"), cp,
                                       row.get("pfcf_cheap_price"), row.get("pfcf_fair_price"))
    for col in ("pfcf_cheap_pfcf", "pfcf_fair_pfcf", "pfcf_expensive_pfcf"):
        issues += check_multiplier_range(sid, col, row.get(col), 0.1, 200)

    return issues


# ─────────────── B. 跨來源比對 ───────────────

def finmind_prices(stock_id: str, start: str) -> dict[str, float]:
    """
    FinMind 收盤價 {日期: 收盤價}。

    FinMind 對「當日無成交」回傳 close = 0，那是缺值不是價格，一律排除，
    否則會把我們正確的「不寫入」誤判為缺漏。
    """
    params = {"dataset": "TaiwanStockPrice", "data_id": stock_id,
              "start_date": start, "token": FINMIND_TOKEN}
    try:
        resp = requests.get(FINMIND_API, params=params, timeout=30).json()
    except Exception as e:
        print(f"  ⚠️  FinMind 請求失敗（{stock_id}）: {e}")
        return {}
    if resp.get("status") != 200:
        print(f"  ⚠️  FinMind 回應異常（{stock_id}）: {resp.get('msg')}")
        return {}
    return {r["date"]: float(r["close"]) for r in resp.get("data", [])
            if r.get("close") is not None and float(r["close"]) > 0}


def our_prices(stock_id: str, start: str) -> dict[str, float]:
    """資料庫收盤價 {日期: 收盤價}（帶 stock_id 走主鍵前綴，不會逾時）"""
    resp = (supabase.table("daily_prices")
            .select("date,close_price")
            .eq("stock_id", stock_id)
            .gte("date", start)
            .order("date")
            .execute())
    return {r["date"]: float(r["close_price"]) for r in resp.data}


def zero_price_issues(stock_id: str, ours: dict[str, float]) -> list[tuple]:
    """零價格：0 是「無成交」不是價格（2026-07-17 曾有 10.3 萬筆）"""
    return [(stock_id, "critical", f"{d} 收盤價為 {p}（0 不是價格，應不寫入）")
            for d, p in sorted(ours.items()) if p <= 0]


def missing_day_issues(stock_id: str, ours: dict, theirs: dict,
                       latest_ok: str) -> list[tuple]:
    """對照來源有、我們沒有的交易日（可能是下載遺漏，非致命）"""
    missing = [d for d in sorted(set(theirs) - set(ours)) if d <= latest_ok]
    if not missing:
        return []
    return [(stock_id, "warning",
             f"缺少 {len(missing)} 個交易日的股價：{', '.join(missing[:3])}"
             + ("…" if len(missing) > 3 else ""))]


def check_price_source(stock_id: str, start: str, latest_ok: str) -> list[tuple]:
    """
    以 FinMind 為對照，驗證資料庫股價的正確性（上市／上櫃；興櫃見 check_price_esb）。

    latest_ok：比對截止日。最新一兩天可能只是排程尚未執行或來源尚未發布，
    不應視為缺漏，故排除。
    """
    ours = our_prices(stock_id, start)
    theirs = finmind_prices(stock_id, start)
    if not theirs:
        return []   # 對照組取不到就無從比對，不誤報

    issues = zero_price_issues(stock_id, ours)

    # 幽靈交易日：我們有、FinMind 沒有 → 可能把休市日寫成交易日
    for d in sorted(set(ours) - set(theirs)):
        if d <= latest_ok:
            issues.append((stock_id, "critical",
                           f"{d} 我們有股價 {ours[d]}，但 FinMind 無該日資料（疑為休市日）"))

    # 同日價格不符 → 日期位移或抓錯來源
    for d in sorted(set(ours) & set(theirs)):
        if abs(ours[d] - theirs[d]) > PRICE_EPSILON:
            issues.append((stock_id, "critical",
                           f"{d} 收盤價不符：我們 {ours[d]} vs FinMind {theirs[d]}"))

    return issues + missing_day_issues(stock_id, ours, theirs, latest_ok)


def esb_codes() -> set[str]:
    """興櫃股票代碼集合（整批端點，一次呼叫）"""
    resp = requests.get(ESB_LIST_URL, timeout=30, verify=False)
    resp.raise_for_status()
    return {str(r.get("SecuritiesCompanyCode", "")).strip() for r in resp.json()}


def esb_ranges(stock_id: str, start: str) -> dict[str, tuple[float, float]]:
    """
    興櫃官方歷史行情 {日期: (最低, 最高)}，只含當日確實有成交的交易日。

    端點一次回傳整月，故依比對視窗跨越的月份逐月查詢。
    抓取失敗直接讓例外往上拋——「來源故障」不可偽裝成「該日沒有資料」。
    """
    out: dict[str, tuple[float, float]] = {}
    y, m = int(start[:4]), int(start[5:7])
    today = date.today()
    while (y, m) <= (today.year, today.month):
        resp = requests.get(ESB_HISTORY_URL, headers=TPEX_HEADERS, timeout=30, verify=False,
                            params={"code": stock_id, "date": f"{y}/{m:02d}/01",
                                    "id": "", "response": "json"})
        resp.raise_for_status()
        tables = resp.json().get("tables") or [{}]
        for roc, volume, _amount, high, low, *_ in tables[0].get("data") or []:
            if not int(volume.replace(",", "")):
                continue        # 當日無成交＝沒有價格，不是缺漏
            yy, mm, dd = roc.split("/")          # 民國年一律 +1911（見 CLAUDE.md）
            iso = f"{int(yy) + 1911}-{mm}-{dd}"
            if iso >= start:
                out[iso] = (float(low), float(high))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def check_price_esb(stock_id: str, start: str, latest_ok: str) -> list[tuple]:
    """
    興櫃：以交易所公告的當日最高／最低區間驗證收盤價。

    盲區（務必知道）：區間內的錯誤抓不到——例如把當日某個中間成交價
    或加權均價存成收盤價，都會通過。這道防線只保證「不可能超出當日成交範圍」，
    以及交易日的有無。興櫃本來就沒有唯一正解的收盤價，能驗的僅止於此；
    「不得以另一個指標頂替」要靠 daily_price_update.fetch_esb_prices 的
    只取 LatestPrice 來守，不是靠這裡。
    """
    ours   = our_prices(stock_id, start)
    theirs = esb_ranges(stock_id, start)
    if not theirs:
        return []   # 對照組取不到就無從比對，不誤報

    issues = zero_price_issues(stock_id, ours)
    for d, p in sorted(ours.items()):
        if p <= 0:
            continue                     # 已由 zero_price_issues 記錄
        if d not in theirs:
            if d <= latest_ok:           # 幽靈交易日
                issues.append((stock_id, "critical",
                               f"{d} 我們有股價 {p}，但交易所該日無成交紀錄"))
        elif not theirs[d][0] - PRICE_EPSILON <= p <= theirs[d][1] + PRICE_EPSILON:
            issues.append((stock_id, "critical",
                           f"{d} 收盤價 {p} 超出交易所公告區間 "
                           f"{theirs[d][0]}–{theirs[d][1]}"))

    return issues + missing_day_issues(stock_id, ours, theirs, latest_ok)


# ─────────────── C. 未還原的資本事件 ───────────────
#
# 減資、面額分割、股份換發都會讓股價一夜之間跳動數倍，但**不走除權除息公告**，
# 兩條還原路徑都接不到：交易所的 TWT49U／tpex_exright_daily 只收除權除息，
# dividends 自算公式也只涵蓋配息與配股。
#
# 後果：歷史股價停在事件前的舊股數基準，而每股基準值（每股營收／FCF／淨值）
# 已換算成新股數 —— 分子分母基準不一致，歷史倍數帶整體位移，目標價跟著錯。
# 減資會使目標價偏低（誤判「昂貴」），分割則偏高（誤判「便宜」、衝上排行榜）。
# 實例 1435 中福：2026-06-18 減資換發，5.56 → 14.10（+153%），
# ps_status 判「昂貴」時現價 25.5 對昂貴價 2.64，歷史帶被壓低約 2.5 倍。
#
# 判準：單日變動超過台股漲跌幅上限 ±10%，且該區間沒有任何還原事件。
# 超過上限只有三種可能 —— 資本事件、無漲跌幅限制的標的、髒資料，三者都該看。
#
# 盲區（新增稽核規則先問「這條規則看不到什麼」）：
#   1. 只能查近 3 個月。更早的資料已瘦身成週採樣（見 calculate_valuation.to_weekly），
#      相鄰兩點相隔一週，10% 門檻失去意義。歷史存量需另行普查。
#   2. 興櫃無漲跌幅限制，逐筆議價本就可能單日翻倍 → 三層過濾（見 check_capital_events）。
#   3. 新上市首五日無漲跌幅限制 → 跳過該股在窗口內的前五筆。
#   4. 抓不到與除權息同日發生的資本事件（因子被部分還原，落在門檻內）。
#   5. 抓不到 10% 以內的小型資本變動。
#   6. 窗口最後幾天的事件還沒有足夠的後續價格可判定是否回復，會照報 —— 寧可早報。
#
# 嚴重度一律 warning：本檢查無法區分「資本事件」與「停牌復牌／處置股」，
# 設成 critical 會讓每週驗證常態性紅燈，而誤報久了就會讓人連真警報一起忽略
# （同 audit_external 的門檻取捨）。
CAPITAL_EVENT_DAYS  = 30      # 掃描窗口（每週跑一次，留兩週餘裕）
CAPITAL_EVENT_LIMIT = 0.105   # 漲跌幅上限 10% + 0.5% 緩衝（避免浮點與參考價舍入誤報）
CAPITAL_EVENT_MAX   = 2       # 同股觸發上限；超過視為無漲跌幅限制或流動性極差，非一次性事件
CAPITAL_EVENT_LOOK  = 5       # 事件後回看幾個交易日，判定價格是否回復
CALENDAR_MIN_ROWS   = 1500    # 全市場單日筆數達此數才算「完整交易日」，用以排除瘦身後的週採樣日


def recovered(seq: list[tuple[str, float]], idx: int, base: float) -> bool:
    """
    事件後 CAPITAL_EVENT_LOOK 個交易日內，價格是否回到事件前水準。

    這是本檢查最關鍵的一層過濾，判準直指本質：
    **資本事件造成的是永久性的價格位移，不是波動。**
    減資換發後股價再也回不到換發前的水準（1435 中福 5.56 → 14.10 後續維持 25 元附近），
    而無漲跌幅限制的標的只是上下震盪（7814 海昌生技 −20.5% 隔天就彈回 +21.7%）。

    用行為判定而非市場別判定，是因為市場別根本查不可靠：
    TWSE MI_INDEX 是當日收盤行情，排程在早上 09:00 跑時回傳 0 筆（上市股會整批漏檢）；
    TPEx 上櫃報價端點實測 10,173 筆，遠多於上櫃家數；
    興櫃基本資料只有 359 筆，7814、6883 這類明顯無漲跌幅限制的標的都不在其中。
    """
    lo, hi = base * (1 - CAPITAL_EVENT_LIMIT), base * (1 + CAPITAL_EVENT_LIMIT)
    return any(lo <= p <= hi for _, p in seq[idx + 1: idx + 1 + CAPITAL_EVENT_LOOK])


def adjustment_dates(start: str) -> dict[str, set[str]]:
    """
    {股票: 還原事件日}。必須同時涵蓋 back_adjust 的兩條路徑，否則會把
    已還原的正常除權息報成未還原斷崖：
      - ex_right_factors：交易所官方因子（上櫃端點只有當日，2026-07-22 起才逐日累積）
      - dividends：查無官方值時的自算 fallback，現階段上櫃股幾乎全靠它
    """
    out: dict[str, set[str]] = {}
    for table in ("ex_right_factors", "dividends"):
        offset = 0
        while True:
            rows = (supabase.table(table).select("stock_id,ex_date")
                    .gte("ex_date", start).order("stock_id").order("ex_date")
                    .range(offset, offset + 999).execute().data)
            for r in rows:
                if r["ex_date"]:
                    out.setdefault(r["stock_id"], set()).add(r["ex_date"])
            if len(rows) < 1000:
                break
            offset += 1000
    return out


def recent_prices(start: str) -> dict[str, list[tuple[str, float]]]:
    """
    {股票: [(日期, 收盤價)]}，日期升冪。0 不是價格（見 zero_price_issues），排除。

    用 stock_id 當游標而非 offset 分頁：daily_prices 有 117 萬列且只有
    (stock_id, date) 主鍵索引，沒有 date 單獨索引 —— offset 分頁要 Postgres
    掃過前面所有列，實測到數萬列就 `canceling statement due to statement timeout`。
    游標式查詢每次都是主鍵前綴的小範圍 seek，offset 恆為 0。
    """
    out: dict[str, list[tuple[str, float]]] = {}
    cursor = ""
    while True:
        rows = (supabase.table("daily_prices").select("stock_id,date,close_price")
                .gte("stock_id", cursor).gte("date", start)
                .order("stock_id").order("date")
                .range(0, 999).execute().data)
        if not rows:
            break
        for r in rows:
            if r["close_price"] and float(r["close_price"]) > 0:
                out.setdefault(r["stock_id"], []).append((r["date"], float(r["close_price"])))
        if len(rows) < 1000:
            break
        # 最後一支可能被截斷在頁中間，丟棄後從它重讀
        # （單支 30 天內最多 22 列，遠小於一頁，不會卡住游標）
        tail = rows[-1]["stock_id"]
        out.pop(tail, None)
        cursor = tail
    return out


def trading_calendar(prices: dict[str, list[tuple[str, float]]]) -> dict[str, str]:
    """
    {某交易日: 前一個交易日}。

    兩層條件缺一不可：
      - 全市場當日筆數 ≥ CALENDAR_MIN_ROWS，排除瘦身後只剩零星資料的日子
      - 兩日實際相隔 ≤ 4 天（週末＋一天假日），排除週採樣區間
    少了第二層，「上週最後交易日 → 本週最後交易日」會被當成相鄰交易日，
    整段歷史被套上漲跌幅門檻（實測會灌出 4.8 萬筆誤報）。
    """
    count = Counter(d for seq in prices.values() for d, _ in seq)
    days = sorted(d for d, n in count.items() if n >= CALENDAR_MIN_ROWS)
    return {days[i]: days[i - 1] for i in range(1, len(days))
            if (date.fromisoformat(days[i]) - date.fromisoformat(days[i - 1])).days <= 4}


def check_capital_events() -> list[tuple]:
    """未還原的資本事件（減資／面額分割／換發）。判準與盲區見本段開頭說明。"""
    start = (date.today() - timedelta(days=CAPITAL_EVENT_DAYS)).strftime("%Y-%m-%d")
    print(f"\n=== 未還原的資本事件（{start} 起）===")

    prices = recent_prices(start)
    calendar = trading_calendar(prices)
    adj = adjustment_dates(start)
    delisted = delisted_codes()
    esb = esb_codes()
    trading_days = sorted(calendar)
    first_day = trading_days[0] if trading_days else start

    hits: list[tuple] = []
    n_recovered = 0
    for sid, seq in prices.items():
        if sid in delisted or sid in esb:      # 下市股價格凍結；興櫃無漲跌幅限制
            continue
        px = dict(seq)
        # 新上市首五日無漲跌幅限制 → 跳過該股在窗口內的前五筆。
        # 但「窗口內才首次出現」不等於新上市：低流動性股票沒成交就沒價格，
        # 起點同樣晚於窗口第一天。兩者的差別在於新上市股自掛牌起【每個交易日都有價】，
        # 稀疏股中間有洞。少了這一層，1435 中福（06-12、15、16 皆無成交）會被
        # 誤判為新上市，連同 06-18 的減資換發一起被跳過——真訊號就這樣漏掉。
        after = [d for d in trading_days if d >= seq[0][0]]
        is_new = seq[0][0] > first_day and len(seq) >= len(after)
        skip = {d for d, _ in seq[:5]} if is_new else set()
        for i, (d1, p1) in enumerate(seq):
            d0 = calendar.get(d1)
            if not d0 or d0 not in px or d1 in skip:
                continue                      # 該股當天缺價 → 兩筆並不相鄰，不可比
            p0 = px[d0]
            ratio = p1 / p0
            if abs(ratio - 1) <= CAPITAL_EVENT_LIMIT:
                continue
            if any(d0 < e <= d1 for e in adj.get(sid, ())):
                continue                      # 除權息已還原
            if recovered(seq, i, p0):
                n_recovered += 1              # 價格彈回＝波動，不是資本事件
                continue
            hits.append((sid, d0, d1, p0, p1, ratio))

    freq = Counter(h[0] for h in hits)
    kept = [h for h in hits if freq[h[0]] <= CAPITAL_EVENT_MAX]
    noisy = sorted({h[0] for h in hits if freq[h[0]] > CAPITAL_EVENT_MAX})

    print(f"  掃描 {len(prices)} 支、{len(calendar)} 個相鄰交易日對；"
          f"價格隨後回復而排除 {n_recovered} 筆")
    print(f"  觸發 {len(hits)} 筆 → 過濾同股 >{CAPITAL_EVENT_MAX} 次後 {len(kept)} 筆")
    if noisy:
        print(f"  觸發過頻而排除（多半無漲跌幅限制或處置中）：{', '.join(noisy)}")

    return [(sid, "warning",
             f"{d1} 單日 {(ratio - 1) * 100:+.1f}%（{p0} → {p1}），"
             f"超過漲跌幅上限且無除權息記錄——"
             f"可能是{'減資／換發' if ratio > 1 else '面額分割'}未還原，歷史估值帶會整體位移")
            for sid, d0, d1, p0, p1, ratio in sorted(kept, key=lambda x: x[2])]


def delisted_codes() -> set[str]:
    """已下市股票代號（價格凍結在最後交易日，跳空無意義）"""
    out: set[str] = set()
    offset = 0
    while True:
        rows = (supabase.table("stocks").select("stock_id")
                .not_.is_("delisted_at", "null").order("stock_id")
                .range(offset, offset + 999).execute().data)
        out |= {r["stock_id"] for r in rows}
        if len(rows) < 1000:
            return out
        offset += 1000


def run_cross_source_check(all_ids: list[str]) -> list[tuple]:
    # 錨點股一定納入（存在於資料庫者），再以隨機抽樣補足其餘名額
    anchors = [s for s in ANCHOR_STOCKS if s in set(all_ids)]
    pool    = [s for s in all_ids if s not in anchors]
    extra   = random.sample(pool, min(PRICE_SAMPLE_SIZE, len(pool)))
    sample  = anchors + extra
    start   = (date.today() - timedelta(days=PRICE_WINDOW_DAYS)).strftime("%Y-%m-%d")
    # 最近 2 天不比對：排程可能尚未執行，或交易所尚未發布
    latest_ok = (date.today() - timedelta(days=2)).strftime("%Y-%m-%d")

    esb        = esb_codes()
    n_finmind  = sum(s not in esb for s in sample)

    print(f"\n=== 跨來源比對（{len(sample)} 支，{start} 起）===")
    print(f"  上市／上櫃 {n_finmind} 支與 FinMind 逐日比對，"
          f"興櫃 {len(sample) - n_finmind} 支改用交易所區間判準")
    print(f"預估耗時約 {n_finmind * CALL_INTERVAL / 60:.1f} 分鐘\n")

    issues = []
    for i, sid in enumerate(sample, 1):
        is_esb = sid in esb
        found  = (check_price_esb if is_esb else check_price_source)(sid, start, latest_ok)
        mark   = "OK" if not found else f"{len(found)} 個問題"
        print(f"  [{i}/{len(sample)}] {sid}{'（興櫃）' if is_esb else ''}: {mark}")
        issues.extend(found)
        if not is_esb and i < len(sample):
            time.sleep(CALL_INTERVAL)   # 只有 FinMind 需要節流，交易所端點不必
    return issues


def main():
    print("=== A. 估值結果一致性驗證 ===\n")

    all_ids = fetch_all_stock_ids()
    sample  = random.sample(all_ids, min(SAMPLE_SIZE, len(all_ids)))
    print(f"資料庫總股票數：{len(all_ids)}，本次抽樣：{len(sample)} 支\n")

    rows   = fetch_sample_rows(sample)
    issues = []
    for row in rows:
        issues.extend(validate(row))
    print(f"內部一致性檢查完成，抽樣 {len(rows)} 支")

    # B. 跨來源比對（沒有 FinMind token 就跳過，但要明講——
    #    少了這段等於只驗內部一致性，抓不到日期位移與陳舊資料）
    if FINMIND_TOKEN:
        issues.extend(run_cross_source_check(all_ids))
    else:
        print("\n⚠️  未設定 FINMIND_TOKEN，跳過跨來源比對")
        print("    僅檢查內部一致性，無法偵測日期位移、資料陳舊、單位錯誤")

    # C. 未還原的資本事件（不需 FinMind，全市場掃描）
    issues.extend(check_capital_events())

    critical = [(s, m) for s, sev, m in issues if sev == "critical"]
    warnings = [(s, m) for s, sev, m in issues if sev == "warning"]

    print(f"\n=== 驗證結果 ===")
    print(f"  嚴重問題（critical）：{len(critical)} 筆")
    print(f"  警告（warning）    ：{len(warnings)} 筆\n")

    if critical:
        print("【嚴重問題】")
        for sid, msg in critical:
            print(f"  [{sid}] {msg}")
        print()

    if warnings:
        print("【警告】")
        for sid, msg in warnings:
            print(f"  [{sid}] {msg}")
        print()

    if not issues:
        print("✅ 所有驗證通過，估值結果一致性良好。")
    elif not critical:
        print("⚠️  有警告但無嚴重問題，請人工確認。")
    else:
        print("❌ 發現嚴重問題，請立即檢查估值計算邏輯。")
        sys.exit(1)


if __name__ == "__main__":
    main()
