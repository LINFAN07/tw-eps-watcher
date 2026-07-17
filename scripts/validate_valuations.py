"""
validate_valuations.py — 估值結果一致性驗證

每週隨機抽樣 100 支股票，檢查以下規則：
  1. 價格順序：cheap < fair < expensive（P/E、P/B、P/S、P/FCF）
  2. status 與 current_price 的對應關係
  3. P/E 倍數在合理範圍（3–200）
  4. 替代模型倍數在合理範圍（P/B: 0.1–50，P/S / P/FCF: 0.1–200）
  5. ttm_eps > 0.5 但 cheap_price 為 null（矛盾空值）
  6. current_price > 0

發現 critical 問題時以 exit code 1 退出，觸發 GitHub Actions 失敗 Email 通知。
"""

import os
import sys
import random
from dotenv import load_dotenv
from supabase import create_client

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

SAMPLE_SIZE = 100
# status 判斷容許 2% 誤差，避免浮點數舍入造成誤報
TOLERANCE = 0.02


def fetch_all_stock_ids() -> list[str]:
    """分頁讀取所有 valuations 的 stock_id"""
    ids, page_size, offset = [], 1000, 0
    while True:
        resp = (supabase.table("valuations")
                .select("stock_id")
                .range(offset, offset + page_size - 1)
                .execute())
        ids.extend(r["stock_id"] for r in resp.data)
        if len(resp.data) < page_size:
            break
        offset += page_size
    return ids


def fetch_sample_rows(stock_ids: list[str]) -> list[dict]:
    """批次讀取抽樣股票的估值詳情"""
    rows = []
    cols = (
        "stock_id,current_price,status,"
        "ttm_eps,cheap_pe,fair_pe,expensive_pe,"
        "cheap_price,fair_price,expensive_price,"
        "pb_book_value,pb_cheap_pb,pb_fair_pb,pb_expensive_pb,"
        "pb_cheap_price,pb_fair_price,pb_expensive_price,pb_status,"
        "ps_revenue_per_share,ps_cheap_ps,ps_fair_ps,ps_expensive_ps,"
        "ps_cheap_price,ps_fair_price,ps_expensive_price,ps_status,"
        "pfcf_per_share,pfcf_cheap_pfcf,pfcf_fair_pfcf,pfcf_expensive_pfcf,"
        "pfcf_cheap_price,pfcf_fair_price,pfcf_expensive_price,pfcf_status"
    )
    for i in range(0, len(stock_ids), 100):
        batch = stock_ids[i:i + 100]
        resp = supabase.table("valuations").select(cols).in_("stock_id", batch).execute()
        rows.extend(resp.data)
    return rows


def check_price_order(sid: str, model: str, cheap, fair, expensive) -> list[tuple]:
    """驗證 cheap < fair < expensive，三值都不為 null 才檢查"""
    if None in (cheap, fair, expensive):
        return []
    if not (cheap < fair < expensive):
        return [(sid, "critical",
                 f"{model} 價格順序錯誤: cheap={cheap} fair={fair} expensive={expensive}")]
    return []


def check_status_consistency(sid: str, model: str, status: str | None,
                              cp: float | None, cheap, fair) -> list[tuple]:
    """驗證 status 與 current_price 的對應（允許 TOLERANCE 容差）"""
    if not status or cp is None or None in (cheap, fair):
        return []
    issues = []
    if status == "便宜" and cp > cheap * (1 + TOLERANCE):
        issues.append((sid, "critical",
                        f"{model} status=便宜 但 current_price={cp} > cheap_price={cheap}"))
    elif status == "合理":
        if cp < cheap * (1 - TOLERANCE) or cp > fair * (1 + TOLERANCE):
            issues.append((sid, "warning",
                           f"{model} status=合理 但 current_price={cp} 超出範圍 [{cheap}, {fair}]"))
    elif status == "昂貴" and cp < fair * (1 - TOLERANCE):
        issues.append((sid, "critical",
                        f"{model} status=昂貴 但 current_price={cp} < fair_price={fair}"))
    return issues


def check_multiplier_range(sid: str, label: str, val,
                            lo: float, hi: float) -> list[tuple]:
    if val is None:
        return []
    if not (lo <= val <= hi):
        return [(sid, "warning", f"{label}={val} 超出合理範圍 [{lo}, {hi}]")]
    return []


