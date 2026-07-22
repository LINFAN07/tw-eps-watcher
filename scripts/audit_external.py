"""
對外比對稽核：拿交易所官方申報值，驗資料庫裡來自 FinMind 的數字。

為什麼需要這支——現有三道防線各有一塊抓不到的地方：

  - `validate_valuations.py` 的內部一致性規則：錯誤的數字彼此自洽，規則全過。
    它的跨來源段只比對「股價」，且只抽樣 10 支。
  - `audit_cross_check.py`：同一份原始資料用兩條路徑重算。原始資料本身錯了，
    兩條路徑會一起錯，比對照樣通過。
  - `audit_workflows.py`：只看腳本有沒有掛排程，不看數字。

也就是說「EPS 抓錯了」「淨值單位錯了」「累計值被當單季」這類錯誤，
目前沒有任何一道防線會叫。本專案四次事故有三次正是這一類，
且每次都是靠人工跨來源比對才發現的（2026-07-17 現金流累計、股價位移；
2026-07-22 除權未還原）。這支把那個人工動作固定下來。

檢查項目（皆為整批端點，全部跑完約 30 秒）：

  A. 每股盈餘 —— 綜合損益表 t187ap06_*，對 eps_quarterly
     同時證明 EPS 是單季值：若哪天來源改成年度累計，Q2 之後會整批對不上。
  B. 每股淨值 —— 資產負債表 t187ap07_*，對 balance_sheet_quarterly
  D. 半年報公司的 TTM 期數 —— 驗 ttm_eps 不是「最近 4 期加總」（那是兩年）。
     A 段只證明每一季的值對，證明不了加總方式對：2026-07-22 事故時
     A 段 1,970 筆只有 1 筆不符，22 檔半年報公司的 TTM 卻全是兩年獲利。
  E. 月營收 —— t187ap05_*，對 monthly_revenue。P/S 模型的唯一原始資料，
     單位為千元→元的換算，錯一個 1000 倍內部檢查完全看不出來。
  C. 除權息還原 —— 除權除息計算結果表 TWT49U，驗「我們的股利資料 ＋ 還原公式」
     能否重現交易所公告的除權息參考價。

股價不在此列：`validate_valuations.py` 已用 FinMind 對照，不重複。

## 目前仍無法跨來源驗證的（不要以為綠燈就是全對）

  - **現金流量表（P/FCF 的原始資料）**：交易所沒有對應的整批端點，只有 FinMind
    一個來源，無從比對。目前僅知台積電的 TTM FCF 數量級合理（約 1.06 兆），
    其餘 1,088 檔有 P/FCF 估值的股票沒有任何外部佐證。
  - **歷史序列**：以上五段全部只驗「最新一期」。估值帶是用十年歷史算的，
    那些歷史數字從未逐點對過外部來源。2026-07-22 修掉的面額與半年報 TTM
    兩個 bug 都會污染整條歷史序列——稽核只能證明修完之後最新一期對了。
  - **上櫃／興櫃的每股淨值**：B 段只涵蓋上市，TPEx 的淨值欄名未驗證。

用法：
  python scripts/audit_external.py
  python scripts/audit_external.py --ex-days 30   # C 段回溯天數（預設 10）
"""

import argparse
import os
import sys
from datetime import date, timedelta

import requests
import urllib3
from dotenv import load_dotenv
from supabase import create_client

sys.path.insert(0, os.path.dirname(__file__))
import periodicity
from price_adjust import back_adjust

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

TWSE = "https://openapi.twse.com.tw/v1/opendata/"
TPEX = "https://www.tpex.org.tw/openapi/v1/"
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 依市場 × 行業別。漏掉 _fh 等於漏掉所有金控——金融股的會計科目與一般業不同，
# 交易所因此分行業別提供端點。
SECTORS = ("ci", "fh", "ins", "bd", "mim", "basi")
INCOME_ENDPOINTS = (
    [(f"上市 {k}", TWSE + f"t187ap06_L_{k}", True) for k in SECTORS]
    + [(f"上櫃 {k}", TPEX + f"mopsfin_t187ap06_O_{k}", False) for k in SECTORS if k != "basi"]
)
# 資產負債表只涵蓋上市：TPEx 端點的淨值欄名尚未驗證，寧可不驗也不要猜欄名
# 猜錯會整批取不到值、卻因「沒有不符」而報告通過——那是最糟的綠燈。
BALANCE_ENDPOINTS = [(f"上市 {k}", TWSE + f"t187ap07_L_{k}", True) for k in SECTORS]

