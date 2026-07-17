"""
月營收增量更新（P/S 估值原始資料）

改用 TWSE／TPEx OpenAPI 的整批端點，取代 FinMind 逐股呼叫：
3 次呼叫（上市／上櫃／興櫃）取代 2,300+ 次 × 6.5 秒 ≈ 4.2 小時。

單位：OpenAPI 為「千元」，資料庫存「元」，需 ×1000。

為何只做月營收，不做資產負債表：
OpenAPI 的「每股參考淨值」雖然是官方值且涵蓋金控等特殊財報格式，
但只提供最新一季、無歷史資料，而 P/B 百分位帶至少需要 8 季；
且它對特別股的處理與 FinMind 不同（官方以總股本計算、FinMind 僅普通股），
混用會讓歷史序列與最新值基準不一致。淨值一律由 download_balance_sheet.py
（FinMind）供應，以確保整條序列基準相同。

用法：
  python scripts/update_fundamentals.py
"""

import os
import sys
import time
import requests
import urllib3
from dotenv import load_dotenv
from supabase import create_client

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
sys.stderr.reconfigure(encoding="utf-8", line_buffering=True)
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

TWSE = "https://openapi.twse.com.tw/v1/opendata/"
TPEX = "https://www.tpex.org.tw/openapi/v1/"

# TPEx 憑證鏈不完整，需略過 SSL 驗證（與 daily_price_update.py 的既有做法一致）
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 月營收：三個市場各一個端點
REVENUE_ENDPOINTS = [
    ("上市", TWSE + "t187ap05_L",          True),
    ("上櫃", TPEX + "mopsfin_t187ap05_O",  False),
    ("興櫃", TPEX + "t187ap05_R",          False),
]


def fetch_json(url: str, verify_ssl: bool) -> list:
    """取得 OpenAPI 資料，失敗重試 3 次；全部失敗回傳空清單"""
    for attempt in range(3):
        try:
            resp = requests.get(url, timeout=30, verify=verify_ssl)
            data = resp.json()
            if isinstance(data, list):
                return data
            print(f"  ⚠️  非預期回應格式: {url}")
        except Exception as e:
            print(f"  ⚠️  請求失敗（第 {attempt + 1} 次）{url}: {e}")
            time.sleep(3)
    return []


def to_number(raw) -> float | None:
    """OpenAPI 數值為字串且可能為空字串或含千分位逗號"""
    if raw is None:
        return None
    text = str(raw).strip().replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def stock_id_of(row: dict) -> str:
    """
    取股票代碼。TWSE 用「公司代號」，TPEx 的資產負債表改用 SecuritiesCompanyCode
    （但 TPEx 的月營收又用「公司代號」），故兩種都要試。
    """
    return str(row.get("公司代號") or row.get("SecuritiesCompanyCode") or "").strip()


def roc_month_to_date(roc_ym: str) -> str | None:
    """民國年月（如 11506）→ 該月第一天（2026-06-01）"""
    text = str(roc_ym).strip()
    if len(text) < 5:
        return None
    try:
        year  = int(text[:-2]) + 1911
        month = int(text[-2:])
    except ValueError:
        return None
    if not 1 <= month <= 12:
        return None
    return f"{year:04d}-{month:02d}-01"


def known_stock_ids() -> set[str]:
    """資料庫既有股票；OpenAPI 會回傳未收錄的標的，需過濾以免外鍵失敗"""
    ids, offset = set(), 0
    while True:
        resp = supabase.table("stocks").select("stock_id").range(offset, offset + 999).execute()
        rows = resp.data or []
        ids.update(r["stock_id"] for r in rows)
        if len(rows) < 1000:
            break
        offset += 1000
    return ids


def upsert_batch(table: str, rows: list[dict], conflict: str, batch_size: int = 500):
    for i in range(0, len(rows), batch_size):
        supabase.table(table).upsert(rows[i:i + batch_size], on_conflict=conflict).execute()


def update_monthly_revenue(known: set[str]) -> int:
    """更新最新一期月營收（OpenAPI 單位為千元，資料庫存元）"""
    print("\n=== 月營收 ===")
    rows: list[dict] = []

    for market, url, verify in REVENUE_ENDPOINTS:
        data = fetch_json(url, verify)
        added = 0
        for r in data:
            sid = stock_id_of(r)
            if sid not in known:
                continue
            ym = roc_month_to_date(r.get("資料年月", ""))
            rev_k = to_number(r.get("營業收入-當月營收"))
            if not ym or rev_k is None or rev_k < 0:
                continue
            rows.append({
                "stock_id":   sid,
                "year_month": ym,
                "revenue":    int(rev_k * 1000),   # 千元 → 元
            })
            added += 1
        print(f"  {market}: {added} 筆（原始 {len(data)} 筆）")

    if rows:
        upsert_batch("monthly_revenue", rows, "stock_id,year_month")
        months = sorted({r["year_month"] for r in rows})
        print(f"  ✅ 寫入 {len(rows)} 筆，月份：{', '.join(months)}")
    else:
        print("  ⚠️  無資料")
    return len(rows)


def main():
    known = known_stock_ids()
    print(f"資料庫既有股票：{len(known)} 支")
    update_monthly_revenue(known)
    print("\n完成！")


if __name__ == "__main__":
    main()
