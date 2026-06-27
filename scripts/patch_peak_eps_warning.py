"""
補丁腳本：為 TTM EPS 顯著高於 5 年均值（> 3 倍）的股票補上峰值獲利警告。
"""
import os, sys
sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
from dotenv import load_dotenv
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))
from supabase import create_client
sys.path.insert(0, os.path.dirname(__file__))
from calculate_valuation import calculate_valuation

supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

# 撈出 ttm_eps > normalized_eps * 3 且 normalized_eps > 0.5 且 warning 為空的股票
resp = (supabase.table("valuations")
        .select("stock_id,ttm_eps,normalized_eps,warning")
        .gt("normalized_eps", 0.5)
        .is_("warning", "null")
        .execute())

# 在 Python 端過濾峰值條件（Supabase 不支援欄位間比較）
targets = [r for r in resp.data if r["ttm_eps"] and r["ttm_eps"] > (r["normalized_eps"] or 0) * 3]
print(f"找到 {len(targets)} 支需要補峰值警告的股票")

updated = 0
for row in targets:
    sid = row["stock_id"]
    result = calculate_valuation(sid)
    if result and result.get("warning"):
        supabase.table("valuations").upsert(result).execute()
        print(f"  {sid} ttm={row['ttm_eps']} norm={row['normalized_eps']} -> 已補上")
        updated += 1

print(f"\n完成：補上 {updated} 支股票的峰值警告")
