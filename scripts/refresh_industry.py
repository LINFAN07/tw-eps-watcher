"""
refresh_industry.py — 以交易所公告的產業代碼維護 stocks.industry

## 為什麼需要這支（取代一次性的 backfill_industry.py）

`backfill_industry.py` 從 FinMind 的 `industry_category` 抓一次就沒再更新，
而它被列在 `audit_workflows.NO_SCHEDULE_OK` 的「一次性補產業別」。
產業別**不是一次性的資料**：公司會被重新分類、新掛牌股需要分類，
而交易所在 2007 年後把「電子工業」拆成 24~31 八個子產業。

**2026-08-09 實測**：在市 2,420 支有 **670 支（27.7%）**與 FinMind 現值不符，
其中 262 支還掛在早已不存在的母類別「電子工業」——台積電、聯發科被歸在
「電子工業」而不是「半導體業」，中華電不是「通信網路業」，大立光不是「光電業」。

影響的不只畫面：`getRecommendedModel` 的產業正則、回測的 `by_industry` 分組、
產業陷阱徽章全都吃這個欄位。也就是說「半導體業 P/E 超額 +7.6pp」那類結論，
它的母體並不包含台積電。

這是「把一個會隨時間變動的欄位當成一次性」的同型缺陷
（同 `download_monthly_revenue.py` 被白名單宣稱有人呼叫那次）。

## 為什麼改用交易所而不是 FinMind

兩者都會漂移，但交易所是**申報端**、且給的是穩定的數字代碼：
- FinMind 的 2308 台達電現值是「電子工業」，交易所代碼 28 = 電子零組件業。
  FinMind 那邊是錯的。
- 交易所三個市場都有端點（`t187ap03_L`／`mopsfin_t187ap03_O`／`_R`），
  秒級整批，共 2,343 支。

## 對照表為什麼寫死而不是每次反推

對照表是 2026-08-09 由「(市場, 代碼) → 現有標籤的多數決」推出來的，
**推導時必須先排除母類別**（電子工業、化學生技醫療、創新板股票）——
上市電子股當初被整批塞進母類別，不排除的話多數決會選到錯的那個。

推完就固化：若每次執行都重新反推，資料修好後母類別消失，對照表會變成
「用自己上次寫的結果推自己」；新代碼出現時更會靜默猜錯。
**未知的 (市場, 代碼) 一律跳過並報數，不猜。**

## 命名分市場，刻意不統一

同一個代碼在上市叫「其他電子業」、上櫃叫「其他電子類」。CLAUDE.md 記載這兩套
標籤的回測結論相反、不可合併統計，故維持現狀——本支只修「過期」，不動分類粒度。

用法：
  python scripts/refresh_industry.py            # 更新
  python scripts/refresh_industry.py --dry-run  # 只列出會改什麼
"""

import argparse
import os
import sys
import time
from collections import Counter

import requests
import urllib3
from dotenv import load_dotenv
from supabase import create_client

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
sys.stderr.reconfigure(encoding="utf-8", line_buffering=True)
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

UA = {"User-Agent": "Mozilla/5.0"}
RETRY_BACKOFF = (2, 5, 10)

# 市場 → 交易所端點（URL, 股票代碼欄, 產業代碼欄, 是否驗證 SSL）
ENDPOINTS = [
    ("TWSE",     "https://openapi.twse.com.tw/v1/opendata/t187ap03_L",
     "公司代號", "產業別", True),
    ("TPEx",     "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O",
     "SecuritiesCompanyCode", "SecuritiesIndustryCode", False),
    ("Emerging", "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_R",
     "SecuritiesCompanyCode", "SecuritiesIndustryCode", False),
]

