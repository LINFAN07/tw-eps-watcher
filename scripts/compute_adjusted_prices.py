"""
compute_adjusted_prices.py — 除權息後向還原股價（自有 dividends 表自建）

## 為什麼

close_price 是原始收盤價，除權息當天的機械性下跌會被 P/E、P/B 河流圖當成
基本面訊號，讓高殖利率股的歷史估值帶長期偏移（實測長榮 75%、台塑 59%、
國泰金 25%，台積電僅 5%）。FinMind 還原股價是付費資料集，故以自有 dividends
自建「後向還原序列」寫入 daily_prices.adjusted_close（衍生欄，不覆蓋原始價）。

## 後向還原演算法

- 每個除息日 d 的還原因子 factor_d = 1 − 現金股利 / 除息前一交易日收盤價。
- adjusted(t) = close(t) × ∏ factor_d（對所有 ex_date d > t）。
- 錨定於今日：最新一日沒有更晚的除息日，factor 連乘為 1，故 adjusted 最新一日
  == close 最新一日——現價與現在的本益比不變，只有歷史被還原下移。

## 資料誠信

- 只處理有股利記錄的股票；無配息者 adjusted_close 留 null，查詢端 COALESCE 回退原始價。
- 只寫入 adjusted 與原始「有差異」的歷史列（除息前的列）；最新段 factor=1 的列留 null，
  回退即原始價，兩者一致。
- 自檢：還原今日 == 原始今日；否則該股拋警不寫，避免寫入錯誤序列。

用法：
  python scripts/compute_adjusted_prices.py
  python scripts/compute_adjusted_prices.py --only 2882 1301   # 指定股票（驗證用）
  python scripts/compute_adjusted_prices.py --dry-run          # 不寫入，僅印摘要
"""

import os
import sys
import bisect
import argparse
from dotenv import load_dotenv
from supabase import create_client

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

WRITE_EPSILON = 0.01   # 還原與原始差異小於 1 分即視為無調整，不寫（回退原始價）


def back_adjust(dates: list[str], closes: list[float],
                ex_list: list[tuple[str, float]]) -> list[float]:
    """
    後向還原。回傳與 dates 對齊的還原價陣列。純函式，供單元測試。

    dates 須為升冪。ex_list 為 (除息日, 現金股利)。
    只採計「除息日 ≤ 最後交易日」且能取得除息前收盤價者，確保最新一日 factor=1。
    """
    if not dates:
        return []
    last_date = dates[-1]

    # 每個除息日的還原因子，用除息前一交易日收盤價當基準
    factors: list[tuple[str, float]] = []
    for ex_date, cash in ex_list:
        if cash is None or cash <= 0 or ex_date > last_date:
            continue
        i = bisect.bisect_left(dates, ex_date)   # 第一個 >= ex_date 的位置
        if i == 0:
            continue                             # 除息日早於所有股價，無基準可算
        prev_close = closes[i - 1]               # 除息前最後一個交易日收盤價
        f = 1.0 - cash / prev_close
        if f <= 0 or f > 1:
            continue                             # 股利 ≥ 前收（資料異常），跳過該筆
        factors.append((ex_date, f))

    factors.sort()                               # 依除息日升冪
    adjusted = [0.0] * len(dates)
    cum = 1.0
    j = len(factors) - 1                         # 由最晚的除息日往回套用
    for k in range(len(dates) - 1, -1, -1):
        # 套用所有「晚於本日」的除息因子（factor 作用於除息日之前的所有日）
        while j >= 0 and factors[j][0] > dates[k]:
            cum *= factors[j][1]
            j -= 1
        adjusted[k] = closes[k] * cum
    return adjusted


def _fetch_paged(table: str, filters: dict, columns: str) -> list:
    all_rows, offset = [], 0
    order_col = columns.split(",")[0]
    while True:
        q = supabase.table(table).select(columns)
        for col, val in filters.items():
            q = q.eq(col, val)
        resp = q.order(order_col).range(offset, offset + 999).execute()
        all_rows.extend(resp.data)
        if len(resp.data) < 1000:
            break
        offset += 1000
    return all_rows


def dividend_paying_stock_ids() -> list[str]:
    """有股利記錄的股票代碼（其餘無需還原，回退原始價即可）"""
    rows = _fetch_paged("dividends", {}, "stock_id,ex_date")
    return sorted({r["stock_id"] for r in rows})


def process_stock(stock_id: str, dry_run: bool) -> tuple[int, str | None]:
    """
    計算並寫入單支股票的 adjusted_close。
    回傳 (寫入列數, 警告訊息or None)。
    """
    prices = _fetch_paged("daily_prices", {"stock_id": stock_id}, "date,close_price")
    if not prices:
        return 0, None
    dates  = [r["date"] for r in prices]
    closes = [float(r["close_price"]) for r in prices]

    divs = _fetch_paged("dividends", {"stock_id": stock_id}, "ex_date,cash_dividend")
    ex_list = [(d["ex_date"], float(d["cash_dividend"])) for d in divs]

    adjusted = back_adjust(dates, closes, ex_list)

    # 自檢：後向還原錨定今日，最新一日必須與原始價一致，否則序列有誤
    if abs(adjusted[-1] - closes[-1]) > WRITE_EPSILON:
        return 0, (f"{stock_id} 還原今日 {adjusted[-1]:.2f} ≠ 原始今日 {closes[-1]:.2f}，"
                   "序列異常，跳過不寫")

    # 只寫「有實際調整」的列（除息前）；最新段 factor=1 的列留 null 回退原始價
    rows = [{"stock_id": stock_id, "date": dates[k],
             "close_price": round(closes[k], 2),
             "adjusted_close": round(adjusted[k], 2)}
            for k in range(len(dates))
            if abs(adjusted[k] - closes[k]) >= WRITE_EPSILON]

    if not dry_run:
        for i in range(0, len(rows), 500):
            supabase.table("daily_prices").upsert(rows[i:i + 500]).execute()
    return len(rows), None


def main():
    parser = argparse.ArgumentParser(description="除權息後向還原股價")
    parser.add_argument("--only", nargs="*", help="只處理指定股票代碼")
    parser.add_argument("--dry-run", action="store_true", help="不寫入，僅印摘要")
    args = parser.parse_args()

    ids = args.only if args.only else dividend_paying_stock_ids()
    print(f"待還原（有股利）股票：{len(ids)} 支{'（dry-run）' if args.dry_run else ''}\n")

    written_total, warnings = 0, []
    for idx, sid in enumerate(ids, 1):
        written, warn = process_stock(sid, args.dry_run)
        written_total += written
        if warn:
            warnings.append(warn)
            print(f"  [{idx}/{len(ids)}] ⚠️  {warn}")
        else:
            print(f"  [{idx}/{len(ids)}] {sid}: 還原 {written} 列")

    print(f"\n✅ 完成，共還原 {written_total} 列")
    if warnings:
        print(f"⚠️  {len(warnings)} 支序列異常已跳過（見上）")


if __name__ == "__main__":
    main()