# 月營收，三個市場各一個端點。欄名皆為中文（與財報端點的中英混用不同）
REVENUE_ENDPOINTS = [
    ("上市", TWSE + "t187ap05_L", True),
    ("上櫃", TPEX + "mopsfin_t187ap05_O", False),
    ("興櫃", TPEX + "t187ap05_R", False),
]

# 容許誤差。四捨五入與申報時點差異不算問題，但單位錯（1000 倍）、
# 累計誤用（Q2 起約 2 倍）、面額錯（10 倍）遠超此值，必被抓出。
EPS_TOLERANCE = 0.02      # 元（EPS 是交易所直接申報的數字，可要求逐筆相符）
PRICE_TOLERANCE = 0.01    # 元（除權息參考價由公式決定，可要求相符）

# 每股淨值改用相對誤差，且門檻放寬到 5%。理由：交易所的「每股參考淨值」
# 無法用它自己公布的欄位重現——1101 台泥的隱含股數 7,691,988 既不等於
# 普通股股本股數 7,523,181，也不等於總股本股數 7,723,182；3008 大立光
# 則恰好等於「權益 ÷ 已發行股數」。同一個欄位對不同公司算法不一致，
# 要求逐筆相符只會讓稽核永遠紅燈，反而失去偵測真問題的能力。
# 5% 足以抓出面額錯（10 倍）、單位錯（1000 倍）、累計誤用（2 倍）。
BVPS_REL_TOLERANCE = 0.05
# 不符佔比的失敗門檻。2026-07-22 修好面額後的基準值是 3.9%，
# 設 8% 保留一倍餘裕；面額寫死時是 23%，會被抓出。
BVPS_BAD_RATE_LIMIT = 0.08

QUARTER_END = {"1": "03-31", "2": "06-30", "3": "09-30", "4": "12-31"}

# 期數判定與生產端共用同一份實作，不再靠註解約定一致（2026-07-22 曾因
# 一邊 8 期、一邊 6 期而誤報）。LOOKBACK 僅用於本檔挑選最近幾期做驗算。
LOOKBACK = periodicity.LOOKBACK


class AuditError(Exception):
    """來源故障。與「該筆確實沒有資料」不同，必須讓工作失敗而非回報通過。"""


def fetch_json(url: str, verify_ssl: bool = True) -> list:
    """抓取整批端點。三次都失敗就拋例外——絕不 catch 之後回傳空清單，
    那會讓呼叫端把故障當成「無資料」，繼續跑完並回報成功。"""
    last = None
    for attempt in range(3):
        try:
            data = requests.get(url, timeout=60, verify=verify_ssl).json()
            if isinstance(data, list):
                return data
            # openapi 的整批端點直接回陣列；www.twse.com.tw 的 rwd 端點回 {stat, data}。
            # 「來源故障」與「該筆確實沒有資料」必須分開：休市日與無除權息的日子，
            # rwd 會回 stat「很抱歉，沒有符合條件的資料!」，那是正常結果不是故障，
            # 重試三次再拋錯只會讓稽核在每個週末誤報。
            if isinstance(data, dict):
                stat = str(data.get("stat", ""))
                if stat == "OK":
                    return data.get("data") or []
                if "沒有符合條件的資料" in stat:
                    return []
            last = f"回應格式非預期：{str(data)[:120]}"
        except Exception as e:
            last = str(e)
        print(f"  ⚠️  第 {attempt + 1} 次請求失敗 {url}：{last}")
    raise AuditError(f"{url} 連續 3 次失敗：{last}")


def field(row: dict, *names) -> str:
    """跨來源取欄位：TWSE 用中文欄名（年度／季別／公司代號），TPEx 用英文"""
    for n in names:
        v = row.get(n)
        if v is not None and str(v).strip() != "":
            return str(v).strip()
    return ""


def to_float(raw) -> float | None:
    text = str(raw or "").strip().replace(",", "")
    if not text or text in ("--", "N/A"):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def quarter_end_of(row: dict) -> str | None:
    """民國年 +1911 轉西元。漏轉會寫出公元 115 年的日期（2026-07 事故）。"""
    y, s = field(row, "年度", "Year"), field(row, "季別", "Season")
    if not y.isdigit() or s not in QUARTER_END:
        return None
    return f"{int(y) + 1911}-{QUARTER_END[s]}"


