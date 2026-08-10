"""
硬編視窗掃描器的偵測能力驗證（純函式，不連資料庫）。

## 為什麼要有這支

`audit_hardcoded_windows.py` 目前是全綠的——因為十份缺陷都已經修掉了。
但「全綠」有兩種可能：真的沒問題，或者規則寫壞了什麼都抓不到。
這個專案已經有稽核說謊的前例（`audit_workflows.py` 的白名單宣稱了不存在的
涵蓋，讓唯一能回補月營收的路徑沒有排程也沒被抓到）。

所以這裡拿**歷史上十份缺陷的真實程式碼**餵給掃描器，要求它全部抓到。
規則若被改窄（例如有人為了消掉誤報而收緊樣式），這裡就會紅。

反向案例同樣重要：日期切片、分頁常數、取最新單筆都不該被報，
否則誤報會淹沒訊號，最終沒有人看這個稽核。

跑法：python tests/test_hardcoded_windows.py
"""

import os
import sys

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from audit_hardcoded_windows import scan_text            # noqa: E402

# (說明, 原始碼, 是否為 Python, 期望被抓到)
# 「應該抓到」的每一則都取自真實事故，來源見 CLAUDE.md「期數判定一律 import periodicity」
CASES = [
    # ── 歷史缺陷：必須抓到 ────────────────────────────────
    ("第七份：稽核端營業利益取最近 4 列（2330 算出 49.27% vs 正確 53.31%）",
     'ttm_op = sum(float(r["operating_income"]) for r in inc[-4:])', True, True),
    ("第七份：稽核端月營收取最近 12 列",
     'ttm_rev = sum(float(r["revenue"]) for r in rev[-12:])', True, True),
    ("第九份：業外警告取最近 4 列（半年報公司變成兩年）",
     'ttm_op  = sum(float(q["operating_income"]) for q in quarters[:4])', True, True),
    ("第十份：normalized_eps 取最近 w×5 列再年化",
     'recent = eps_df.tail(w * 5)["eps"].astype(float)', True, True),
    ("2026-08-06：P/FCF 用 rolling 以列數滾動",
     'ttm_fcf = cash_flow_df["fcf"].rolling(4).sum()', True, True),
    ("2026-08-06：以 iloc 取最近 N 期 EPS",
     'window = eps_df.iloc[-4:]["eps"]', True, True),
    ("第八份：前端個股頁取最近 4 列當近四季 EPS",
     'const ttmQuarters = eps8.slice(0, 4)', False, True),
    ("第八份：前端取第 5~8 列當去年同期",
     'const prevYearQuarters = eps8.slice(4, 8)', False, True),
    ("前端以負索引取最近 12 筆月營收",
     'const ttmRevenue = revenueRows.slice(-12)', False, True),

    # ── 不該被抓到：誤報會淹沒訊號 ──────────────────────
    ("日期字串取年份（quarter_end_date 是 ISO 字串，不是序列）",
     'year, month_day = int(quarter_end[:4]), quarter_end[5:]', True, False),
    ("日期字串取年月",
     'rev_by_month = {r["year_month"][:7]: float(r["revenue"]) for r in rows}', True, False),
    ("Supabase 分頁常數（1000 是每頁上限，與期數無關）",
     'if len(rows) < 1000:  # eps_quarterly 分頁', True, False),
    ("取最新單筆股數，不是視窗",
     'latest_shares = shares.dropna().iloc[-1]  # 最新一期 eps 對應的股數', True, False),
    ("前端日期字串切片（取年份顯示季別）",
     'return `${iso.slice(0, 4)} Q${Math.ceil(+iso.slice(5, 7) / 3)}`  // quarter', False, False),
    ("前端以日期為鍵建索引（revenue 對照月份）",
     'for (const p of prices) byMonth[p.date.slice(0, 7)] = p  // revenue', False, False),
    ("docstring 內描述舊寫法的文字不該被當成程式碼",
     '"""\n這裡原本寫 inc[-4:]，是錯的：operating_income 半年報會取到兩年\n"""',
     True, False),
]


def main() -> int:
    failures = []
    print("=== 硬編視窗掃描器：偵測能力 ===")
    for name, source, is_py, expected in CASES:
        hits = [h for h in scan_text(source, is_py) if h[3]]   # 只算落在財報脈絡內的
        got = bool(hits)
        ok = got == expected
        mark = "✓" if ok else "✗"
        want = "應抓到" if expected else "不該報"
        print(f"  {mark} [{want}] {name}")
        if not ok:
            print(f"      得到 {len(hits)} 個命中：{[h[1] for h in hits]}")
            failures.append(name)

    total = len(CASES)
    print(f"\n{total - len(failures)}/{total} 通過")
    if failures:
        print("失敗：" + "、".join(failures))
        print("\n掃描器規則被改動時請確認：收緊樣式會讓歷史缺陷重新溜過，"
              "放寬則會製造誤報。兩者都會讓這個稽核失去作用。")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
