"""
業外收支偵測（賣祖產警告）
讀取 income_statement_quarterly，計算各股 TTM 業外收益比率，
若（稅後淨利 − 營業利益）/ 稅後淨利 > 30% 則於 valuations.nonop_warning 寫入警告。

觸發條件（三個同時成立）：
  1. TTM 稅後淨利 > 0（公司整體獲利）
  2. TTM 稅後淨利 > TTM 營業利益（業外收入為淨正貢獻）
  3. 業外佔比 > 30%

用法：
  python scripts/patch_nonop_warning.py
  python scripts/patch_nonop_warning.py --dry-run  # 僅列出受影響股票，不寫入
"""

import os
import sys
from dotenv import load_dotenv
from supabase import create_client

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
NONOP_THRESHOLD = 0.30  # 業外佔比門檻

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


def fetch_income_data() -> dict[str, list[dict]]:
    """取得所有股票近 4 季有效損益資料，按股票分組"""
    all_rows: list[dict] = []
    offset = 0
    while True:
        resp = supabase.table("income_statement_quarterly") \
            .select("stock_id,quarter_end_date,operating_income,net_income") \
            .not_("operating_income", "is", None) \
            .not_("net_income", "is", None) \
            .order("quarter_end_date", desc=True) \
            .range(offset, offset + 999) \
            .execute()
        batch = resp.data or []
        all_rows.extend(batch)
        if len(batch) < 1000:
            break
        offset += 1000

    # 按股票分組，只保留最新 4 季
    by_stock: dict[str, list[dict]] = {}
    for r in all_rows:
        sid = r["stock_id"]
        if sid not in by_stock:
            by_stock[sid] = []
        if len(by_stock[sid]) < 4:
            by_stock[sid].append(r)
    return by_stock


def compute_ttm_ratio(quarters: list[dict]) -> float | None:
    """計算 TTM 業外佔比。回傳 None 表示資料不足或條件不符"""
    if len(quarters) < 4:
        return None

    ttm_op  = sum(float(q["operating_income"]) for q in quarters[:4])
    ttm_net = sum(float(q["net_income"])        for q in quarters[:4])

    if ttm_net <= 0:
        return None                          # 整體虧損，P/E 已有其他警告處理
    if ttm_net <= ttm_op:
        return None                          # 業外為負貢獻或持平，不觸發
    ratio = (ttm_net - ttm_op) / ttm_net
    return ratio if ratio > NONOP_THRESHOLD else None


def update_warnings(updates: list[dict], dry_run: bool):
    """批次更新 valuations.nonop_warning"""
    if dry_run:
        for u in updates:
            print(f"  [DRY] {u['stock_id']}: {u['nonop_warning']}")
        return

    # 需要設定警告的股票
    to_warn   = [u for u in updates if u["nonop_warning"] is not None]
    # 需要清除警告的股票
    to_clear  = [u for u in updates if u["nonop_warning"] is None]

    # 逐批更新（每次 100 筆）
    for i in range(0, len(to_warn), 100):
        batch = to_warn[i:i + 100]
        for u in batch:
            supabase.table("valuations") \
                .update({"nonop_warning": u["nonop_warning"]}) \
                .eq("stock_id", u["stock_id"]) \
                .execute()

    # 清除不再符合條件的警告
    clear_ids = [u["stock_id"] for u in to_clear]
    for i in range(0, len(clear_ids), 100):
        batch_ids = clear_ids[i:i + 100]
        supabase.table("valuations") \
            .update({"nonop_warning": None}) \
            .in_("stock_id", batch_ids) \
            .execute()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="業外收支偵測，回填 valuations.nonop_warning")
    parser.add_argument("--dry-run", action="store_true", help="僅列出結果，不寫入資料庫")
    args = parser.parse_args()

    print("讀取損益表資料...")
    by_stock = fetch_income_data()
    print(f"共 {len(by_stock)} 支股票有損益資料")

    updates: list[dict] = []
    warned = 0
    for sid, quarters in by_stock.items():
        ratio = compute_ttm_ratio(quarters)
        if ratio is not None:
            pct = round(ratio * 100, 1)
            warning = f"業外收益佔稅後淨利 {pct}%，TTM EPS 含一次性成分"
            updates.append({"stock_id": sid, "nonop_warning": warning})
            warned += 1
        else:
            updates.append({"stock_id": sid, "nonop_warning": None})

    print(f"觸發業外收益警告：{warned} 支股票")

    if warned > 0:
        print("\n受影響股票（業外佔比 > 30%）：")
        for u in updates:
            if u["nonop_warning"]:
                print(f"  {u['stock_id']}: {u['nonop_warning']}")

    print(f"\n{'[DRY RUN] ' if args.dry_run else ''}寫入警告...")
    update_warnings(updates, args.dry_run)
    print("✅ 完成")


if __name__ == "__main__":
    main()