def roc_month_to_iso(roc_ym: str) -> str | None:
    """民國年月（11506）→ 該月第一天（2026-06-01）。與 update_fundamentals 同一套轉換。"""
    text = str(roc_ym or "").strip()
    if len(text) < 5:
        return None
    try:
        year, month = int(text[:-2]) + 1911, int(text[-2:])
    except ValueError:
        return None
    return f"{year}-{month:02d}-01" if 1 <= month <= 12 else None


def official_values(endpoints: list, col_names: tuple) -> dict:
    """{(股票代號, 季末日): 官方申報值}"""
    out = {}
    for label, url, verify in endpoints:
        rows = fetch_json(url, verify)
        hit = 0
        for r in rows:
            sid, q, val = (field(r, "公司代號", "SecuritiesCompanyCode"),
                           quarter_end_of(r), to_float(field(r, *col_names)))
            if sid and q and val is not None:
                out[(sid, q)] = val
                hit += 1
        print(f"  {label}：{len(rows)} 筆，可用 {hit} 筆")
    return out


def known_stock_ids() -> set[str]:
    """股票名冊。Supabase 預設 1000 筆上限，必須分頁且排序。"""
    ids, offset = set(), 0
    while True:
        rows = (supabase.table("stocks").select("stock_id").order("stock_id")
                .range(offset, offset + 999).execute().data)
        ids.update(r["stock_id"] for r in rows)
        if len(rows) < 1000:
            return ids
        offset += 1000


def db_values(table: str, col: str, quarters: set) -> dict:
    """{(股票代號, 季末日): 資料庫值}。Supabase 預設 1000 筆上限，必須分頁且排序。"""
    out, offset = {}, 0
    while True:
        rows = (supabase.table(table).select(f"stock_id,quarter_end_date,{col}")
                .in_("quarter_end_date", sorted(quarters))
                .order("stock_id").order("quarter_end_date")
                .range(offset, offset + 999).execute().data)
        for r in rows:
            if r[col] is not None:
                out[(r["stock_id"], r["quarter_end_date"])] = float(r[col])
        if len(rows) < 1000:
            return out
        offset += 1000


def compare(official: dict, table: str, col: str,
            tol: float, relative: bool = False) -> list[str]:
    """逐筆比對官方值與資料庫值。回傳不符清單。"""
    quarters = {q for _, q in official}
    ours = db_values(table, col, quarters)

    bad, checked, missing, near = [], 0, 0, 0
    for key, theirs in official.items():
        mine = ours.get(key)
        if mine is None:
            missing += 1
            continue
        checked += 1
        diff = abs(mine - theirs)
        limit = abs(theirs) * tol if relative else tol
        if diff > limit:
            bad.append(f"{key[0]} {key[1]}：我們 {mine} vs 交易所 {theirs}"
                       f"（差 {mine - theirs:+.2f}）")
        elif relative and diff > abs(theirs) * 0.01:
            near += 1

    print(f"\n  比對 {checked} 筆，不符 {len(bad)} 筆，資料庫無對應 {missing} 筆")
    if relative:
        # 容差內但差距 >1% 者單獨計數：這是「還沒壞但值得盯」的區間，
        # 若某天暴增，代表演算法或來源出現系統性偏移
        print(f"  容差內但差距 >1%：{near} 筆（門檻 {tol:.0%}）")
    print(f"  涵蓋季別：{', '.join(sorted(quarters))}")
    if missing > checked * 0.5:
        # 對不上的比對得上的還多，多半是季別對齊或欄名取錯，而非資料真的缺
        print(f"  ⚠️  無對應筆數偏高，請確認 {table} 是否已更新到最新季")
    return bad


def check_eps() -> list[str]:
    print("\n=== A. 每股盈餘（綜合損益表 vs eps_quarterly）===")
    official = official_values(INCOME_ENDPOINTS, ("基本每股盈餘（元）",))
    return compare(official, "eps_quarterly", "eps", EPS_TOLERANCE)


