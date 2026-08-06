"""
月營收缺口偵測與回補

## 為什麼需要這支

三個交易所月營收端點（`t187ap05_L`／`mopsfin_t187ap05_O`／`t187ap05_R`）都只回傳
**單月快照**——整份檔案的 `資料年月` 是同一個值。`update_fundamentals.py` 只寫當月，
沒有任何回補路徑，所以某公司在當月批次缺席，那個月就永久補不回，
與 CLAUDE.md 記載的 TPEx 除權息因子是同一個結構問題。

FinMind `TaiwanStockMonthRevenue` 可回溯 10 年，是唯一的補救來源。

## 偵測的兩種洞

1. **區間內缺月**：該股最早與最新月份之間少了某幾個月
2. **落後市場**：該股最新月份比全市場最新月份舊（漏掉最近幾次批次）

## 盲區（新增規則先問盲區在哪——CLAUDE.md 的要求）

- 看不到「從未被收錄」的公司（`stocks` 有、`monthly_revenue` 一筆都沒有）。
  那是初次下載的範疇，不是缺口回補。
- 看不到「值錯了」，只看得到「沒有值」。跨來源比對是 `audit_external.py` 的事。
- FinMind 也沒有的月份補不回來（多為近期上市，來源歷史起點就晚）。這類每次
  執行都會重試一遍，代價每檔 6.5 秒；檔數少故不另建「已知補不回」的狀態表，
  多一張表要維護的成本高於每月多花的幾十秒。
- 落後市場只追 `MAX_TRAILING_MONTHS` 個月。再久的多半是實質停止營運卻沒被標
  下市，無限往回追只會每月浪費呼叫。這類會列在摘要裡，需人工判斷。

用法：
  python scripts/backfill_revenue_gaps.py              # 偵測並回補
  python scripts/backfill_revenue_gaps.py --dry-run    # 只偵測不寫入
  python scripts/backfill_revenue_gaps.py --limit 500  # 放寬單次回補上限
"""

import argparse
import os
import sys
import time
from datetime import date
from dotenv import load_dotenv
from supabase import create_client
import finmind_client as fm

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

FINMIND_TOKEN = os.getenv("FINMIND_TOKEN")
CALL_INTERVAL = 6.5

# 單次回補的股票數上限。全市場整月漏跑需 2,300 × 6.5 秒 ≈ 4.2 小時，
# 會撐爆 GitHub Actions 的免費額度；預設 300 檔約 33 分鐘。
# 超出的部分【一定要印出來】——靜默截斷會讓人以為補完了（CLAUDE.md：不得靜默設限）。
DEFAULT_LIMIT = 300

# 落後市場最多往回追幾個月，見模組說明的盲區
MAX_TRAILING_MONTHS = 12

supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))


def _fetch_paged(table: str, columns: str) -> list:
    rows, offset = [], 0
    while True:
        resp = (supabase.table(table).select(columns)
                .order("stock_id").range(offset, offset + 999).execute())
        rows.extend(resp.data or [])
        if len(resp.data or []) < 1000:
            break
        offset += 1000
    return rows


def _index(ym: str) -> int:
    """YYYY-MM → 月份序號。轉成整數後加減月份不必處理跨年進位"""
    return int(ym[:4]) * 12 + int(ym[5:7]) - 1


def _month(index: int) -> str:
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


def month_range(start: str, end: str) -> list[str]:
    """含頭含尾的連續月份清單，格式 YYYY-MM"""
    return [_month(i) for i in range(_index(start), _index(end) + 1)]


def find_gaps() -> tuple[dict[str, list[str]], list[str]]:
    """
    回傳 ({stock_id: 缺少的月份}, 落後太久而放棄追的股票)。
    只看未下市股票——已下市者停止申報是正常的，不是缺口。
    """
    alive = {s["stock_id"] for s in _fetch_paged("stocks", "stock_id,delisted_at")
             if not s["delisted_at"]}

    have: dict[str, set[str]] = {}
    for r in _fetch_paged("monthly_revenue", "stock_id,year_month"):
        if r["stock_id"] in alive:
            have.setdefault(r["stock_id"], set()).add(r["year_month"][:7])

    # 市場最新月份＝多數公司已申報的月份。取單一最大值會被個別早報公司拉高，
    # 使全市場都被判定「落後一個月」，於是每次執行都在追一個還沒到的月份。
    latest_counts: dict[str, int] = {}
    for months in have.values():
        if months:
            latest_counts[max(months)] = latest_counts.get(max(months), 0) + 1
    if not latest_counts:
        return {}, []
    market_latest = max(latest_counts, key=lambda m: (latest_counts[m], m))

    floor = _month(_index(market_latest) - MAX_TRAILING_MONTHS)

    gaps: dict[str, list[str]] = {}
    abandoned: list[str] = []
    for sid, months in have.items():
        latest = max(months)
        if latest < floor:
            abandoned.append(sid)          # 停更太久，交人工判斷
            continue
        # 區間內缺月 + 落後市場的那幾個月，一次算完
        missing = [m for m in month_range(min(months), market_latest) if m not in months]
        if missing:
            gaps[sid] = missing
    return gaps, abandoned