# (市場, 交易所產業代碼) → 本專案使用的產業名稱。推導方式見檔頭。
INDUSTRY_BY_CODE: dict[str, dict[str, str]] = {
    "TWSE": {
        "01": "水泥工業", "02": "食品工業", "03": "塑膠工業", "04": "紡織纖維",
        "05": "電機機械", "06": "電器電纜", "08": "玻璃陶瓷", "09": "造紙工業",
        "10": "鋼鐵工業", "11": "橡膠工業", "12": "汽車工業", "14": "建材營造",
        "15": "航運業", "16": "觀光餐旅", "17": "金融保險", "18": "貿易百貨",
        "20": "其他", "21": "化學工業", "22": "生技醫療業", "23": "油電燃氣業",
        "24": "半導體業", "25": "電腦及週邊設備業", "26": "光電業", "27": "通信網路業",
        "28": "電子零組件業", "29": "電子通路業", "30": "資訊服務業", "31": "其他電子業",
        "32": "文化創意業", "33": "農業科技業", "35": "綠能環保", "36": "數位雲端",
        "37": "運動休閒", "38": "居家生活", "91": "存託憑證",
    },
    "TPEx": {
        "02": "食品工業", "03": "塑膠工業", "04": "紡織纖維", "05": "電機機械",
        "06": "電器電纜", "10": "鋼鐵工業", "14": "建材營造", "15": "航運業",
        "16": "觀光餐旅", "17": "金融業", "20": "其他", "21": "化學工業",
        "22": "生技醫療業", "23": "油電燃氣業", "24": "半導體業", "25": "電腦及週邊設備業",
        "26": "光電業", "27": "通信網路業", "28": "電子零組件業", "29": "電子通路業",
        "30": "資訊服務業", "31": "其他電子類", "32": "文化創意業", "33": "農業科技業",
        "35": "綠能環保類", "36": "數位雲端類", "37": "運動休閒類", "38": "居家生活類",
    },
    "Emerging": {
        "02": "食品工業", "04": "紡織纖維", "05": "電機機械", "10": "鋼鐵工業",
        "14": "建材營造", "15": "航運業", "16": "觀光餐旅", "17": "金融業",
        "20": "其他", "21": "化學工業", "22": "生技醫療業", "23": "油電燃氣業",
        "24": "半導體業", "25": "電腦及週邊設備業", "26": "光電業", "27": "通信網路業",
        "28": "電子零組件業", "29": "電子通路業", "30": "資訊服務業", "31": "其他電子業",
        "32": "文化創意業", "33": "農業科技", "35": "綠能環保", "36": "數位雲端",
        "37": "運動休閒", "38": "居家生活",
    },
}

# 一次改動超過這個比例就中止：對照表寫錯或來源改格式時，症狀就是「整批都要改」。
# 這是「旗標覆蓋率異常＝旗標本身壞了」那條教訓的同型防護。
MAX_CHANGE_RATE = 0.40


class FetchError(Exception):
    """抓取失敗（與「該市場確實沒有資料」不同，呼叫端必須讓工作失敗）"""


def get_json(url: str, verify: bool) -> list:
    last = None
    for attempt, wait in enumerate((*RETRY_BACKOFF, None)):
        try:
            resp = requests.get(url, timeout=60, headers=UA, verify=verify)
            data = resp.json()
            if isinstance(data, list) and data:
                return data
            last = f"回應非預期（HTTP {resp.status_code}，型別 {type(data).__name__}）"
        except Exception as e:
            last = f"請求例外：{e}"
        print(f"  ⚠️  第 {attempt + 1} 次失敗 {url}：{last}")
        if wait:
            time.sleep(wait)
    # 絕不回空清單——那會讓呼叫端把故障當成「這個市場沒有股票」而整批跳過
    raise FetchError(f"{url} 連續 {len(RETRY_BACKOFF) + 1} 次失敗：{last}")


def official_industries() -> dict[str, tuple[str, str]]:
    """{股票代碼: (市場, 產業代碼)}"""
    out: dict[str, tuple[str, str]] = {}
    for market, url, code_key, ind_key, verify in ENDPOINTS:
        rows = get_json(url, verify)
        hit = 0
        for r in rows:
            sid = str(r.get(code_key, "")).strip()
            code = str(r.get(ind_key, "")).strip()
            if sid and code:
                out[sid] = (market, code)
                hit += 1
        print(f"  {market}：{len(rows)} 筆，可用 {hit} 筆")
    return out


