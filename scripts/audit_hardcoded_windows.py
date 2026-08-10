"""
硬編 TTM 視窗掃描：抓出「取最近 N 期／N 列」而沒有經過 periodicity 的程式碼。

## 為什麼需要這支

期數判定（「哪幾期加起來剛好 12 個月」）在這個專案已經長出**十份**實作，
每一次都是事後才發現，代價從「利益率整批高估一倍」到「43 支河流圖用錯 TTM
三天無人察覺」。共同形狀是同一個：某處寫了 `[-4:]`／`tail(w*5)`／`slice(0,4)`
這類「最近 N 列」，而列數要換算成期間的前提是**每列涵蓋的期間相同**——
公司改變揭露頻率時這個前提就不成立，半年報公司的 4 列是【兩年】。

這類缺陷不會報錯：值仍在合理範圍、內部一致性檢查全過，只是大了一倍或錯開幾個月。
CLAUDE.md 已有「期數判定一律 import periodicity」這條規則，但前十次證明
**靠人記得是無效的防線**。本支把它變成機制。

發現未登記的硬編視窗即 exit 1。純靜態檢查，不連資料庫、不需密鑰——
2026-08-10 的教訓是需要密鑰的稽核會在無密鑰環境整批失效，這支刻意不依賴任何外部資源。

## 白名單以「整行文字」為鍵，不是檔名或行號

這是刻意的：任何人改動該行，豁免就自動失效、重新舉手。
`audit_workflows.py` 曾有一條說謊的豁免（宣稱「由 X 呼叫」但那個呼叫不存在），
讓唯一能回補月營收的路徑沒有排程也沒被稽核抓到。以檔名為鍵的白名單會腐爛，
以行文字為鍵的不會——改了就要重新說明理由。

## 這條規則的盲區（新增稽核規則時必須寫下來）

1. **抓不到常數定義**：`MIN_QUARTERS = 4` 這種寫法不在樣式內，而第五份正是這型。
   要抓它得掃所有 `= 4`，誤報會淹沒訊號。
2. **TypeScript 的字串切片與陣列切片同語法**：`iso.slice(0, 4)` 取年份、
   `eps8.slice(0, 4)` 取四列，靜態上無法區分，只能靠變數命名啟發式（見 TS_SEQ）。
   命名不像陣列的真實案例會漏掉。
3. **抓不到跨語言不對稱**：「Python 改了、TypeScript 沒跟上」兩邊都沒有硬編字面量，
   本支看不到。那一半歸 `tests/fixtures/shared_cases.json` 管，兩者互補不可互相取代。
4. **只掃財報脈絡**：命中行前後數行要出現 eps／income／revenue／quarter 等字樣，
   避免把分頁常數與日期切片全部報進來。脈絡不足的真實案例會漏。

用法：
  python scripts/audit_hardcoded_windows.py
  python scripts/audit_hardcoded_windows.py --all   # 連財報脈絡外的命中也列出（人工複查用）
"""

import argparse
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

ROOT = Path(__file__).resolve().parent.parent

# ── 樣式：只認「取序列最近 N 個元素」這個動作，不認資料量閘門（len(x) < N）
#    與正向日期切片（quarter_end[:4]），那兩者誤報率接近 100%
PY_PATTERNS = [
    (r"\[\s*-\s*([2-9]|\d{2,})\s*:\s*\]",            "[-N:] 取最後 N 列"),
    (r"\.tail\(",                                     ".tail() 取最後 N 列"),
    (r"\.iloc\[\s*-\s*([2-9]|\d{2,})\s*:",            ".iloc[-N:] 取最後 N 列"),
    (r"\.rolling\(",                                  ".rolling() 以列數滾動"),
    # 正向切片只在變數名像序列時才算：quarters[:4] 是第九份，quarter_end[:4] 是取年份
    (r"\b\w*(?:rows|ends|quarters|periods|recent|windows|wins)\w*\s*\[\s*:\s*\d+\s*\]",
     "seq[:N] 取前 N 列"),
]

# TypeScript：字串切片與陣列切片同語法，靠接收者命名區分（盲區 2）
TS_SEQ = r"(?:rows|ends|quarters|periods|eps\d*|data|items|list|arr|series)"
TS_PATTERNS = [
    (r"\.slice\(\s*-\s*\d+\s*\)",                                    ".slice(-N) 取最後 N 個"),
    # 起點不限 0：第八份的另一半是 eps8.slice(4, 8)（取第 5~8 列當去年同期），
    # 只認 slice(0, N) 會讓它整個溜過去（由 tests/test_hardcoded_windows.py 抓出）
    (rf"\b\w*{TS_SEQ}\w*\.slice\(\s*\d+\s*,\s*\d+\s*\)",             "seq.slice(M,N) 取固定列數"),
]

# 財報脈絡（盲區 4）：命中行前後 3 行要出現其一，否則多半是分頁常數或畫面截斷
CONTEXT = re.compile(r"eps|income|cash_flow|operating_cf|revenue|quarter|ttm|period|margin",
                     re.I)

