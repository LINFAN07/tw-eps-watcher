"""
補丁腳本：為 TTM EPS 與常態化 EPS 皆偏低的股票補上 warning 欄位。
只處理需要更新的股票，不重跑全量。
"""
import os, sys
sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
from dotenv import load_dotenv
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))
from supabase import create_client
sys.path.insert(0, os.path.dirname(__file__))
from calculate_valuation import calculate_valuation

supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

# 撈出 TTM 和 normalized_eps 皆 <= 0.5 且 warning 為空的股票
resp = (supabase.table("valuations")
        .select("stock_id,ttm_eps,normalized_eps,warning")
        .lte("ttm_eps", 0.5)
        .lte("normalized_eps", 0.5)
        .is_("warning", "null")
        .execute())

targets = resp.data
print(f"找到 {len(targets)} 支需要補 warning 的股票")

updated = 0
for row in targets:
    sid = row["stock_id"]
    result = calculate_valuation(sid)
    if result and result.get("warning"):
        supabase.table("valuations").upsert(result).execute()
        print(f"  {sid} -> warning 已補上")
        updated += 1
    else:
        print(f"  {sid} -> 無需更新")

print(f"\n完成：補上 {updated} 支股票的 warning")
