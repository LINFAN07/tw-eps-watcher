"""
週採樣瘦身執行器 — 呼叫 sql/thin_daily_prices.sql 定義的資料庫函式。

用途：把 3 個月前的每日股價降為「每週最後一個交易日」，解決 Supabase
免費層 500MB 的容量壓力（2026-07-21 實測已用 92.9%、每年增長約 50MB）。

前置作業（缺一不可）：
  1. 在 Supabase SQL Editor 執行 sql/thin_daily_prices.sql 建立函式
  2. calculate_valuation.to_weekly() 必須已上線並完成全庫重算
     （否則混合密度會使近期價格權重放大約 5 倍，污染估值帶）

用法：
  python scripts/thin_daily_prices.py --dry-run   # 只統計會刪多少，不動資料
  python scripts/thin_daily_prices.py             # 實際執行

執行後請在 SQL Editor 跑一次 `VACUUM (ANALYZE) daily_prices;`
讓空間回到 free space 供後續寫入重用（切勿用 VACUUM FULL，見 SQL 檔說明）。
"""

import argparse
import os
import sys
from calendar import monthrange
from datetime import date

from dotenv import load_dotenv
from supabase import create_client

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

REFERENCE_STOCK = "2330"   # 交易日曆參考股：權值股不會整月停牌
KEEP_DAILY_MONTHS = 3      # 近幾個月保留每日（看門狗、現價判定、跨來源比對需要）
BATCH_SIZE = 50            # 每次處理幾支股票


def latest_trading_date() -> str:
    """
    取得資料本身的最新交易日。
    不可用系統時間回推：休市、來源延遲都會讓系統日期與資料日期脫節，
    以系統時間當基準會誤刪還在「近 3 個月」保護範圍內的資料。
    """
    resp = (supabase.table("daily_prices").select("date")
            .eq("stock_id", REFERENCE_STOCK).order("date", desc=True).limit(1).execute())
    if not resp.data:
        raise RuntimeError(f"找不到參考股 {REFERENCE_STOCK} 的股價，無法決定 cutoff")
    return resp.data[0]["date"]


def cutoff_date(latest: str) -> str:
    """
    latest 往前推 KEEP_DAILY_MONTHS 個月（純日期運算，不碰系統時間）。
    用標準庫而非 pandas：這支腳本要掛進 workflow，
    為了一行日期運算讓 CI 多裝 pandas 不划算。
    """
    d = date.fromisoformat(latest)
    m = d.month - KEEP_DAILY_MONTHS
    y, m = d.year + (m - 1) // 12, (m - 1) % 12 + 1
    # 若目標月沒有該日（例如 5/31 往前推到 2/31），退到當月最後一天
    return str(d.replace(year=y, month=m, day=min(d.day, monthrange(y, m)[1])))


def all_stock_ids() -> list[str]:
    ids, offset = [], 0
    while True:
        rows = (supabase.table("stocks").select("stock_id")
                .order("stock_id").range(offset, offset + 999).execute().data)
        ids.extend(r["stock_id"] for r in rows)
        if len(rows) < 1000:
            return ids
        offset += 1000


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="只統計會刪多少，不實際刪除")
    args = ap.parse_args()

    latest = latest_trading_date()
    cutoff = cutoff_date(latest)
    ids = all_stock_ids()
    mode = "試算" if args.dry_run else "執行"
    print(f"{mode}週採樣瘦身：資料最新日 {latest}，cutoff {cutoff}（更早者只留每週最後交易日）")
    print(f"共 {len(ids)} 支股票，每批 {BATCH_SIZE} 支\n")

    total, failed = 0, []
    for i in range(0, len(ids), BATCH_SIZE):
        batch = ids[i:i + BATCH_SIZE]
        try:
            n = supabase.rpc("thin_daily_prices", {
                "p_stock_ids": batch, "p_cutoff": cutoff, "p_dry_run": args.dry_run,
            }).execute().data
        except Exception as e:
            # 單批失敗不中斷（可重跑，函式具冪等性），但收尾要讓工作失敗
            print(f"  [{i // BATCH_SIZE + 1}] 失敗: {str(e)[:120]}")
            failed.append(batch)
            continue
        total += n or 0
        print(f"  [{i // BATCH_SIZE + 1}/{(len(ids) - 1) // BATCH_SIZE + 1}] "
              f"{batch[0]}~{batch[-1]}: {n:,} 列，累計 {total:,}")

    print(f"\n{mode}完成，共 {total:,} 列")
    if args.dry_run:
        print("確認數字合理後，拿掉 --dry-run 重跑")
    else:
        print("請在 Supabase SQL Editor 執行：VACUUM (ANALYZE) daily_prices;")

    if failed:
        # 吞掉失敗會讓呼叫端把故障當成「沒東西可刪」，必須讓工作失敗
        print(f"\n有 {len(failed)} 批失敗，未完整瘦身", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