# ── 白名單：鍵是【整行的正規化文字】，改動該行即自動失效並重新舉手。
#    每一項都要寫得出「為什麼這個 N 不是期數判定」，寫不出來就是該改成 periodicity。
EXEMPT = {
    "rps = per_share(wide.rolling(12, min_periods=12).sum(), shares_divisor)":
        "月營收已先 reindex 成連續月份、缺月為 NaN，min_periods=12 會自動略過，"
        "故 12 列必然等於 12 個月（不是期數判定）",
    "ttm = monthly.rolling(TTM_MONTHS, min_periods=TTM_MONTHS).sum().reindex(idx)":
        "同上：先 reindex 完整月序列並 fillna(0)（該月沒除息＝0，不是缺值），"
        "列數與月數一一對應",
}


def norm(line: str) -> str:
    """整行正規化：去頭尾空白、壓縮連續空白。行號與縮排改變不會讓豁免失效，內容改變會"""
    return re.sub(r"\s+", " ", line.strip())


def code_lines(text: str, is_python: bool):
    """
    產生 (行號, 行文字)，排除註解與 docstring。

    docstring 必須排除：本專案的註解密度極高，多處在說明「原本寫 rows[-12:]，
    那是錯的」——把說明錯誤的文字報成錯誤，稽核就會變成雜訊來源。
    """
    lines = text.splitlines()
    out, in_doc, delim = [], False, None
    for i, raw in enumerate(lines, 1):
        s = raw.strip()
        if is_python:
            if in_doc:
                if delim in s:
                    in_doc = False
                continue
            opener = next((d for d in ('"""', "'''") if s.startswith(d)), None)
            if opener:
                # 單行 docstring（開頭結尾同一行）不進入區塊狀態
                if not (s.endswith(opener) and len(s) > len(opener)):
                    in_doc, delim = True, opener
                continue
            if s.startswith("#"):
                continue
        else:
            if s.startswith("//") or s.startswith("*") or s.startswith("/*"):
                continue
        out.append((i, raw))
    return lines, out


def scan_text(text: str, is_python: bool) -> list[tuple[int, str, str, bool]]:
    """
    掃一段原始碼，回傳 (行號, 樣式標籤, 正規化行文字, 是否落在財報脈絡內)。

    與 scan() 分開是為了讓 tests/test_hardcoded_windows.py 能餵入歷史上十份缺陷的
    真實程式碼來驗證偵測能力——稽核自己也需要被稽核，否則「全綠」可能只代表
    規則寫壞了（本專案已有稽核說謊的前例）。
    """
    all_lines, lines = code_lines(text, is_python)
    out = []
    for lineno, raw in lines:
        for pattern, label in (PY_PATTERNS if is_python else TS_PATTERNS):
            if not re.search(pattern, raw):
                continue
            key = norm(raw)
            if key in EXEMPT:
                break
            ctx = "\n".join(all_lines[max(0, lineno - 4):lineno + 3])
            out.append((lineno, label, key, bool(CONTEXT.search(ctx))))
            break
    return out


def scan():
    targets = sorted((ROOT / "scripts").glob("*.py"))
    for ext in ("*.ts", "*.tsx"):
        targets += sorted(p for p in (ROOT / "frontend").rglob(ext)
                          if "node_modules" not in p.parts)

    findings, out_of_context = [], []
    for path in targets:
        if path.name == Path(__file__).name:      # 本檔的樣式字串會自我命中
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        rel = path.relative_to(ROOT).as_posix()
        for lineno, label, key, in_ctx in scan_text(text, path.suffix == ".py"):
            (findings if in_ctx else out_of_context).append((rel, lineno, label, key))
    return findings, out_of_context


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true",
                    help="連財報脈絡外的命中也列出（人工複查盲區 4 用）")
    args = ap.parse_args()

    findings, out_of_context = scan()

    print(f"硬編視窗掃描：{len(EXEMPT)} 項已登記豁免")
    if args.all and out_of_context:
        print(f"\n財報脈絡外的命中（僅供複查，不計入失敗）：{len(out_of_context)} 處")
        for rel, ln, label, key in out_of_context:
            print(f"  {rel}:{ln}  {label}\n      {key[:100]}")

    if not findings:
        print("✅ 沒有未登記的硬編視窗")
        return 0

    print(f"\n❌ 發現 {len(findings)} 處未登記的硬編視窗：\n")
    for rel, ln, label, key in findings:
        print(f"  {rel}:{ln}  {label}")
        print(f"      {key[:110]}")
    print("\n「取最近 N 期」的 N 若是期數判定，改呼叫 periodicity 的 ttm_periods()／")
    print("annual_windows()／ttm_month_window()；若確定不是，把整行文字加進本檔的")
    print("EXEMPT 並寫下理由——理由要能回答「為什麼列數在這裡等於期間」。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