def check_bvps() -> list[str]:
    """
    每股淨值以「不符佔比」判定，而非逐筆。

    交易所的「每股參考淨值」無法用它自己公布的欄位重現（見 BVPS_REL_TOLERANCE
    的說明），2026-07-22 實測 1,079 檔中有 42 檔（3.9%）差距超過 5%，
    且隱含股數比值 1.07～4.15 毫無規律，逐案追查也得不到答案。
    逐筆判定會讓這支稽核永遠紅燈，久了就沒人看——那比不做還糟。

    改用佔比門檻，偵測的是「系統性惡化」：面額寫死造成 23% 不符、
    單位錯或累計誤用會讓佔比逼近 100%，都遠超門檻。單一股票的異常
    由 A 段（EPS 可逐筆精確比對）與 audit_cross_check.py 負責。
    """
    print("\n=== B. 每股淨值（資產負債表 vs balance_sheet_quarterly）===")
    print("  注意：僅涵蓋上市；上櫃／興櫃的 TPEx 淨值欄名未驗證，故不納入")
    official = official_values(BALANCE_ENDPOINTS, ("每股參考淨值",))
    bad = compare(official, "balance_sheet_quarterly",
                  "book_value_per_share", BVPS_REL_TOLERANCE, relative=True)

    rate = len(bad) / len(official) if official else 0
    print(f"  不符佔比 {rate:.1%}（門檻 {BVPS_BAD_RATE_LIMIT:.0%}，"
          f"2026-07-22 基準值 3.9%）")
    if rate <= BVPS_BAD_RATE_LIMIT:
        print("  ✓ 在已知的不可重現範圍內，不計入失敗。差距最大的 5 筆：")
        for b in bad[:5]:
            print(f"      {b}")
        return []
    return bad


def check_ttm_window() -> list[str]:
    """
    半年報公司的 ttm_eps 不得等於「最近 4 期加總」——那是兩年的獲利。

    為什麼要獨立一段：A 段拿交易所的單季申報值逐筆比對，只證明「每一季的
    EPS 都對」，證明不了「把它們加起來的方式對」。2026-07-22 事故正是如此——
    A 段 1,970 筆只有 1 筆不符，看起來很健康，但 22 檔半年報公司的 ttm_eps
    全是兩年加總（4546 長亨 12.98，正確為 7.58），A 段完全沒有反應。

    判定方式不依賴期別月份的判斷邏輯（那正是出錯的地方），改為直接驗算：
    若 ttm_eps 明顯接近 4 期加總、而與 2 期加總相差甚遠，就是誤用了 4 期。

    ⚠️ 兩個必須容忍的誤差來源，門檻因此用相對值而非絕對值：
      1. ttm_eps 是【股數調整後】的 EPS 加總（見 calculate_valuation.share_factors），
         這裡拿原始 eps 比對，配過股的公司本來就對不齊。
      2. 4 期與 2 期加總有時只差一點點（7558 只差 0.01），絕對門檻會卡在邊界誤報。
    要求「與 4 期的差距 < 2%」且「4 期與 2 期相差 > 20%」才判定為誤用，
    寧可漏報也不要天天喊狼來了——稽核一旦開始誤報就沒人看了。
    """
    print("\n=== D. 半年報公司的 TTM 期數 ===")
    eps = {}
    offset = 0
    while True:
        rows = (supabase.table("eps_quarterly").select("stock_id,quarter_end_date,eps")
                .order("stock_id").order("quarter_end_date")
                .range(offset, offset + 999).execute().data)
        for r in rows:
            if r["eps"] is not None:
                eps.setdefault(r["stock_id"], []).append((r["quarter_end_date"], float(r["eps"])))
        if len(rows) < 1000:
            break
        offset += 1000

    vals = {}
    offset = 0
    while True:
        rows = (supabase.table("valuations").select("stock_id,ttm_eps")
                .order("stock_id").range(offset, offset + 999).execute().data)
        vals.update({r["stock_id"]: r["ttm_eps"] for r in rows if r["ttm_eps"] is not None})
        if len(rows) < 1000:
            break
        offset += 1000

    bad, checked = [], 0
    for sid, recs in eps.items():
        ttm = vals.get(sid)
        if ttm is None or len(recs) < 4:
            continue
        # 回看期數必須與 calculate_valuation._eps_window 一致，否則兩邊
        # 對同一支股票會給出不同答案（2026-07-22 曾因一邊 8 期、一邊 6 期而誤報）
        recent = sorted(recs, reverse=True)[:LOOKBACK]
        if {int(d[5:7]) for d, _ in recent} > {6, 12}:
            continue                                  # 季報公司，本段不適用
        checked += 1
        four = sum(e for _, e in recent[:4])
        two = sum(e for _, e in recent[:2])
        if abs(two) < 0.01 or abs(four) < 0.01:
            continue                                  # 接近 0，比值無意義
        near_four = abs(float(ttm) - four) / abs(four) < 0.02
        differs = abs(four - two) / abs(two) > 0.20
        if near_four and differs:
            bad.append(f"{sid}：ttm_eps={ttm} 等於最近 4 期加總（兩年），"
                       f"應為 2 期加總 {two:.2f}")
    print(f"  半年報公司 {checked} 檔，TTM 誤用 4 期 {len(bad)} 檔")
    return bad


