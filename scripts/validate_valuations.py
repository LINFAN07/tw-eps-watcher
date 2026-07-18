"""
validate_valuations.py — 估值結果驗證（內部一致性 + 跨來源比對）

## A. 內部一致性（隨機抽樣 100 支）
  1. 價格順序：cheap < fair < expensive（P/E、P/B、P/S、P/FCF）
  2. status 與 current_price 的對應關係
  3. P/E 倍數在合理範圍（3–200）
  4. 替代模型倍數在合理範圍（P/B: 0.1–50，P/S / P/FCF: 0.1–200）
  5. ttm_eps > 0.5 但 cheap_price 為 null（矛盾空值）
  6. current_price > 0

## B. 跨來源比對（隨機抽樣 10 支，與 FinMind 對照）
  7. 零價格（0 不是價格，是「無成交」偽裝成數字）
  8. 幽靈交易日（我們有、FinMind 沒有 → 可能寫入了休市日）
  9. 同日價格不符（→ 日期位移或抓錯來源）

**為何需要 B**：A 只能驗「內部自洽」。資料是舊的、日期整批位移、單位錯了——
這些錯誤的數字彼此完全自洽，A 的規則會全部通過。
2026-07-17 發現的兩個重大缺陷（上市股價位移一個交易日、10 萬筆零價格）
就是 A 完全抓不到、靠人工跨來源比對才揪出來的。B 即是將該手法自動化。

參見 CLAUDE.md「資料誠信原則」。

發現 critical 問題時以 exit code 1 退出，觸發 GitHub Actions 失敗 Email 通知。
"""

import os
import sys
import time
import random
import requests
from datetime import date, timedelta
from dotenv import load_dotenv
from supabase import create_client

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

SAMPLE_SIZE = 100
# status 判斷容許 2% 誤差，避免浮點數舍入造成誤報
TOLERANCE = 0.02

# 跨來源比對：FinMind 免費版每次呼叫需間隔 6.5 秒，抽樣數需控制在合理耗時內
FINMIND_TOKEN     = os.getenv("FINMIND_TOKEN")
FINMIND_API       = "https://api.finmindtrade.com/api/v4/data"
CALL_INTERVAL     = 6.5
PRICE_SAMPLE_SIZE = 10
PRICE_WINDOW_DAYS = 15
# 錨點股：熟到能一眼看穿的權值股，每次「必比」而非碰運氣被隨機抽到。
# 系統性錯誤（整批日期位移、單位錯、來源抓錯）會先在這些名字上露餡——
# 把「我腦中台積電該多少」的直覺，變成一定會跑到的防線。
ANCHOR_STOCKS = ["2330", "2317", "2454", "2882", "1301", "2412", "2603", "2891"]
# 收盤價比對容許 1 分錢誤差（雙方四捨五入位數可能不同）
PRICE_EPSILON     = 0.011


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


# ─────────────── B. 跨來源比對 ───────────────

def finmind_prices(stock_id: str, start: str) -> dict[str, float]:
    """
    FinMind 收盤價 {日期: 收盤價}。

    FinMind 對「當日無成交」回傳 close = 0，那是缺值不是價格，一律排除，
    否則會把我們正確的「不寫入」誤判為缺漏。
    """
    params = {"dataset": "TaiwanStockPrice", "data_id": stock_id,
              "start_date": start, "token": FINMIND_TOKEN}
    try:
        resp = requests.get(FINMIND_API, params=params, timeout=30).json()
    except Exception as e:
        print(f"  ⚠️  FinMind 請求失敗（{stock_id}）: {e}")
        return {}
    if resp.get("status") != 200:
        print(f"  ⚠️  FinMind 回應異常（{stock_id}）: {resp.get('msg')}")
        return {}
    return {r["date"]: float(r["close"]) for r in resp.get("data", [])
            if r.get("close") is not None and float(r["close"]) > 0}


def our_prices(stock_id: str, start: str) -> dict[str, float]:
    """資料庫收盤價 {日期: 收盤價}（帶 stock_id 走主鍵前綴，不會逾時）"""
    resp = (supabase.table("daily_prices")
            .select("date,close_price")
            .eq("stock_id", stock_id)
            .gte("date", start)
            .order("date")
            .execute())
    return {r["date"]: float(r["close_price"]) for r in resp.data}


