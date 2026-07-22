"""
交叉驗證健檢：同一個數字用兩條不同路徑算，比對是否一致。

為什麼需要這支：`validate_valuations.py` 只檢查內部一致性
（cheap < fair < expensive、status 與現價相符），
但單位錯、累計誤用、股數基準不符這類錯誤，算出來的數字彼此自洽，
那些規則全部會通過。專案已為此付出過代價：

  - 現金流量表是年度累計卻被當單季加總，P/FCF 全數高估約 2.5 倍（2026-07-17）
  - 配股造成的除權從未還原，1,790 支（74%）的歷史估值被污染（2026-07-22）

兩者都不是靠內部規則發現的，是靠跨來源／跨路徑比對。

本腳本針對 valuations 的每個衍生值，用其原始資料獨立重算一次並比對。
差異超過容許值即報告。發現問題以 exit 1 結束，供排程寄信。

用法：
  python scripts/audit_cross_check.py            # 抽樣檢查
  python scripts/audit_cross_check.py --all      # 全市場（慢）
"""

import argparse
import os
import random
import sys

import pandas as pd
from dotenv import load_dotenv
from supabase import create_client

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

# 相對誤差容許值。四捨五入與取值時點的微小差異不算問題，
# 但單位錯（1000 倍）、累計誤用（約 2.5 倍）遠超此值，必被抓出。
TOLERANCE = 0.02

SAMPLE_SIZE = 60

# 樣本必須涵蓋「會出事的極端案例」，不能只挑熟悉的權值股。
# 2026-07-22 教訓：除權還原漏做卻驗證通過，正因當初四支樣本有三支從沒配過股。
MUST_CHECK = [
    "2330", "2317", "2454", "2882",   # 權值股：量級最容易用常識判斷
    "1436", "1519",                   # 連年配股：除權還原的極端案例
    "2603", "1301",                   # 高配息
    "5871", "2915",                   # 租賃／零售：財報結構與製造業不同
]


def _paged(table: str, cols: str, stock_id: str) -> list[dict]:
    rows, offset = [], 0
    while True:
        data = (supabase.table(table).select(cols).eq("stock_id", stock_id)
                .order(cols.split(",")[0]).range(offset, offset + 999).execute().data)
        rows.extend(data)
        if len(data) < 1000:
            return rows
        offset += 1000


# 絕對誤差下限：欄位多為 DECIMAL(x,2)，值很小時（如 -0.13%）四捨五入本身
# 就可能造成數個百分比的相對差異，純用相對誤差會全是誤報。
ABS_TOLERANCE = 0.02


def close(a: float | None, b: float | None) -> bool:
    """兩值是否在容許誤差內；任一為空視為不可比（由呼叫端另行處理）"""
    if a is None or b is None:
        return True
    diff = abs(a - b)
    if diff <= ABS_TOLERANCE:
        return True
    denom = max(abs(a), abs(b))
    return denom == 0 or diff / denom <= TOLERANCE


def check_ttm_eps(sid: str, v: dict) -> str | None:
    """ttm_eps 應等於近四季 EPS 相加（興櫃半年報用兩期）"""
    rows = _paged("eps_quarterly", "quarter_end_date,eps", sid)
    if len(rows) < 2 or v.get("ttm_eps") is None:
        return None
    months = {int(r["quarter_end_date"][5:7]) for r in rows}
    w = 2 if months <= {6, 12} else 4
    if len(rows) < w:
        return None
    recalc = sum(float(r["eps"]) for r in rows[-w:])
    stored = float(v["ttm_eps"])
    # 一次性收益偵測會把離群季 cap 掉，故存的值可能【低於】相加值，那是正常的；
    # 只有「明顯高於」才是問題。用差值判斷，不可寫成 recalc * (1 + TOLERANCE)——
    # 負數乘以大於 1 的係數會變得更小，判斷方向會反過來（首版即因此全是誤報）。
    margin = max(ABS_TOLERANCE, abs(recalc) * TOLERANCE)
    if stored - recalc > margin:
        return f"ttm_eps {stored} 高於近 {w} 季相加 {recalc:.2f}"
    return None