def validate(row: dict) -> list[tuple]:
    sid = row["stock_id"]
    cp  = row.get("current_price")
    issues = []

    # --- current_price > 0 ---
    if cp is not None and cp <= 0:
        issues.append((sid, "critical", f"current_price={cp} ≤ 0"))

    # --- P/E ---
    cheap_p = row.get("cheap_price")
    fair_p  = row.get("fair_price")
    exp_p   = row.get("expensive_price")
    issues += check_price_order(sid, "P/E", cheap_p, fair_p, exp_p)
    issues += check_status_consistency(sid, "P/E", row.get("status"), cp, cheap_p, fair_p)
    for col, lo, hi in [("cheap_pe", 3, 200), ("fair_pe", 3, 200), ("expensive_pe", 3, 200)]:
        issues += check_multiplier_range(sid, col, row.get(col), lo, hi)

    # ttm_eps 有值但估值結果為 null（矛盾空值）
    ttm = row.get("ttm_eps")
    if ttm and ttm > 0.5 and cheap_p is None:
        issues.append((sid, "warning", f"ttm_eps={ttm} > 0.5 但 cheap_price 為 null"))

    # --- P/B ---
    issues += check_price_order(sid, "P/B",
                                row.get("pb_cheap_price"),
                                row.get("pb_fair_price"),
                                row.get("pb_expensive_price"))
    issues += check_status_consistency(sid, "P/B", row.get("pb_status"), cp,
                                       row.get("pb_cheap_price"), row.get("pb_fair_price"))
    for col in ("pb_cheap_pb", "pb_fair_pb", "pb_expensive_pb"):
        issues += check_multiplier_range(sid, col, row.get(col), 0.1, 50)

    # --- P/S ---
    issues += check_price_order(sid, "P/S",
                                row.get("ps_cheap_price"),
                                row.get("ps_fair_price"),
                                row.get("ps_expensive_price"))
    issues += check_status_consistency(sid, "P/S", row.get("ps_status"), cp,
                                       row.get("ps_cheap_price"), row.get("ps_fair_price"))
    for col in ("ps_cheap_ps", "ps_fair_ps", "ps_expensive_ps"):
        issues += check_multiplier_range(sid, col, row.get(col), 0.1, 200)

    # --- P/FCF ---
    issues += check_price_order(sid, "P/FCF",
                                row.get("pfcf_cheap_price"),
                                row.get("pfcf_fair_price"),
                                row.get("pfcf_expensive_price"))
    issues += check_status_consistency(sid, "P/FCF", row.get("pfcf_status"), cp,
                                       row.get("pfcf_cheap_price"), row.get("pfcf_fair_price"))
    for col in ("pfcf_cheap_pfcf", "pfcf_fair_pfcf", "pfcf_expensive_pfcf"):
        issues += check_multiplier_range(sid, col, row.get(col), 0.1, 200)

    return issues


def main():
    print("=== 估值結果一致性驗證 ===\n")

    all_ids = fetch_all_stock_ids()
    sample  = random.sample(all_ids, min(SAMPLE_SIZE, len(all_ids)))
    print(f"資料庫總股票數：{len(all_ids)}，本次抽樣：{len(sample)} 支\n")

    rows   = fetch_sample_rows(sample)
    issues = []
    for row in rows:
        issues.extend(validate(row))

    critical = [(s, m) for s, sev, m in issues if sev == "critical"]
    warnings = [(s, m) for s, sev, m in issues if sev == "warning"]

    print(f"驗證完成，抽樣 {len(rows)} 支股票")
    print(f"  嚴重問題（critical）：{len(critical)} 筆")
    print(f"  警告（warning）    ：{len(warnings)} 筆\n")

    if critical:
        print("【嚴重問題】")
        for sid, msg in critical:
            print(f"  [{sid}] {msg}")
        print()

    if warnings:
        print("【警告】")
        for sid, msg in warnings:
            print(f"  [{sid}] {msg}")
        print()

    if not issues:
        print("✅ 所有驗證通過，估值結果一致性良好。")
    elif not critical:
        print("⚠️  有警告但無嚴重問題，請人工確認。")
    else:
        print("❌ 發現嚴重問題，請立即檢查估值計算邏輯。")
        sys.exit(1)


if __name__ == "__main__":
    main()
