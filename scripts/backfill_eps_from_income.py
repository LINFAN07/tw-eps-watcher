"""
以 TWSE／TPEx 綜合損益表補 Q1 EPS（P/E 估值原始資料）

用途與限制：
  FinMind 對金控／保險／證券期貨業的 EPS 更新較慢，導致每年 Q1 財報季
  這些股票的 P/E 會沿用上一年 Q4 的舊財報（2026-07 曾發現國泰金等 13 家
  金控全部缺 2026 Q1）。交易所綜合損益表 OpenAPI 有官方「基本每股盈餘」，
  且分行業別提供端點，可整批補上，數秒完成、涵蓋金控。

  **只補 Q1（季別=1）**：綜合損益表為「年初至今累計」揭露，Q1 的累計恰等於
  單季，可安全寫入 eps_quarterly（存單季值）。但 OpenAPI 每次僅提供最新一季
  的累計、無法取得前一季來還原，故 Q2~Q4 不能由此來源推得單季，仍須靠 FinMind。
  腳本因此硬性只採用「季別=1」的資料，非 Q1 一律跳過。

  已用台積電交叉驗證：交易所損益表 Q1 EPS 與 FinMind 單季 Q1 EPS 完全一致
  （2330=22.08、2317=3.56、2412=1.30）。

用法：
  python scripts/backfill_eps_from_income.py            # 補最新可得年度的 Q1
  python scripts/backfill_eps_from_income.py --year 2026
"""

import os
import sys
import argparse
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
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 綜合損益表，依市場 × 行業別。漏掉 _fh 等於漏掉所有金控。
INCOME_ENDPOINTS = (
    [("上市", TWSE + f"t187ap06_L_{k}",         True)  for k in ("ci", "fh", "ins", "bd", "mim", "basi")]
    + [("上櫃", TPEX + f"mopsfin_t187ap06_O_{k}", False) for k in ("ci", "fh", "ins", "bd", "mim")]
    + [("興櫃", TPEX + f"mopsfin_t187ap06_U_{k}", False) for k in ("ci", "fh", "ins", "bd", "mim", "basi")]
)

EPS_COL = "基本每股盈餘（元）"


def field(row: dict, *names) -> str:
    """跨來源取欄位：TWSE 用中文欄名（年度／季別），TPEx 用英文（Year／Season）"""
    for n in names:
        v = row.get(n)
        if v is not None and str(v).strip() != "":
            return str(v).strip()
    return ""


def fetch_json(url: str, verify_ssl: bool) -> list:
    for attempt in range(3):
        try:
            resp = requests.get(url, timeout=30, verify=verify_ssl)
            data = resp.json()
            if isinstance(data, list):
                return data
        except Exception as e:
            print(f"  ⚠️  請求失敗（第 {attempt + 1} 次）{url}: {e}")
    return []


def stock_id_of(row: dict) -> str:
    """TWSE 用「公司代號」，TPEx 部分端點用 SecuritiesCompanyCode"""
    return field(row, "公司代號", "SecuritiesCompanyCode")


def to_eps(raw) -> float | None:
    if raw is None:
        return None
    text = str(raw).strip().replace(",", "")
    if not text or text in ("--", "N/A"):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def known_stock_ids() -> set[str]:
    ids, offset = set(), 0
    while True:
        resp = supabase.table("stocks").select("stock_id").range(offset, offset + 999).execute()
        rows = resp.data or []
        ids.update(r["stock_id"] for r in rows)
        if len(rows) < 1000:
            break
        offset += 1000
    return ids


def existing_q1(quarter_end: str) -> set[str]:
    """已有該 Q1 的股票，用來只對「新補上」者重算，並回報實際新增數"""
    ids, offset = set(), 0
    while True:
        resp = (supabase.table("eps_quarterly").select("stock_id")
                .eq("quarter_end_date", quarter_end)
                .range(offset, offset + 999).execute())
        rows = resp.data or []
        ids.update(r["stock_id"] for r in rows)
        if len(rows) < 1000:
            break
        offset += 1000
    return ids


def main():
    parser = argparse.ArgumentParser(description="用交易所綜合損益表補 Q1 EPS")
    parser.add_argument("--year", type=int, help="西元年（預設取端點回報的最新年度）")
    parser.add_argument("--no-recalc", action="store_true", help="只寫入，不重算 P/E")
    args = parser.parse_args()

    known = known_stock_ids()
    print(f"資料庫既有股票：{len(known)} 支\n")

    # 收集所有行業別的 Q1 EPS。年度一律以「民國」為內部單位，最後才 +1911 轉西元
    collected: dict[str, tuple[int, float]] = {}   # stock_id -> (roc_year, eps)
    for market, url, verify in INCOME_ENDPOINTS:
        data = fetch_json(url, verify)
        added = 0
        for r in data:
            if field(r, "季別", "Season") != "1":   # 只採 Q1
                continue
            sid = stock_id_of(r)
            eps = to_eps(r.get(EPS_COL))
            roc = field(r, "年度", "Year")
            if sid not in known or eps is None or not roc.isdigit():
                continue
            roc_year = int(roc)
            # 同股若多來源出現，取年度較新者
            if sid not in collected or roc_year > collected[sid][0]:
                collected[sid] = (roc_year, eps)
                added += 1
        label = url.rsplit("_", 1)[-1]
        print(f"  {market} ({label}): Q1 {added} 筆")

    if not collected:
        print("\n無資料，結束。")
        return

    # 決定目標民國年度（預設用資料中最新的，避免混入尚未換季的舊檔）
    # args.year 由使用者以「西元」輸入，先轉回民國與 collected 比對
    target_roc = (args.year - 1911) if args.year else max(y for y, _ in collected.values())
    west_year = target_roc + 1911                        # 民國 → 西元（元凶 bug：先前漏了這一步）
    quarter_end = f"{west_year}-03-31"
    rows = [{"stock_id": sid, "quarter_end_date": quarter_end, "eps": eps}
            for sid, (y, eps) in collected.items() if y == target_roc]
    print(f"\n目標季度：{quarter_end}（民國 {target_roc} 年 Q1），共 {len(rows)} 支")

    before = existing_q1(quarter_end)
    new_ids = [r["stock_id"] for r in rows if r["stock_id"] not in before]
    print(f"  其中資料庫已有：{len(rows) - len(new_ids)} 支｜新補上：{len(new_ids)} 支")

    for i in range(0, len(rows), 500):
        supabase.table("eps_quarterly").upsert(
            rows[i:i + 500], on_conflict="stock_id,quarter_end_date").execute()
    print("  寫入完成")

    if new_ids and not args.no_recalc:
        print(f"\n對新補上的 {len(new_ids)} 支重算 P/E 估值...")
        import calculate_valuation as cv
        cv.run(new_ids)

    print("\n完成！")


if __name__ == "__main__":
    main()
