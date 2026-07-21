"""
backfill_last_seen.py — 一次性回填 stocks.last_seen_date 與 delisted_at

daily_price_update.mark_delisted() 只維護「今天有出現的股票」，
既有的 last_seen_date 全為 NULL，而判定式刻意跳過 NULL（避免上線首日整批誤判下市）。
本腳本從 daily_prices 既有資料回推每支股票的最後報價日，把起始值補齊。

執行一次即可；之後由每日排程自動維護。
  python scripts/backfill_last_seen.py
  python scripts/backfill_last_seen.py --dry-run

查詢策略：先取「最新交易日有報價」的股票（一次分頁查詢即可涵蓋 94%），
只有缺席的少數才逐支查最後報價日——避免對全市場 2,400 支各打一次 API。
"""
import argparse
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

from dotenv import load_dotenv
from supabase import create_client

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))
URL, KEY = os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY")
supabase = create_client(URL, KEY)

ABSENT_DAYS = 21   # 與 daily_price_update.ABSENT_DAYS 一致
REFERENCE_STOCK = "2330"   # 交易日曆基準（權值股不會整月停牌）


def _paged(table: str, columns: str, **eq) -> list[dict]:
    rows, offset = [], 0
    while True:
        q = supabase.table(table).select(columns)
        for col, val in eq.items():
            q = q.eq(col, val)
        data = q.order("stock_id").range(offset, offset + 999).execute().data
        rows.extend(data)
        if len(data) < 1000:
            return rows
        offset += 1000


def last_price_date(stock_id: str) -> tuple[str, str | None]:
    """單支股票的最後報價日；每個執行緒各自建 client（supabase-py 非執行緒安全）"""
    sb = create_client(URL, KEY)
    data = (sb.table("daily_prices").select("date").eq("stock_id", stock_id)
            .order("date", desc=True).limit(1).execute().data)
    return stock_id, (data[0]["date"] if data else None)


def main():
    parser = argparse.ArgumentParser(description="回填 stocks.last_seen_date / delisted_at")
    parser.add_argument("--dry-run", action="store_true", help="只列出結果，不寫入")
    args = parser.parse_args()

    latest = (supabase.table("daily_prices").select("date").eq("stock_id", REFERENCE_STOCK)
              .order("date", desc=True).limit(1).execute().data[0]["date"])
    print(f"最新交易日：{latest}")

    all_ids = [r["stock_id"] for r in _paged("stocks", "stock_id")]
    alive = {r["stock_id"] for r in _paged("daily_prices", "stock_id", date=latest)}
    missing = [s for s in all_ids if s not in alive]
    print(f"股票 {len(all_ids)} 支；最新交易日有報價 {len(alive & set(all_ids))} 支，缺席 {len(missing)} 支")

    last_seen = {s: latest for s in all_ids if s in alive}
    with ThreadPoolExecutor(max_workers=8) as pool:
        for sid, d in pool.map(last_price_date, missing):
            if d:                      # 從無任何報價者留 NULL，不猜
                last_seen[sid] = d

    cutoff = (date.fromisoformat(latest) - timedelta(days=ABSENT_DAYS)).isoformat()
    dead = sorted(s for s, d in last_seen.items() if d < cutoff)
    print(f"最後報價日早於 {cutoff} → 判定下市：{len(dead)} 檔")
    print(f"從無報價紀錄（保留 NULL）：{len(all_ids) - len(last_seen)} 檔")

    if args.dry_run:
        for s in dead[:20]:
            print(f"  [DRY] {s} 末次報價 {last_seen[s]}")
        return

    # 必須用 UPDATE 而非 upsert：upsert 會先嘗試 INSERT，而 stocks.name / market
    # 是 NOT NULL，只帶 stock_id 的列會在衝突解析前就違反約束。
    # 同一個 last_seen_date 的股票可合併成一次請求，代碼清單分批避免 URL 過長。
    by_date: dict[str, list[str]] = {}
    for sid, d in last_seen.items():
        by_date.setdefault(d, []).append(sid)

    done = 0
    for d, sids in by_date.items():
        payload = {"last_seen_date": d, "delisted_at": (d if d < cutoff else None)}
        for i in range(0, len(sids), 200):
            supabase.table("stocks").update(payload).in_("stock_id", sids[i:i + 200]).execute()
            done += len(sids[i:i + 200])
    print(f"完成：寫入 {done} 檔的 last_seen_date，其中 {len(dead)} 檔標記為已下市")


if __name__ == "__main__":
    main()
