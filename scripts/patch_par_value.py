"""
一次性修正：面額非 10 元的股票，每股淨值與股數全部算錯。

`download_balance_sheet.py` 原本硬編「面額 10 元」計算：
    BVPS = 10 × 股東權益 / 股本        股數 = 股本 / 10 / 1000
台灣多數股票面額確實是 10 元，但 KY 股與部分公司不是，這些公司因此全錯。

2026-07-22 由 `audit_external.py` 抓出：1,079 檔上市公司有 253 檔（23%）
每股淨值與交易所官方申報值不符，比值恰為面額比。災情實例：

    4763 材料*-KY  面額 1 元    每股淨值 218.17 → 實際 21.82   P/B 合理價 1,129.78（現價 50.3）
    6919 康霈*     面額 0.5 元  每股淨值 120.25 → 實際 6.02    P/B 合理價 892.43（現價 104.0）

錯誤的每股淨值使目標價虛高，這些股票會被判「便宜」而衝上排行榜。
連帶 shares_thousand 與 listed_shares 也錯，污染 P/S、P/FCF 的每股基準
與 P/E 的股數還原因子。

修法是確定性的單位換算，不是推估：既有值乘上面額比即為正確值，
故不必重跑 4 小時的 FinMind 下載。
    正確 BVPS   = 既有 BVPS   × 面額 / 10
    正確 股數   = 既有 股數   × 10 / 面額
`stocks.listed_shares` 則一律改用交易所公告的「已發行普通股數」——
那是官方值，且排除了庫藏股與特別股，優於任何推算。

用法：
  python scripts/patch_par_value.py --dry-run   # 只列出將修改的內容
  python scripts/patch_par_value.py
"""

import argparse
import os
import sys

from dotenv import load_dotenv
from supabase import create_client

sys.path.insert(0, os.path.dirname(__file__))
from download_balance_sheet import DEFAULT_PAR, fetch_par_values

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

CHUNK = 200


def fetch_rows(stock_ids: list[str]) -> list[dict]:
    """取出待修正股票的所有季度列。Supabase 預設 1000 筆上限，必須分頁且排序。"""
    rows = []
    for i in range(0, len(stock_ids), CHUNK):
        batch, offset = stock_ids[i:i + CHUNK], 0
        while True:
            page = (supabase.table("balance_sheet_quarterly")
                    .select("stock_id,quarter_end_date,book_value_per_share,"
                            "debt_ratio,shares_thousand")
                    .in_("stock_id", batch)
                    .order("stock_id").order("quarter_end_date")
                    .range(offset, offset + 999).execute().data)
            rows.extend(page)
            if len(page) < 1000:
                break
            offset += 1000
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="只列出將修改的內容")
    args = ap.parse_args()

    print("取得各股面額…")
    pars, official_shares = fetch_par_values()

    odd = {sid: par for sid, par in pars.items() if par != DEFAULT_PAR}
    print(f"\n面額非 10 元者 {len(odd)} 家：")
    for sid, par in sorted(odd.items())[:20]:
        print(f"  {sid}: {par} 元")
    if len(odd) > 20:
        print(f"  …另有 {len(odd) - 20} 家")

    # ── 1. 修正 balance_sheet_quarterly 的每股淨值與股數
    rows = fetch_rows(sorted(odd))
    print(f"\n待修正 {len(rows)} 季列（{len(odd)} 家）")

    fixed = []
    for r in rows:
        par = odd[r["stock_id"]]
        bvps = r["book_value_per_share"]
        shares = r["shares_thousand"]
        fixed.append({
            "stock_id":             r["stock_id"],
            "quarter_end_date":     r["quarter_end_date"],
            # 面額比是確定的換算係數，不是推估值
            "book_value_per_share": round(bvps * par / DEFAULT_PAR, 4) if bvps is not None else None,
            "debt_ratio":           r["debt_ratio"],       # 比率不受面額影響，原樣帶回
            "shares_thousand":      int(shares * DEFAULT_PAR / par) if shares else None,
        })

    print("\n修正前後對照（前 8 列）：")
    for old, new in list(zip(rows, fixed))[:8]:
        print(f"  {old['stock_id']} {old['quarter_end_date']}: "
              f"淨值 {old['book_value_per_share']} → {new['book_value_per_share']}，"
              f"股數 {old['shares_thousand']} → {new['shares_thousand']}")

    # ── 2. stocks.listed_shares 改用交易所公告的已發行普通股數（全體，不限面額異常者）
    current = {}
    offset = 0
    while True:
        page = (supabase.table("stocks").select("stock_id,listed_shares")
                .order("stock_id").range(offset, offset + 999).execute().data)
        current.update({r["stock_id"]: r["listed_shares"] for r in page})
        if len(page) < 1000:
            break
        offset += 1000

    share_updates = {sid: n for sid, n in official_shares.items()
                     if sid in current and current[sid] != n}
    print(f"\nlisted_shares 與交易所公告不符者 {len(share_updates)} 家（共 {len(current)} 家）")
    for sid, n in sorted(share_updates.items())[:8]:
        print(f"  {sid}: {current[sid]} → {n} 千股")

    if args.dry_run:
        print("\n[dry-run] 未寫入任何資料")
        return

    print(f"\n寫入 balance_sheet_quarterly（{len(fixed)} 列）…")
    for i in range(0, len(fixed), CHUNK):
        supabase.table("balance_sheet_quarterly").upsert(
            fixed[i:i + CHUNK], on_conflict="stock_id,quarter_end_date").execute()
        print(f"  {min(i + CHUNK, len(fixed))}/{len(fixed)}")

    print(f"\n更新 stocks.listed_shares（{len(share_updates)} 家）…")
    # 相同股數的股票可合併成一次 update；用 update 而非 upsert——
    # 只帶主鍵的 upsert 會在衝突解析前就違反 stocks.name 的 NOT NULL 約束
    by_value: dict[int, list[str]] = {}
    for sid, n in share_updates.items():
        by_value.setdefault(n, []).append(sid)
    done = 0
    for n, sids in by_value.items():
        for i in range(0, len(sids), CHUNK):
            supabase.table("stocks").update({"listed_shares": n}) \
                .in_("stock_id", sids[i:i + CHUNK]).execute()
        done += len(sids)
    print(f"  完成 {done} 家")

    print("\n✅ 修正完成。接著必須重算估值，否則畫面上仍是舊的目標價：")
    print("   python scripts/calculate_valuation.py")
    print("   python scripts/calculate_alt_valuations.py")
    print("   python scripts/audit_external.py      # 驗證 B 段歸零")


if __name__ == "__main__":
    main()