def current_stocks() -> list[dict]:
    rows, offset = [], 0
    while True:
        page = (supabase.table("stocks").select("stock_id,name,industry,market,delisted_at")
                .order("stock_id").range(offset, offset + 999).execute().data)
        rows.extend(page)
        if len(page) < 1000:
            break
        offset += 1000
    return rows


def run(dry_run: bool = False):
    print("=== 產業別更新（來源：交易所公司基本資料）===")
    if dry_run:
        print("（--dry-run：只列出會改什麼，不寫入）")

    official = official_industries()
    stocks = current_stocks()
    alive = [r for r in stocks if r["delisted_at"] is None]
    print(f"\n交易所涵蓋 {len(official)} 支；我方在市 {len(alive)} 支")

    changes: list[tuple[str, str, str, str]] = []   # (代碼, 名稱, 舊, 新)
    unknown: Counter = Counter()
    absent = 0

    for r in alive:
        entry = official.get(r["stock_id"])
        if entry is None:
            absent += 1          # ETF 與剛掛牌者不在名單上，維持原標籤
            continue
        market, code = entry
        # 以交易所回報的市場為準：我方 market 欄位每日由 daily_price_update 維護，
        # 但轉板當天可能還沒同步，用來源自己說的比較安全
        name = INDUSTRY_BY_CODE.get(market, {}).get(code)
        if name is None:
            unknown[(market, code)] += 1
            continue             # 未知代碼不猜，留著原值並在收尾報數
        if r["industry"] != name:
            changes.append((r["stock_id"], r["name"], r["industry"], name))

    rate = len(changes) / len(alive) if alive else 0
    print(f"需更新 {len(changes)} 支（{rate:.1%}）、"
          f"交易所名單沒有而略過 {absent} 支、未知代碼 {sum(unknown.values())} 支")

    if unknown:
        # 新代碼＝交易所新增了產業分類，對照表要跟著補。沉默會讓那批股票永遠停在舊值
        print("\n⚠️  對照表沒有的 (市場, 代碼)，這些股票維持原標籤：")
        for (market, code), n in unknown.most_common():
            print(f"     {market} {code}：{n} 支")

    print("\n改動型態：")
    for (old, new), n in Counter((c[2], c[3]) for c in changes).most_common(15):
        print(f"     {str(old):<14} → {str(new):<14} {n} 支")

    if rate > MAX_CHANGE_RATE:
        print(f"\n❌ 改動比例 {rate:.1%} 超過門檻 {MAX_CHANGE_RATE:.0%}——"
              f"多半是對照表寫錯或來源改了格式，不是市場真的重分類。中止。")
        sys.exit(1)

    if dry_run or not changes:
        print("\n（未寫入）" if dry_run else "\n無需更新。")
        return

    # 依產業分組批次 update。不可用 upsert：只帶主鍵與少數欄位的 upsert 會在
    # 衝突解析【之前】違反 stocks.name 的 NOT NULL（見 CLAUDE.md 平台限制）
    groups: dict[str, list[str]] = {}
    for sid, _, _, new in changes:
        groups.setdefault(new, []).append(sid)
    for industry, sids in groups.items():
        for i in range(0, len(sids), 100):
            supabase.table("stocks").update({"industry": industry}) \
                .in_("stock_id", sids[i:i + 100]).execute()
    print(f"\n完成！更新 {len(changes)} 支。")
    print("提醒：產業別改動會連帶影響推薦模型、回測的 by_industry 分組與產業陷阱徽章，"
          "需重跑 backtest_valuation.py 並同步前端常數。")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="只列出會改什麼")
    run(**vars(ap.parse_args()))
