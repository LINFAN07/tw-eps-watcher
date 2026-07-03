"""
負債比回填腳本
從 balance_sheet_quarterly 一次批次撈出所有股票的最新負債比，
批次 upsert 到 valuations.debt_ratio。

執行前提：
  1. 已在 Supabase 執行 schema.sql 的 ALTER TABLE 語句（新增 debt_ratio 欄位）
  2. 已重新執行 download_balance_sheet.py 以填入 balance_sheet_quarterly.debt_ratio

用法：
  python scripts/patch_debt_ratio.py
"""

import os
import sys
from dotenv import load_dotenv
from supabase import create_client

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

BATCH_SIZE = 500  # Supabase upsert 單批上限


def main():
    # 一次分頁撈出所有有 debt_ratio 的季度資料，按 stock_id ASC, quarter_end_date DESC
    # 使 Python 端只要取每 stock_id 第一次出現的記錄即為最新一季
    print("讀取 balance_sheet_quarterly 負債比資料...")
    all_rows: list[dict] = []
    offset = 0
    while True:
        resp = (
            supabase.table("balance_sheet_quarterly")
            .select("stock_id,quarter_end_date,debt_ratio")
            .not_.is_("debt_ratio", "null")
            .order("stock_id", desc=False)
            .order("quarter_end_date", desc=True)
            .range(offset, offset + 999)
            .execute()
        )
        batch = resp.data or []
        all_rows.extend(batch)
        if len(batch) < 1000:
            break
        offset += 1000
    print(f"  讀取 {len(all_rows)} 筆（含歷史各季）")

    # 取每支股票最新一季（已按 quarter_end_date DESC，同 stock_id 第一筆即最新）
    seen: set[str] = set()
    records: list[dict] = []
    for r in all_rows:
        sid = r["stock_id"]
        if sid not in seen:
            seen.add(sid)
            records.append({"stock_id": sid, "debt_ratio": r["debt_ratio"]})
    print(f"  共 {len(records)} 支股票有負債比資料")

    # 撈出已在 valuations 的股票清單，篩除後再批次 upsert
    # （避免 upsert 對不存在的股票 INSERT 骨架列，清空其他欄位）
    existing: set[str] = set()
    offset2 = 0
    while True:
        resp2 = supabase.table("valuations").select("stock_id").range(offset2, offset2 + 999).execute()
        batch2 = resp2.data or []
        existing.update(r["stock_id"] for r in batch2)
        if len(batch2) < 1000:
            break
        offset2 += 1000
    print(f"  valuations 現有 {len(existing)} 支股票")

    # 只保留已在 valuations 的記錄，確保走 UPDATE 而非 INSERT
    to_write = [r for r in records if r["stock_id"] in existing]
    skipped  = len(records) - len(to_write)
    if skipped:
        print(f"  略過 {skipped} 支（不在 valuations，尚未跑過估值計算）")

    # 批次 upsert（全部走 ON CONFLICT UPDATE 路徑，安全）
    for i in range(0, len(to_write), BATCH_SIZE):
        chunk = to_write[i:i + BATCH_SIZE]
        supabase.table("valuations").upsert(chunk, on_conflict="stock_id").execute()
        print(f"  已寫入 {min(i + BATCH_SIZE, len(to_write))}/{len(to_write)} 筆")

    print(f"\n✅ 完成：更新 {len(to_write)} 支股票負債比")


if __name__ == "__main__":
    main()
