"""
periodicity.py — 財報揭露頻率的判定（共用純函式）

## 為什麼要獨立成一個模組

「這家公司是季報還是半年報」這個判斷，決定 TTM 要加總幾期。判錯的代價是
把兩年的獲利當成一年，直接高估一倍以上。

2026-07-22 一天之內，這個判斷在四個地方各寫了一份，跑出三種答案：

    calculate_valuation.py      最近 6 期
    calculate_alt_valuations.py 最近 8 期（註解卻寫「同 _eps_window」）
    audit_external.py           常數 6（靠註解與生產端「約定」一致）
    backtest_valuation.py       全歷史（＝當天要修掉的那個缺陷本身）

修 bug 時只改了其中一處，其餘三處各自漂移。回測那份尤其要命——所有旗標
門檻（pb_reliable 的 2 倍、pe_deep_discount 的 3 倍、帶寬分位）都是用回測
算出來的，它用錯 TTM，等於門檻建在污染的樣本上。

靠註解約定「兩邊必須相同」是沒有機制的。這個模組讓四處 import 同一個函式。

## 判定規則

半年報公司（多為興櫃）只揭露 6/30 與 12/31 兩期，TTM 取 2 期；季報取 4 期。

**只看最近 6 期**，不看全部歷史：早年揭露頻率不同或單筆資料異常，會讓整支
股票被誤判。實例：
  - 4546 長亨 的 EPS 全是 6/12 月，只有一筆 2020-03-31 例外。看全歷史會被
    判成季報，ttm_eps 算成 12.98（正確 7.58，高估 71%），目標價虛高、
    被判「便宜」進了排行榜。全市場 22 檔同症狀，最嚴重者高估 350%。
  - 5254 欣訊科技 的最近第 7 期是 2023-03-31。視窗設 8 期仍會誤判——
    這是為什麼是 6 而不是 8：季報 6 期＝1.5 年，已足以判斷頻率，
    再往前拉只會多納入陳年的異常期別。

已知限制：若某公司真的在期間中途改變揭露頻率，歷史序列前段的 TTM 會用錯
期數。半年報公司幾乎都是興櫃小型股、鮮少改頻率，故不為此增加複雜度。
"""

from collections.abc import Iterable

# 判定時回看幾期。改這個常數會同時影響計算、回測與稽核——那正是重點。
LOOKBACK = 6

# 半年報公司的季末月份集合
_HALF_YEAR_MONTHS = {6, 12}

# 少於這個期數就不下「半年報」結論（見 report_window 的說明）
MIN_PERIODS_TO_JUDGE = 3


def report_window(quarter_ends: Iterable) -> int:
    """
    回傳 TTM 應加總的期數：半年報 2、季報 4。

    quarter_ends 可以是 ISO 日期字串（"2026-03-31"）或 date/datetime，
    順序不拘，內部自行取最近 LOOKBACK 期。同一次呼叫請勿混用型別
    （排序需要可比較）。
    """
    # 先依「日期」排序取最近 LOOKBACK 期，再看月份——
    # 若直接對月份排序取前 N 個，拿到的會是月份數字最大的幾期，不是最近的幾期
    recent = sorted((d for d in quarter_ends if d), reverse=True)[:LOOKBACK]
    months = {m for m in (_month_of(d) for d in recent) if m}

    # 期數不足時一律採季報。「月份都落在 6/12」對只有 1~2 期的公司必然成立
    # （新上市、或 Q1/Q3 尚未揭露），判成半年報會讓 TTM 只加總兩季、
    # 少掉一半獲利 → 目標價腰斬 → 誤標「昂貴」。
    # 採 4 期是安全的一邊：資料真的不足時 rolling(4) 會得到 NaN、該股沒有估值，
    # 而判成 2 期反而會用不完整的資料算出一個看似正常的數字。
    if len(recent) < MIN_PERIODS_TO_JUDGE:
        return 4
    return 2 if months <= _HALF_YEAR_MONTHS else 4


def _month_of(value) -> int | None:
    """從 ISO 字串或 date/datetime 取出月份"""
    month = getattr(value, "month", None)
    if month is not None:
        # pd.NaT 的 .month 是 NaN 且 bool(pd.NaT) 為 True，過濾不掉，
        # 直接 int() 會拋 ValueError 讓整支腳本掛掉
        return int(month) if month == month else None   # NaN != NaN
    text = str(value or "")
    # "2026-03-31" → 03
    return int(text[5:7]) if len(text) >= 7 and text[5:7].isdigit() else None
