"""
股本變動偵測（減資 / 增資 / 分割）

讀取 balance_sheet_quarterly 的逐季流通股數（shares_thousand），偵測相鄰季
股本變動 ≥ 15% 的事件，於 valuations.capital_change_warning 寫入提示。

## 為什麼需要它

listed_shares 只存最新值，所有「每股」序列（EPS、每股淨值、每股營收）都以
最新股本回頭套舊期分子，減資 / 增資 / 分割那一點會在河流圖出現「假斷崖」，
而畫面上毫無提示。這是「同一欄位必須始終是同一個東西」原則在時間軸上的漏洞。

方向為「偵測並標記」而非重算歷史：用最少代價讓使用者看到變動點前的估值帶
基準不同、僅供參考，不去竄改歷史數字。

## 觸發條件

- 相鄰兩季流通股數變動 |Δ / 前值| ≥ 15%（濾掉現增/員工認股的小幅漸進稀釋）
- 只採計近 5 年內的事件（更久遠且已穩定的變動對當前估值影響有限）
- 報告最近一次事件：方向（股本減少=減資、增加=增資/分割）+ 幅度 + 季別

用法：
  python scripts/patch_capital_change_warning.py
  python scripts/patch_capital_change_warning.py --dry-run  # 僅列出，不寫入
"""

import os
import sys
from datetime import date
from dotenv import load_dotenv
from supabase import create_client

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

# 增資與減資分開設門檻：兩者性質不同，不該共用一個數字。
#
# 2026-07-21 首次全市場啟用的實測分布（2418 支有逐季股本資料）：
#   增資/分割 652 支（中位 24%），其中 341 支落在 15~24%——多為配股票股利，
#     台股極普遍（配 2 元股票股利即 +20%），警告價值低。
#   減資 131 支（中位 30%），15~24% 僅 41 支，且減資常伴隨彌補虧損，
#     事件本身就是值得注意的訊號。
#
# 統一 15% 會讓 779 支（32%）掛上警告，三分之一的股票都有徽章，
# 使用者會習慣性忽略，反而稀釋掉真正該注意的大幅變動。
INCREASE_THRESHOLD = 0.25   # 增資／分割：略過配股等常態小幅變動
DECREASE_THRESHOLD = 0.15   # 減資：較罕見且訊號較強，完整保留
RECENT_YEARS       = 5      # 只採計近幾年的事件


def fetch_shares_by_stock() -> dict[str, list[tuple[str, int]]]:
    """
    讀取各股逐季流通股數，按股票分組並依日期升冪排列。

    加 order() 確保分頁跨頁順序一致（無排序時 Postgres 不保證，會重複/遺漏）。
    只保留 shares_thousand 非空者——尚未回填股本的舊資料略過，避免誤判。
    """
    by_stock: dict[str, list[tuple[str, int]]] = {}
    offset = 0
    while True:
        resp = (supabase.table("balance_sheet_quarterly")
                .select("stock_id,quarter_end_date,shares_thousand")
                .order("stock_id").order("quarter_end_date")
                .range(offset, offset + 999).execute())
        batch = resp.data or []
        for r in batch:
            if r["shares_thousand"] is None:
                continue
            by_stock.setdefault(r["stock_id"], []).append(
                (r["quarter_end_date"], int(r["shares_thousand"])))
        if len(batch) < 1000:
            break
        offset += 1000
    return by_stock


def quarter_label(date_str: str) -> str:
    """2024-09-30 → 2024Q3"""
    y, m, _ = date_str.split("-")
    return f"{y}Q{(int(m) - 1) // 3 + 1}"


def detect_latest_event(series: list[tuple[str, int]], cutoff: str) -> str | None:
    """
    偵測近 5 年內最近一次 ≥ 15% 的股本變動，回傳提示文字；無則 None。

    series 已依日期升冪；由新到舊掃描相鄰季，取第一個（最近）事件即回傳。
    """
    for i in range(len(series) - 1, 0, -1):
        cur_date, cur = series[i]
        _, prev = series[i - 1]
        if cur_date < cutoff or prev <= 0:
            continue
        change = (cur - prev) / prev
        # 依方向套用各自的門檻（見上方常數說明），不可用 abs() 一視同仁
        threshold = DECREASE_THRESHOLD if change < 0 else INCREASE_THRESHOLD
        if abs(change) < threshold:
            continue
        direction = "減資" if change < 0 else "增資/分割"
        pct = abs(round(change * 100))
        return (f"{quarter_label(cur_date)} {direction} {pct}%："
                "股本變動前的每股數值（EPS/淨值/營收）基準不同，"
                "該區間河流圖僅供參考")
    return None


def apply_updates(updates: list[dict], dry_run: bool):
    """設定 / 清除 valuations.capital_change_warning"""
    to_warn  = [u for u in updates if u["capital_change_warning"] is not None]
    to_clear = [u["stock_id"] for u in updates if u["capital_change_warning"] is None]

    if dry_run:
        for u in to_warn:
            print(f"  [DRY] {u['stock_id']}: {u['capital_change_warning']}")
        print(f"  [DRY] 另清除 {len(to_clear)} 支的舊警告")
        return

    for u in to_warn:
        supabase.table("valuations").update(
            {"capital_change_warning": u["capital_change_warning"]}
        ).eq("stock_id", u["stock_id"]).execute()

    for i in range(0, len(to_clear), 100):
        supabase.table("valuations").update(
            {"capital_change_warning": None}
        ).in_("stock_id", to_clear[i:i + 100]).execute()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="股本變動偵測，回填 valuations.capital_change_warning")
    parser.add_argument("--dry-run", action="store_true", help="僅列出結果，不寫入")
    args = parser.parse_args()

    by_stock = fetch_shares_by_stock()
    print(f"有逐季股本資料的股票：{len(by_stock)} 支")
    if not by_stock:
        print("⚠️  balance_sheet_quarterly 尚無 shares_thousand。"
              "請先執行 download_balance_sheet.py 回填歷史股本後再偵測。")
        return

    cutoff = date(date.today().year - RECENT_YEARS, 1, 1).isoformat()

    updates, warned = [], 0
    for sid, series in by_stock.items():
        warning = detect_latest_event(series, cutoff) if len(series) >= 2 else None
        updates.append({"stock_id": sid, "capital_change_warning": warning})
        if warning:
            warned += 1

    print(f"偵測到近 {RECENT_YEARS} 年股本變動"
          f"（增資 ≥{int(INCREASE_THRESHOLD*100)}%、減資 ≥{int(DECREASE_THRESHOLD*100)}%）：{warned} 支\n")
    if warned:
        for u in updates:
            if u["capital_change_warning"]:
                print(f"  {u['stock_id']}: {u['capital_change_warning']}")

    print(f"\n{'[DRY RUN] ' if args.dry_run else ''}寫入...")
    apply_updates(updates, args.dry_run)
    print("✅ 完成")


if __name__ == "__main__":
    main()