def check_revenue() -> list[str]:
    """
    月營收 —— P/S 模型的唯一原始資料，先前完全沒有跨來源驗證。

    P/S 有 420 檔判「便宜」，而它的分子（TTM 每股營收）全靠 monthly_revenue。
    這張表的單位是【元】，來源 OpenAPI 給的是【千元】——差一個 1000 倍就是
    每股營收暴增千倍、目標價跟著暴增，而內部一致性檢查完全看不出來
    （所有數字彼此自洽）。這正是本專案「單位錯」那類事故的形狀。

    三個市場的欄名一致（皆為中文），與財報端點不同，故不需 field() 兜英文欄名。
    """
    print("\n=== E. 月營收（t187ap05_* vs monthly_revenue）===")
    official: dict[tuple[str, str], float] = {}
    for label, url, verify in REVENUE_ENDPOINTS:
        rows = fetch_json(url, verify)
        hit = 0
        for r in rows:
            sid = field(r, "公司代號")
            ym = roc_month_to_iso(field(r, "資料年月"))
            rev_k = to_float(field(r, "營業收入-當月營收"))
            if sid and ym and rev_k is not None and rev_k >= 0:
                official[(sid, ym)] = rev_k * 1000      # 千元 → 元
                hit += 1
        print(f"  {label}：{len(rows)} 筆，可用 {hit} 筆")

    months = {ym for _, ym in official}
    ours: dict[tuple[str, str], float] = {}
    offset = 0
    while True:
        rows = (supabase.table("monthly_revenue").select("stock_id,year_month,revenue")
                .in_("year_month", sorted(months))
                .order("stock_id").order("year_month")
                .range(offset, offset + 999).execute().data)
        for r in rows:
            if r["revenue"] is not None:
                ours[(r["stock_id"], r["year_month"])] = float(r["revenue"])
        if len(rows) < 1000:
            break
        offset += 1000

    bad, checked, missing = [], 0, 0
    for key, theirs in official.items():
        mine = ours.get(key)
        if mine is None:
            missing += 1
            continue
        checked += 1
        # 相對誤差 1%：容忍四捨五入，但單位錯（1000 倍）必被抓出
        if theirs == 0:
            if mine != 0:
                bad.append(f"{key[0]} {key[1]}：我們 {mine:,.0f} vs 交易所 0")
        elif abs(mine - theirs) / abs(theirs) > 0.01:
            bad.append(f"{key[0]} {key[1]}：我們 {mine:,.0f} vs 交易所 {theirs:,.0f}"
                       f"（{mine / theirs:.2f} 倍）")
    print(f"  比對 {checked} 筆，不符 {len(bad)} 筆，資料庫無對應 {missing} 筆")
    print(f"  涵蓋月份：{', '.join(sorted(months))}")
    return bad


