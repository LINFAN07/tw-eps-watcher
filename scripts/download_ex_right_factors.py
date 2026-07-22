"""
除權息還原因子下載：存交易所公告的「除權息前收盤價」與「除權息參考價」。

## 為什麼不自己算

原本的還原因子由現金股利與配股推算：
    factor = (前收 − 現金股利) ÷ (前收 × (1 + 配股率))
這條公式對「只有配息配股」的情況完全正確（2026-07-22 實測 1808／2540／3056
與交易所公告參考價分毫不差），但涵蓋不了現金增資與減資。

`audit_external.py` 首次量化這個缺口：近 20 天 217 筆除權息中 6 筆對不上，
全部是現金增資造成的。其中 3028 零壹配息配股皆為 0、只辦現金增資，
`dividends` 表根本沒有那筆資料，等於完全沒還原。

與其繼續往公式裡疊條款（現金增資的認股率定義、減資要分現金減資與彌補虧損），
不如直接存交易所算好的兩個價格——它們涵蓋所有情況，包括未來出現的新型態。

## 兩個市場的落差（必須講明，不可假裝一致）

    上市 TWT49U               2016-01 起，支援 10 年區間查詢，一次請求 10,694 筆
    上櫃 tpex_exright_daily   只有當日（約 8 筆），無歷史

因此上櫃／興櫃的歷史除權息仍走自算路徑，現狀不變、不會變差；
每日執行會讓上櫃的官方因子逐步累積。

用法：
  python scripts/download_ex_right_factors.py                # 每日增量（近 30 天）
  python scripts/download_ex_right_factors.py --backfill     # 上市 10 年全量回補
"""

import argparse
import os
import sys
import time
from datetime import date, timedelta

import requests
import urllib3
from dotenv import load_dotenv
from supabase import create_client

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

TWSE_URL = "https://www.twse.com.tw/rwd/zh/exRight/TWT49U"
TPEX_URL = "https://www.tpex.org.tw/openapi/v1/tpex_exright_daily"
CHUNK = 500


class FetchError(Exception):
    """來源故障。與「該期間確實沒有除權息」不同，必須讓工作失敗而非靜默通過。"""


def get(url: str, verify: bool = True, **params):
    last = None
    for attempt in range(3):
        try:
            data = requests.get(url, params=params or None, timeout=90, verify=verify).json()
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                stat = str(data.get("stat", ""))
                if stat == "OK":
                    return data.get("data") or []
                # 休市日與無除權息的日子會回這句，那是正常結果不是故障
                if "沒有符合條件的資料" in stat:
                    return []
            last = f"回應格式非預期：{str(data)[:120]}"
        except Exception as e:
            last = str(e)
        print(f"  ⚠️  第 {attempt + 1} 次請求失敗：{last}")
        time.sleep(2 * (attempt + 1))
    raise FetchError(f"{url} 連續 3 次失敗：{last}")


def to_float(raw) -> float | None:
    text = str(raw or "").strip().replace(",", "")
    if not text or text in ("--", "N/A", "0.00"):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def roc_to_iso(raw: str) -> str | None:
    """
    民國日期轉西元。TWSE 回「115年07月22日」，TPEx 回「1150722」。
    民國年一律 +1911——漏轉會寫出公元 115 年的日期（2026-07 有過事故）。
    """
    text = str(raw or "").strip()
    digits = "".join(c for c in text if c.isdigit())
    if len(digits) == 7:                       # 1150722
        y, m, d = digits[:3], digits[3:5], digits[5:]
    elif "年" in text:                          # 115年07月22日
        y, rest = text.split("年")
        m, d = rest.replace("日", "").split("月")
    else:
        return None
    try:
        return f"{int(y) + 1911}-{int(m):02d}-{int(d):02d}"
    except ValueError:
        return None


def fetch_twse(start: date, end: date) -> list[dict]:
    """上市：欄位順序為 [資料日期, 股票代號, 名稱, 除權息前收盤價, 除權息參考價, …]"""
    rows = get(TWSE_URL, startDate=f"{start:%Y%m%d}", endDate=f"{end:%Y%m%d}",
               response="json")
    out = []
    for r in rows:
        ex_date, sid = roc_to_iso(r[0]), str(r[1]).strip()
        prev, ref = to_float(r[3]), to_float(r[4])
        if ex_date and sid and prev and ref:
            out.append({"stock_id": sid, "ex_date": ex_date, "prev_close": prev,
                        "ref_price": ref, "source": "TWSE"})
    print(f"  上市 {start:%Y-%m-%d}~{end:%Y-%m-%d}：{len(rows)} 筆，可用 {len(out)} 筆")
    return out


def fetch_tpex() -> list[dict]:
    """上櫃：只有當日資料，欄位為英文名"""
    rows = get(TPEX_URL, verify=False)
    out = []
    for r in rows:
        ex_date = roc_to_iso(r.get("Date"))
        sid = str(r.get("SecuritiesCompanyCode", "")).strip()
        prev = to_float(r.get("ClosePriceBeforeExRightsDiviend"))
        ref = to_float(r.get("ExRightsDiviendQuote"))
        if ex_date and sid and prev and ref:
            out.append({"stock_id": sid, "ex_date": ex_date, "prev_close": prev,
                        "ref_price": ref, "source": "TPEX"})
    print(f"  上櫃當日：{len(rows)} 筆，可用 {len(out)} 筆")
    return out


def save(rows: list[dict]) -> int:
    for i in range(0, len(rows), CHUNK):
        supabase.table("ex_right_factors").upsert(
            rows[i:i + CHUNK], on_conflict="stock_id,ex_date").execute()
    return len(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backfill", action="store_true", help="上市 10 年全量回補")
    ap.add_argument("--days", type=int, default=30, help="增量模式回溯天數")
    args = ap.parse_args()

    today = date.today()
    if args.backfill:
        print("全量回補上市 10 年除權息…")
        rows = fetch_twse(today - timedelta(days=365 * 10), today)
    else:
        print(f"增量更新近 {args.days} 天…")
        rows = fetch_twse(today - timedelta(days=args.days), today)
    rows += fetch_tpex()

    if not rows:
        print("期間內沒有除權息資料")
        return

    n = save(rows)
    bad = [r for r in rows if not 0 < r["ref_price"] / r["prev_close"] <= 1.5]
    print(f"\n✅ 寫入 {n} 筆")
    print(f"   還原因子範圍 {min(r['ref_price'] / r['prev_close'] for r in rows):.4f}"
          f" ~ {max(r['ref_price'] / r['prev_close'] for r in rows):.4f}")
    if bad:
        # 因子應落在 (0, 1]；>1 代表參考價高於前收（減資會如此），須人工確認
        print(f"   ⚠️  因子超出 (0, 1.5] 的有 {len(bad)} 筆：")
        for r in bad[:5]:
            print(f"      {r['stock_id']} {r['ex_date']}: "
                  f"{r['prev_close']} → {r['ref_price']}")


if __name__ == "__main__":
    try:
        main()
    except FetchError as e:
        print(f"\n❌ 中止（來源故障）：{e}")
        sys.exit(1)