def check_price_source(stock_id: str, start: str, latest_ok: str) -> list[tuple]:
    """
    以 FinMind 為對照，驗證資料庫股價的正確性。

    latest_ok：比對截止日。最新一兩天可能只是排程尚未執行或來源尚未發布，
    不應視為缺漏，故排除。
    """
    ours = our_prices(stock_id, start)
    theirs = finmind_prices(stock_id, start)
    if not theirs:
        return []   # 對照組取不到就無從比對，不誤報

    issues = []

    # 零價格：0 是「無成交」不是價格（2026-07-17 曾有 10.3 萬筆）
    for d, p in ours.items():
        if p <= 0:
            issues.append((stock_id, "critical", f"{d} 收盤價為 {p}（0 不是價格，應不寫入）"))

    # 幽靈交易日：我們有、FinMind 沒有 → 可能把休市日寫成交易日
    for d in sorted(set(ours) - set(theirs)):
        if d <= latest_ok:
            issues.append((stock_id, "critical",
                           f"{d} 我們有股價 {ours[d]}，但 FinMind 無該日資料（疑為休市日）"))

    # 同日價格不符 → 日期位移或抓錯來源
    for d in sorted(set(ours) & set(theirs)):
        if abs(ours[d] - theirs[d]) > PRICE_EPSILON:
            issues.append((stock_id, "critical",
                           f"{d} 收盤價不符：我們 {ours[d]} vs FinMind {theirs[d]}"))

    # 缺漏：FinMind 有、我們沒有（可能是下載遺漏，非致命）
    missing = [d for d in sorted(set(theirs) - set(ours)) if d <= latest_ok]
    if missing:
        issues.append((stock_id, "warning",
                       f"缺少 {len(missing)} 個交易日的股價：{', '.join(missing[:3])}"
                       + ("…" if len(missing) > 3 else "")))
    return issues


def run_cross_source_check(all_ids: list[str]) -> list[tuple]:
    # 錨點股一定納入（存在於資料庫者），再以隨機抽樣補足其餘名額
    anchors = [s for s in ANCHOR_STOCKS if s in set(all_ids)]
    pool    = [s for s in all_ids if s not in anchors]
    extra   = random.sample(pool, min(PRICE_SAMPLE_SIZE, len(pool)))
    sample  = anchors + extra
    start   = (date.today() - timedelta(days=PRICE_WINDOW_DAYS)).strftime("%Y-%m-%d")
    # 最近 2 天不比對：排程可能尚未執行，或交易所尚未發布
    latest_ok = (date.today() - timedelta(days=2)).strftime("%Y-%m-%d")

    print(f"\n=== 跨來源比對（與 FinMind 對照 {len(sample)} 支，{start} 起）===")
    print(f"預估耗時約 {len(sample) * CALL_INTERVAL / 60:.1f} 分鐘\n")

    issues = []
    for i, sid in enumerate(sample, 1):
        found = check_price_source(sid, start, latest_ok)
        mark  = "OK" if not found else f"{len(found)} 個問題"
        print(f"  [{i}/{len(sample)}] {sid}: {mark}")
        issues.extend(found)
        if i < len(sample):
            time.sleep(CALL_INTERVAL)
    return issues


def main():
    print("=== A. 估值結果一致性驗證 ===\n")

    all_ids = fetch_all_stock_ids()
    sample  = random.sample(all_ids, min(SAMPLE_SIZE, len(all_ids)))
    print(f"資料庫總股票數：{len(all_ids)}，本次抽樣：{len(sample)} 支\n")

    rows   = fetch_sample_rows(sample)
    issues = []
    for row in rows:
        issues.extend(validate(row))
    print(f"內部一致性檢查完成，抽樣 {len(rows)} 支")

    # B. 跨來源比對（沒有 FinMind token 就跳過，但要明講——
    #    少了這段等於只驗內部一致性，抓不到日期位移與陳舊資料）
    if FINMIND_TOKEN:
        issues.extend(run_cross_source_check(all_ids))
    else:
        print("\n⚠️  未設定 FINMIND_TOKEN，跳過跨來源比對")
        print("    僅檢查內部一致性，無法偵測日期位移、資料陳舊、單位錯誤")

    critical = [(s, m) for s, sev, m in issues if sev == "critical"]
    warnings = [(s, m) for s, sev, m in issues if sev == "warning"]

    print(f"\n=== 驗證結果 ===")
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