def backfill(stock_id: str, wanted: set[str]) -> tuple[int, list[str]]:
    """從 FinMind 取回該股月營收，只寫入缺少的月份。回傳（寫入數, 仍缺的月份）"""
    # start_date 是必填參數，省略會拿到 status=400「start_date parameter is missing」，
    # 而 fm.fetch 會忠實地重試三次後拋錯——整批就這樣慢慢失敗。
    # 取最早的缺月當起點：既滿足必填，也不必抓回用不到的十年資料。
    raw = fm.fetch("TaiwanStockMonthRevenue", stock_id, f"{min(wanted)}-01", FINMIND_TOKEN)

    rows = []
    for r in raw:
        y, m, rev = r.get("revenue_year"), r.get("revenue_month"), r.get("revenue")
        if not y or not m or rev is None:
            continue
        ym = f"{int(y):04d}-{int(m):02d}"
        if ym not in wanted:
            continue
        # 負營收照寫，見 download_monthly_revenue.download_stock_revenue() 的說明
        rows.append({"stock_id": stock_id, "year_month": f"{ym}-01",
                     "revenue": int(float(str(rev).replace(",", "")))})

    if rows:
        supabase.table("monthly_revenue").upsert(
            rows, on_conflict="stock_id,year_month").execute()
    return len(rows), sorted(wanted - {r["year_month"][:7] for r in rows})


def main():
    ap = argparse.ArgumentParser(description="月營收缺口偵測與回補")
    ap.add_argument("--dry-run", action="store_true", help="只偵測不寫入")
    ap.add_argument("--limit", type=int, default=DEFAULT_LIMIT,
                    help=f"單次回補的股票數上限（預設 {DEFAULT_LIMIT}）")
    args = ap.parse_args()

    print(f"偵測月營收缺口…（{date.today()}）")
    gaps, abandoned = find_gaps()
    total_months = sum(len(v) for v in gaps.values())
    print(f"  有缺口的股票：{len(gaps)} 支，合計 {total_months} 個月")
    if abandoned:
        print(f"  ⚠️  停更逾 {MAX_TRAILING_MONTHS} 個月而未追的：{len(abandoned)} 支"
              f"（{', '.join(sorted(abandoned)[:10])}{'…' if len(abandoned) > 10 else ''}）"
              f"——請確認是否已實質下市")

    if not gaps:
        print("✅ 無缺口")
        return

    for sid, months in sorted(gaps.items(), key=lambda kv: -len(kv[1]))[:20]:
        print(f"    {sid}: 缺 {len(months)} 個月（{months[0]} ~ {months[-1]}）")

    if args.dry_run:
        print("\n--dry-run：不寫入")
        return

    targets = sorted(gaps, key=lambda s: -len(gaps[s]))[:args.limit]
    if len(gaps) > args.limit:
        print(f"\n⚠️  本次只處理缺口最多的 {args.limit} 支，剩餘 {len(gaps) - args.limit} 支"
              f"未處理——請以 --limit 放寬後手動補完，或等下次排程繼續")

    print(f"\n開始回補 {len(targets)} 支（FinMind 每次間隔 {CALL_INTERVAL} 秒）…")
    tracker = fm.FailureTracker("月營收缺口回補")
    filled, unfillable = 0, []
    for i, sid in enumerate(targets, 1):
        try:
            n, still = backfill(sid, set(gaps[sid]))
        except fm.FinMindError as e:
            tracker.record(sid, e)
            n, still = 0, []
        filled += n
        if still:
            unfillable.append((sid, len(still)))
        print(f"[{i}/{len(targets)}] {sid}: 補回 {n} 個月"
              + (f"，FinMind 也沒有 {len(still)} 個月" if still else ""))
        time.sleep(CALL_INTERVAL)

    print(f"\n✅ 補回 {filled} 筆月營收")
    if unfillable:
        print(f"來源本身沒有、補不回的：{len(unfillable)} 支"
              f"（{', '.join(f'{s}×{n}' for s, n in unfillable[:10])}"
              f"{'…' if len(unfillable) > 10 else ''}）——多為近期上市，FinMind 歷史起點就晚")
    tracker.finish()   # 抓取失敗要讓工作失敗，不得吞掉（資料誠信原則第 5 條）


if __name__ == "__main__":
    main()
