"""
測試腳本：只抓 2330（台積電）和 2454（聯發科）
確認 API 連線與資料格式正確後再跑完整版
"""

import os
import sys
import time
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv
from supabase import create_client

# 強制使用 UTF-8 輸出，避免 Windows cp950 編碼錯誤
sys.stdout.reconfigure(encoding="utf-8")

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

FINMIND_TOKEN = os.getenv("FINMIND_TOKEN")
SUPABASE_URL  = os.getenv("SUPABASE_URL")
SUPABASE_KEY  = os.getenv("SUPABASE_KEY")
FINMIND_API   = "https://api.finmindtrade.com/api/v4/data"
START_DATE    = (datetime.today() - timedelta(days=365 * 10)).strftime("%Y-%m-%d")
TEST_STOCKS   = ["2330", "2454"]

# ── 環境變數檢查 ──────────────────────────────────────────
print("=== 環境變數檢查 ===")
missing = [k for k, v in {"FINMIND_TOKEN": FINMIND_TOKEN, "SUPABASE_URL": SUPABASE_URL, "SUPABASE_KEY": SUPABASE_KEY}.items() if not v]
if missing:
    print(f"❌ 缺少環境變數：{', '.join(missing)}")
    print("   請確認 .env 檔案存在且已填入正確數值")
    sys.exit(1)
print("✅ 環境變數齊全\n")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


def finmind_get(dataset, stock_id=None, start_date=None):
    params = {"dataset": dataset, "token": FINMIND_TOKEN}
    if stock_id:
        params["data_id"] = stock_id
    if start_date:
        params["start_date"] = start_date
    resp = requests.get(FINMIND_API, params=params, timeout=30)
    return resp.json()


# ── 測試 1：FinMind 連線 ──────────────────────────────────
print("=== 測試 1：FinMind API 連線 ===")
result = finmind_get("TaiwanStockInfo")
if result.get("status") == 200:
    print(f"✅ 連線成功，共 {len(result['data'])} 筆股票資料")
else:
    print(f"❌ 連線失敗：{result.get('msg')}")
    sys.exit(1)

# 寫入測試股票至 stocks 資料表
test_stock_rows = [
    {"stock_id": "2330", "name": "台積電", "market": "TWSE"},
    {"stock_id": "2454", "name": "聯發科", "market": "TWSE"},
]
supabase.table("stocks").upsert(test_stock_rows).execute()
print("✅ 測試股票寫入 stocks 資料表\n")


# ── 測試 2：EPS 資料 ─────────────────────────────────────
print("=== 測試 2：季度 EPS ===")
for stock_id in TEST_STOCKS:
    result = finmind_get("TaiwanStockFinancialStatements", stock_id, START_DATE)
    data   = result.get("data", [])

    if not data:
        print(f"  ⚠️  {stock_id}：無資料（token 可能額度不足或格式不符）")
        continue

    # 印出所有出現的 type，幫助確認正確欄位名稱
    types_found = sorted(set(item.get("type") for item in data))
    print(f"  {stock_id} 可用 type 值：{types_found}")

    # 嘗試常見 EPS type 名稱
    eps_candidates = [r for r in data if r.get("type") in {"EPS", "BasicEPS", "EPSTaxExcluded"}]
    print(f"  {stock_id} EPS 筆數：{len(eps_candidates)} 筆（近 10 年）")

    if eps_candidates:
        # 寫入資料庫
        rows = [{"stock_id": stock_id, "quarter_end_date": r["date"], "eps": float(r["value"])}
                for r in eps_candidates if r.get("value") is not None]
        supabase.table("eps_quarterly").upsert(rows).execute()
        print(f"  ✅ {stock_id} EPS 寫入成功，最新一筆：{eps_candidates[-1]}")
    else:
        print(f"  ⚠️  找不到 EPS type，請看上方 type 清單，告知正確名稱")

    time.sleep(6.5)

print()


# ── 測試 3：日收盤價 ──────────────────────────────────────
print("=== 測試 3：日收盤價 ===")
for stock_id in TEST_STOCKS:
    result = finmind_get("TaiwanStockPrice", stock_id, START_DATE)
    data   = result.get("data", [])

    print(f"  {stock_id} 收盤價筆數：{len(data)} 筆（近 10 年）")

    if data:
        rows = [{"stock_id": stock_id, "date": r["date"], "close_price": float(r["close"])}
                for r in data if r.get("close") is not None]
        for i in range(0, len(rows), 500):
            supabase.table("daily_prices").upsert(rows[i:i+500]).execute()
        print(f"  ✅ {stock_id} 股價寫入成功，最新一筆：date={data[-1]['date']} close={data[-1]['close']}")
    else:
        print(f"  ⚠️  {stock_id}：無股價資料")

    time.sleep(6.5)

print()
print("=== 測試完成 ===")
print("請至 Supabase → Table Editor 確認 eps_quarterly 和 daily_prices 有資料")
