"""
基本面資料增量更新（月營收 + 每股淨值 + 負債比）

改用 TWSE／TPEx OpenAPI 的「整批」端點，取代 FinMind 逐股呼叫：

  月營收    ：3 次呼叫（上市／上櫃／興櫃）取代 2,300+ 次 × 6.5 秒 ≈ 4.2 小時
  資產負債表：依「市場 × 行業別」分別提供端點，合計約 16 次呼叫

FinMind 版的 download_*.py 仍保留，用於首次建立 10 年歷史資料；
本腳本只做「最新一期」的增量更新，供排程每月／每季執行。

單位對照（務必注意）：
  OpenAPI 月營收    ：千元 → 資料庫存「元」，需 ×1000
  OpenAPI 每股參考淨值：元／股，直接採用（官方公告值，含金控等特殊財報格式）

用法：
  python scripts/update_fundamentals.py              # 月營收 + 資產負債表
  python scripts/update_fundamentals.py --revenue    # 只更新月營收
  python scripts/update_fundamentals.py --balance    # 只更新資產負債表
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

# 資產負債表：金控／保險／證券期貨業的財報格式與一般業不同，
# 交易所因此分別提供端點；漏掉 _fh 等於漏掉所有金控股。
BALANCE_ENDPOINTS = (
    [("上市", TWSE + f"t187ap07_L_{k}",         True)  for k in ("ci", "fh", "ins", "bd", "mim", "basi")]
    + [("上櫃", TPEX + f"mopsfin_t187ap07_O_{k}", False) for k in ("ci", "fh", "ins", "bd", "mim")]
    + [("興櫃", TPEX + f"mopsfin_t187ap07_U_{k}", False) for k in ("ci", "fh", "ins", "bd", "mim", "basi")]
)

# 同一語意在不同行業別端點的欄位名稱不同（一般業用「總額」、金控用「總計」）
ASSET_KEYS = ("資產總額", "資產總計")
LIAB_KEYS  = ("負債總額", "負債總計")

QUARTER_END = {"1": "03-31", "2": "06-30", "3": "09-30", "4": "12-31"}


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


def pick(row: dict, keys: tuple[str, ...]) -> float | None:
    """依序嘗試多個欄位名稱，取第一個有值的"""
    for k in keys:
        v = to_number(row.get(k))
        if v is not None:
            return v
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


def roc_quarter_to_date(roc_year, quarter) -> str | None:
    """民國年 + 季別（115, 1）→ 季末日（2026-03-31）"""
    suffix = QUARTER_END.get(str(quarter).strip())
    if not suffix:
        return None
    try:
        year = int(str(roc_year).strip()) + 1911
    except ValueError:
        return None
    return f"{year}-{suffix}"


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


def update_balance_sheet(known: set[str]) -> int:
    """更新最新一季每股淨值與負債比（採用交易所公告的每股參考淨值）"""
    print("\n=== 資產負債表（每股淨值 + 負債比）===")
    merged: dict[tuple[str, str], dict] = {}

    for market, url, verify in BALANCE_ENDPOINTS:
        data = fetch_json(url, verify)
        added = 0
        for r in data:
            sid = stock_id_of(r)
            if sid not in known:
                continue
            qdate = roc_quarter_to_date(r.get("年度", ""), r.get("季別", ""))
            bvps  = to_number(r.get("每股參考淨值"))
            if not qdate or bvps is None or bvps <= 0:
                continue

            assets = pick(r, ASSET_KEYS)
            liab   = pick(r, LIAB_KEYS)
            debt_ratio = round(liab / assets * 100, 2) if assets and liab and assets > 0 else None

            merged[(sid, qdate)] = {
                "stock_id":            sid,
                "quarter_end_date":    qdate,
                "book_value_per_share": round(bvps, 4),
                "debt_ratio":          debt_ratio,
            }
            added += 1
        label = url.rsplit("_", 1)[-1]
        print(f"  {market} ({label}): {added} 筆")

    rows = list(merged.values())
    if rows:
        upsert_batch("balance_sheet_quarterly", rows, "stock_id,quarter_end_date")
        quarters = sorted({r["quarter_end_date"] for r in rows})
        print(f"  ✅ 寫入 {len(rows)} 筆，季度：{', '.join(quarters)}")
    else:
        print("  ⚠️  無資料")
    return len(rows)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="以 TWSE/TPEx OpenAPI 增量更新基本面資料")
    parser.add_argument("--revenue", action="store_true", help="只更新月營收")
    parser.add_argument("--balance", action="store_true", help="只更新資產負債表")
    args = parser.parse_args()

    do_all = not (args.revenue or args.balance)
    known  = known_stock_ids()
    print(f"資料庫既有股票：{len(known)} 支")

    if args.revenue or do_all:
        update_monthly_revenue(known)
    if args.balance or do_all:
        update_balance_sheet(known)

    print("\n完成！")


if __name__ == "__main__":
    main()