def check_revenue_per_share(sid: str, v: dict, shares: int | None) -> str | None:
    """ps_revenue_per_share 應等於 TTM 月營收 ÷（股數×1000）"""
    if not shares or v.get("ps_revenue_per_share") is None:
        return None
    rows = _paged("monthly_revenue", "year_month,revenue", sid)
    if len(rows) < 12:
        return None
    ttm = sum(float(r["revenue"]) for r in rows[-12:])
    recalc = ttm / (shares * 1000)
    if not close(float(v["ps_revenue_per_share"]), recalc):
        return (f"ps_revenue_per_share {v['ps_revenue_per_share']} vs 重算 {recalc:.4f}"
                f"（TTM 營收 {ttm:,.0f}、股數 {shares:,} 千股）")
    return None


def check_book_value(sid: str, v: dict) -> str | None:
    """pb_book_value 應等於資產負債表最新一季的每股淨值"""
    rows = _paged("balance_sheet_quarterly", "quarter_end_date,book_value_per_share", sid)
    rows = [r for r in rows if r["book_value_per_share"] is not None]
    if not rows or v.get("pb_book_value") is None:
        return None
    latest = float(rows[-1]["book_value_per_share"])
    if not close(float(v["pb_book_value"]), latest):
        return (f"pb_book_value {v['pb_book_value']} vs 最新季 {latest}"
                f"（{rows[-1]['quarter_end_date']}）")
    return None


def check_operating_margin(sid: str, v: dict) -> str | None:
    """
    operating_margin 應等於 TTM 營業利益 ÷ TTM 營收 × 100。

    兩者來自不同資料表（income_statement_quarterly 與 monthly_revenue），
    單位若不一致，比率會差 1000 倍——這正是本檢查的目的。
    """
    if v.get("operating_margin") is None:
        return None
    inc = _paged("income_statement_quarterly", "quarter_end_date,operating_income", sid)
    inc = [r for r in inc if r["operating_income"] is not None]
    rev = _paged("monthly_revenue", "year_month,revenue", sid)
    if len(inc) < 4 or len(rev) < 12:
        return None
    ttm_op = sum(float(r["operating_income"]) for r in inc[-4:])
    ttm_rev = sum(float(r["revenue"]) for r in rev[-12:])
    if ttm_rev <= 0:
        return None
    recalc = ttm_op / ttm_rev * 100
    if not close(float(v["operating_margin"]), recalc):
        return f"operating_margin {v['operating_margin']}% vs 重算 {recalc:.2f}%"
    return None


def check_status(sid: str, v: dict) -> str | None:
    """status 應與現價、目標價的關係一致（內部一致性，成本極低故一併檢查）"""
    price, cheap, fair = v.get("current_price"), v.get("cheap_price"), v.get("fair_price")
    if None in (price, cheap, fair) or v.get("status") in (None, "無法計算"):
        return None
    price, cheap, fair = float(price), float(cheap), float(fair)
    expect = "便宜" if price <= cheap else "合理" if price <= fair else "昂貴"
    if expect != v["status"]:
        return f"status {v['status']} 但現價 {price} vs 便宜 {cheap}/合理 {fair} → 應為 {expect}"
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="檢查全市場（慢）")
    args = ap.parse_args()

    stocks = {r["stock_id"]: r for r in
              supabase.table("stocks").select("stock_id,listed_shares").execute().data}
    vals = {r["stock_id"]: r for r in
            supabase.table("valuations").select(
                "stock_id,ttm_eps,ps_revenue_per_share,pb_book_value,"
                "operating_margin,current_price,cheap_price,fair_price,status"
            ).execute().data}

    targets = list(vals) if args.all else sorted(
        set(MUST_CHECK) | set(random.sample(list(vals), min(SAMPLE_SIZE, len(vals)))))
    targets = [t for t in targets if t in vals]

    print(f"交叉驗證 {len(targets)} 支（容許誤差 {TOLERANCE:.0%}）\n")

    problems: list[str] = []
    for i, sid in enumerate(targets, 1):
        v = vals[sid]
        shares = (stocks.get(sid) or {}).get("listed_shares")
        for check in (
            check_ttm_eps(sid, v),
            check_revenue_per_share(sid, v, shares),
            check_book_value(sid, v),
            check_operating_margin(sid, v),
            check_status(sid, v),
        ):
            if check:
                problems.append(f"{sid}: {check}")
                print(f"  ❌ {sid}: {check}")
        if i % 20 == 0:
            print(f"  …{i}/{len(targets)}")

    print(f"\n檢查完成：{len(targets)} 支、發現 {len(problems)} 個不一致")
    if problems:
        print("\n這些是【兩條路徑算出不同答案】，代表單位、累計或基準有問題，"
              "不是四捨五入誤差。")
        sys.exit(1)
    print("✅ 全部一致")


if __name__ == "__main__":
    main()
