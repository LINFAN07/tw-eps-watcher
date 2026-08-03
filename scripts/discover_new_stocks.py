"""
discover_new_stocks.py — 新掛牌股發現（每月執行）

## 為什麼需要它

唯一會「新增」股票到 stocks 名冊的 init_download.py 是一次性手動腳本，
不在任何排程裡。其餘所有腳本對 stocks 表只有 select（讀既有名冊）或 update
（改既有欄位），從不 insert 新代號。

結果：資料庫從初始下載那天起就是一個「只減不增」的宇宙——cleanup 會移除下市股，
卻沒有任何機制納入新掛牌股。每一檔新 IPO、新掛牌興櫃永遠進不來，而且因為
「沒有東西會出錯」，這件事會無聲無息地讓資料庫與真實市場逐月背離。

本腳本每月比對 FinMind 名冊與資料庫，只補「資料庫還沒有」的新代號。
補進 stocks 後，既有下載/計算排程（都以 stocks 為迭代來源）會自然把歷史回填。

## 資料誠信

FinMind 名冊呼叫經 finmind_client.fetch()，失敗會拋 FinMindError 讓工作以 exit 1
結束——絕不吞掉錯誤後把「抓不到名冊」誤當成「沒有新股」。
"""

import os
import sys
import argparse
from dotenv import load_dotenv
from supabase import create_client

sys.path.insert(0, os.path.dirname(__file__))
from finmind_client import fetch, roster_market  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

supabase      = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
FINMIND_TOKEN = os.getenv("FINMIND_TOKEN")


def fetch_roster() -> dict[str, dict]:
    """
    FinMind 全市場名冊 {股票代碼: {name, market}}。

    只收 4 位純數字代碼，與 init_download.step1 一致（濾掉 ETF、權證、
    指數等非個股代號），確保新股的欄位形狀與既有資料一致。
    """
    raw = fetch("TaiwanStockInfo", None, None, FINMIND_TOKEN)
    roster = {}
    for item in raw:
        sid = str(item.get("stock_id", "")).strip()
        if sid.isdigit() and len(sid) == 4 and sid not in roster:
            roster[sid] = {"stock_id": sid,
                           "name": item.get("stock_name", ""),
                           "market": roster_market(item)}
    return roster


def fetch_existing_ids() -> set[str]:
    """分頁讀取資料庫既有 stock_id（繞過 Supabase 1000 筆上限）"""
    ids, offset = set(), 0
    while True:
        resp = supabase.table("stocks").select("stock_id").range(offset, offset + 999).execute()
        ids.update(r["stock_id"] for r in resp.data)
        if len(resp.data) < 1000:
            break
        offset += 1000
    return ids


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="只列出將新增的股票，不寫入資料庫")
    args = parser.parse_args()

    roster   = fetch_roster()
    existing = fetch_existing_ids()
    new_ids  = sorted(set(roster) - existing)

    print(f"FinMind 名冊：{len(roster)} 支；資料庫既有：{len(existing)} 支")
    print(f"新掛牌（資料庫尚無）：{len(new_ids)} 支\n")

    if not new_ids:
        print("✅ 沒有新股，名冊已是最新。")
        return

    for sid in new_ids:
        print(f"  + {sid} {roster[sid]['name']}（{roster[sid]['market']}）")

    if args.dry_run:
        print("\n[dry-run] 未寫入。移除 --dry-run 即會補進 stocks 名冊。")
        return

    rows = [roster[sid] for sid in new_ids]
    supabase.table("stocks").upsert(rows).execute()
    print(f"\n✅ 已補進 {len(rows)} 支新股。"
          "\n   歷史 EPS/股價/淨值等將由既有下載排程於下次執行時自然回填。")


if __name__ == "__main__":
    main()
