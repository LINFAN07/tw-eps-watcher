"""
補填 stocks.industry 欄位
從 FinMind TaiwanStockInfo 取得 industry_category，單次 API 呼叫更新全部股票。
"""

import os
import sys
import requests
from dotenv import load_dotenv
from supabase import create_client

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

FINMIND_API  = "https://api.finmindtrade.com/api/v4/data"
FINMIND_TOKEN = os.getenv("FINMIND_TOKEN")
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))


def run():
    print("取得 FinMind TaiwanStockInfo...")
    resp = requests.get(FINMIND_API, params={"dataset": "TaiwanStockInfo", "token": FINMIND_TOKEN}, timeout=30).json()
    if resp.get("status") != 200:
        print(f"API 錯誤: {resp.get('msg')}")
        return

    raw = resp.get("data", [])
    # 只取 4 位數字代碼（排除 ETF、存託憑證等）
    updates = [
        {"stock_id": str(r["stock_id"]).strip(), "industry": r.get("industry_category", "其他")}
        for r in raw
        if str(r.get("stock_id", "")).strip().isdigit() and len(str(r.get("stock_id", "")).strip()) == 4
    ]

    # 只更新資料庫中已存在的股票（避免插入空名稱新股造成 NOT NULL 錯誤）
    industry_map = {r["stock_id"]: r["industry"] for r in updates}

    # 用 page 變數避免覆蓋上方的 FinMind resp
    existing_ids, offset = [], 0
    while True:
        page = supabase.table("stocks").select("stock_id").range(offset, offset + 999).execute()
        existing_ids.extend(r["stock_id"] for r in page.data)
        if len(page.data) < 1000:
            break
        offset += 1000

    matched = [(sid, industry_map[sid]) for sid in existing_ids if sid in industry_map]
    print(f"資料庫現有 {len(existing_ids)} 支，匹配到 {len(matched)} 筆，開始寫入...")

    # 按產業分組，每組用 .in_() 批次 UPDATE（避免逐筆呼叫）
    from collections import defaultdict
    groups: dict[str, list[str]] = defaultdict(list)
    for sid, ind in matched:
        groups[ind].append(sid)

    count = 0
    for industry, sids in groups.items():
        for i in range(0, len(sids), 100):
            supabase.table("stocks").update({"industry": industry}).in_("stock_id", sids[i:i + 100]).execute()
        count += len(sids)
    print(f"  已更新 {count}/{len(matched)}")

    print(f"\n完成！共更新 {count} 支股票產業資訊。")

    # 印出樣本確認
    sample = supabase.table("stocks").select("stock_id,name,industry").limit(5).execute()
    print("\n樣本：")
    for r in sample.data:
        print(f"  {r['stock_id']} {r['name']} → {r['industry']}")


if __name__ == "__main__":
    run()