def check_ex_rights(days: int) -> list[str]:
    """
    驗「我們的股利資料 ＋ 還原公式」能否重現交易所公告的除權息參考價。

    刻意用交易所公告的前收當基準，而不是資料庫價格——這裡要驗的是
    股利資料與還原公式，把價格的已知誤差（週採樣使基準偏移 6~7 天）隔離掉。

    ## 有官方因子的日期不計失敗

    2026-07-22 起，生產路徑（估值、河流圖、回測）優先使用 ex_right_factors
    表的官方因子，自算公式只在查不到官方值時才用（見 price_adjust.back_adjust）。
    因此「自算對不上」不等於「網站上的數字錯了」——上市有 10 年官方因子，
    自算誤差不會流到畫面上。

    這一段若不區分，紅燈會持續亮在早已修好的東西上。稽核一旦開始喊狼來了
    就沒人看，那比不做更糟（同 check_bvps 的取捨）。

    真正該失敗的只有兩種：
      1. 官方因子涵蓋不到的日期（上櫃／興櫃歷史）自算對不上——那是生產路徑
      2. dividends 表完全沒有該筆——那是資料缺漏，兩條路徑都救不了
    """
    print(f"\n=== C. 除權息還原（TWT49U 近 {days} 天）===")
    # 稽核範圍限於股票名冊。TWT49U 也含 ETF（00 開頭），那些本就不在 dividends 表，
    # 不先濾掉會產生大量假警報，把真正的缺漏淹沒。
    known = known_stock_ids()
    bad, info, checked, skipped = [], [], 0, 0
    for i in range(days):
        d = date.today() - timedelta(days=i)
        ex = f"{d:%Y-%m-%d}"
        rows = fetch_json("https://www.twse.com.tw/rwd/zh/exRight/TWT49U"
                          f"?startDate={d:%Y%m%d}&endDate={d:%Y%m%d}&response=json")
        if not rows:
            continue
        ours_div = {r["stock_id"]: r for r in
                    supabase.table("dividends").select("stock_id,cash_dividend,stock_dividend")
                    .eq("ex_date", ex).execute().data}
        # 該日已有官方還原因子的股票：自算誤差不會流到生產，僅供參考
        covered = {r["stock_id"] for r in
                   supabase.table("ex_right_factors").select("stock_id")
                   .eq("ex_date", ex).execute().data}
        for r in rows:
            sid, prev, ref = r[1], to_float(r[3]), to_float(r[4])
            if not (prev and ref):
                continue
            if sid not in known:
                skipped += 1
                continue
            dv = ours_div.get(sid)
            if not dv:
                if sid in covered:
                    # 官方因子有這筆，還原不受影響；但股利本身缺漏會影響殖利率模型
                    info.append(f"{sid} {ex}：dividends 表沒有（官方因子已涵蓋，"
                                f"還原不受影響；殖利率模型仍會少這筆）")
                else:
                    bad.append(f"{sid} {ex}：交易所有除權息紀錄，dividends 表沒有")
                continue
            cash, stock = float(dv["cash_dividend"] or 0), float(dv["stock_dividend"] or 0)
            # 用同一支還原函式，確保驗的是生產程式碼而非另寫一份公式。
            # 造兩筆序列：除權息日前一筆用交易所公告的前收，還原後應等於公告參考價
            ours = back_adjust(["1900-01-01", ex], [prev, prev], [(ex, cash, stock)])[0]
            checked += 1
            if abs(ours - ref) > PRICE_TOLERANCE:
                msg = (f"{sid} {ex}：自算還原價 {ours:.2f} vs 交易所公告 {ref}"
                       f"（現金 {cash} 配股 {stock}）")
                # 有官方因子者，生產路徑走的是官方值，自算誤差不影響畫面
                (info if sid in covered else bad).append(msg)
    print(f"  比對 {checked} 筆，不符 {len(bad)} 筆，非名冊標的（ETF 等）跳過 {skipped} 筆")
    if info:
        print(f"  另有 {len(info)} 筆自算對不上、但已由官方因子涵蓋（不計失敗）：")
        for m in info[:5]:
            print(f"      {m}")
    if checked == 0:
        print("  （期間無除權息，此段未實際驗證任何資料）")
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ex-days", type=int, default=10, help="除權息回溯天數")
    args = ap.parse_args()

    print("對外比對稽核：以交易所官方申報值驗證資料庫")
    problems = (check_eps() + check_bvps() + check_ttm_window()
                + check_revenue() + check_ex_rights(args.ex_days))

    print("\n" + "=" * 60)
    if not problems:
        print("✅ 全部與交易所一致")
        return
    print(f"❌ 發現 {len(problems)} 筆與交易所不符：\n")
    for p in problems[:50]:
        print(f"  {p}")
    if len(problems) > 50:
        print(f"  …另有 {len(problems) - 50} 筆")
    sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except AuditError as e:
        # 來源故障與「資料正確」是兩件事，不可靜默通過
        print(f"\n❌ 稽核中止（來源故障）：{e}")
        sys.exit(1)
