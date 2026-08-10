"""
periodicity.py — TTM 視窗的單一來源（共用純函式）

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

## report_window 的已知限制，與 ttm_window 為何存在

`report_window` 給的是「這家公司是季報還是半年報」這個**單一標籤**，下游拿它去
`rolling(w)`／`iloc[-w:]`——也就是**加總最近 w 列**。當公司的揭露頻率在期間中途
改變時，最近 w 列會橫跨不同頻率的期別，加起來就不是 12 個月。

原本這裡寫著「半年報公司幾乎都是興櫃小型股、鮮少改頻率，故不為此增加複雜度」。
**2026-08-06 證明這個假設是錯的**：今年一整批興櫃轉上市櫃的公司同時在 2026-03
交出第一份季報，`report_window` 看到 3 月就判季報，`rolling(4)` 於是加總
`2026-03(Q1) + 2025-12(H2) + 2025-06(H1) + 2024-12(H2)`——**21 個月**的獲利。
全市場 39 檔如此，另有 8 檔因期別真有洞而同型出錯（已與 FinMind 逐檔比對，
洞是真的、不是漏抓）。方向固定：TTM 灌水 → 目標價虛高 →【看起來比實際便宜】，
其中 6 檔當時正掛在便宜排行榜上。

`ttm_window()` 改問一個不會被標籤誤導的問題：**哪幾期加起來剛好是 12 個月？**
- 純季報 → 最近 4 季
- 純半年報 → 最近 2 期
- 轉換期公司 → 退回上一組完整 12 個月（湧盛改用 FY2025，落後一季但數字正確）
- 真的湊不出 → 回 None，不給估值（資料誠信原則第 3、4 條）

## 每一期涵蓋幾個季，是從資料推論出來的

期別本身不帶「我涵蓋幾個月」的欄位，只能從同一會計年度裡的期別組合反推。
只承認台灣法定的兩種揭露節奏，其餘一律拒絕推論：

    月份組合為 [3] / [3,6] / [3,6,9] / [3,6,9,12] → 季報，每期涵蓋 1 季
    月份組合為 [6] / [6,12]                        → 半年報，每期涵蓋 2 季
    其餘（如 [3,6,12]、[12]、[9,12]）              → 推不出來，該年度整年不參與

**盲區**：一個季報公司若剛好只缺 Q1，該年度會變成 [6,9,12] → 不合法 → 整年不用，
這是安全的一邊。但若只留下 [6,12]（缺 Q1 與 Q3），會被誤判成半年報而**重複計算**。
無法從資料分辨「沒申報」與「我們沒抓到」，故上線前已逐檔問過第二來源；
日後若 `eps_quarterly` 出現整批漏抓，這個推論會跟著錯。
`[12]` 單獨出現一律視為不合法——台灣沒有只揭露年報的上市櫃公司，
出現這種組合代表資料不全，而非公司真的一年只報一次。
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


# ─────────────── TTM 視窗（哪幾期加起來剛好 12 個月） ───────────────

TTM_QUARTERS = 4          # 12 個月 = 4 季
MAX_STALENESS_QUARTERS = 4  # 退回的視窗最多可比最新一期舊 12 個月

# 合法的揭露節奏 → 每一期涵蓋幾個季。進行中的年度取前綴亦可
_CADENCES = (((3, 6, 9, 12), 1),   # 季報
             ((6, 12),       2))   # 半年報


def _quarter_index(value) -> int | None:
    """期末日 → 全域季序號（2026-03-31 → 2026×4+0）。可加減、可比較"""
    month = _month_of(value)
    year  = _year_of(value)
    return None if month is None or year is None else year * 4 + (month - 1) // 3


def _coverage(period_ends: list) -> dict:
    """
    {期末日: 涵蓋幾個季}。年度的期別組合不合法時，該年度所有期別都不列入——
    寧可不給答案，也不要用推不出來的涵蓋範圍算出一個看似正常的 TTM。
    """
    by_year: dict[int, list] = {}
    for end in period_ends:
        year = _year_of(end)
        if year is not None:
            by_year.setdefault(year, []).append(end)

    coverage = {}
    for ends in by_year.values():
        ends = sorted(ends, key=_month_of)
        months = tuple(_month_of(e) for e in ends)
        span = next((s for pattern, s in _CADENCES if months == pattern[:len(months)]), None)
        if span is None:
            continue                       # 不合法的組合，整年跳過
        coverage.update({e: span for e in ends})
    return coverage


def _window_ending_at(ordered: list, coverage: dict, end) -> list | None:
    """從 end 往前累加涵蓋季數，剛好 4 季就成立；跨過或不連續就是湊不出來"""
    window, total = [], 0
    for period in reversed(ordered[:ordered.index(end) + 1]):
        # 連續性：後一期的季序號必須正好比前一期多出「前一期涵蓋的季數」
        if window and _quarter_index(window[0]) - _quarter_index(period) != coverage[period]:
            return None
        window.insert(0, period)
        total += coverage[period]
        if total == TTM_QUARTERS:
            return window
        if total > TTM_QUARTERS:
            return None
    return None


def ttm_windows(period_ends) -> dict:
    """
    {期末日: 以該期為結尾、剛好涵蓋 12 個月的期別清單（湊不出為 None）}。

    這是本模組的基本操作，`ttm_window` 與 `ttm_periods` 都建立在它之上——
    逐期建 TTM 序列時請直接用這支，coverage 只會算一次（逐期呼叫 `ttm_window`
    會讓每支股票變成 O(n²)）。
    """
    ends = sorted({e for e in period_ends if e is not None and e == e}, key=_quarter_index)
    coverage = _coverage(ends)
    ordered = sorted(coverage, key=_quarter_index)
    return {end: _window_ending_at(ordered, coverage, end) for end in ordered}


def ttm_window(period_ends, end) -> list | None:
    """截至 end（含）剛好涵蓋 12 個月的連續期別（由舊到新），湊不出回 None"""
    return ttm_windows(period_ends).get(end)


def previous_ttm_periods(period_ends) -> list | None:
    """
    緊接在最近一組 12 個月【之前】的那組完整 12 個月（去年同期），湊不出回 None。

    **不可用「排序後往前退一格」代替**：那只保證前一組自己是 12 個月，不保證它
    緊接在後一組之前。中間缺一整年時會拿到兩年前那組，而畫面上照樣顯示
    「年增 N%」——值在合理範圍、內部一致性檢查全過，錯誤無從察覺。
    例：半年報公司只有 2023 與 2025 兩年，退一格會拿 FY2023 當 FY2025 的去年同期。
    """
    ends = sorted({e for e in period_ends if e is not None and e == e},
                  key=_quarter_index)
    current = ttm_periods(ends)
    if current is None:
        return None
    coverage = _coverage(ends)
    ordered = sorted(coverage, key=_quarter_index)
    idx = ordered.index(current[0])
    if idx == 0:
        return None
    prev_end = ordered[idx - 1]
    # 相鄰性：current 的第一期必須正好接在 prev_end 之後，跨距等於 prev_end 的涵蓋季數
    if _quarter_index(current[0]) - _quarter_index(prev_end) != coverage[prev_end]:
        return None
    return _window_ending_at(ordered, coverage, prev_end)


def ttm_periods(period_ends) -> list | None:
    """
    最近一組完整 12 個月的期別。最新一期湊不出來時往前退，
    但最多退 12 個月——再舊的 TTM 配今天的股價已無意義（同下市股的機制）。

    落後是拿「不合法年度」換來的：湧盛 2026-03 是轉季報後的第一份季報，
    往前湊不到四季，退回 FY2025（2025-06 + 2025-12）落後一季但數字為真。
    """
    ends = [e for e in period_ends if e is not None and e == e]
    if not ends:
        return None
    # 落後程度以「實際最新一期」為準，不是以「有合法視窗的最新一期」——
    # 否則最新年度整年不合法時，會把一年前的 TTM 當成最新的而不自知
    newest = max(_quarter_index(e) for e in ends)
    windows = ttm_windows(ends)
    for end in sorted(windows, key=_quarter_index, reverse=True):
        if newest - _quarter_index(end) > MAX_STALENESS_QUARTERS:
            return None
        if windows[end]:
            return windows[end]
    return None


# ─────────────── 財報真正可得的日期 ───────────────

# 主管機關的申報期限。半年報公司（興櫃）6/30 的期限是 8/31，
# 取兩者較晚者以策保守——寧可晚一點才用，也不要偷看還沒公布的財報。
_FILING_DEADLINE = {3: (0, 5, 15), 6: (0, 8, 31), 9: (0, 11, 14), 12: (1, 3, 31)}


def available_date(period_end) -> str:
    """
    期末日 → 該期財報在市場上真正可得的日期（ISO 字串）。

    直接拿期末日當可用日，等於讓任何「以當時資料重算」的東西偷看未來：
    2026-04-30 不可能知道 2026Q1 的 EPS，那要到 5/15 才申報。

    回測與前端的訊號回放都必須用這個，否則兩邊會對「那天算不算便宜」給出
    不同答案（同 report_window 那次的分岔形狀）。
    """
    year, month = _year_of(period_end), _month_of(period_end)
    if year is None or month is None or month not in _FILING_DEADLINE:
        # 非季末月份代表資料本身有問題，出聲比安靜地給一個日期好
        raise ValueError(f"不是合法的期末日：{period_end!r}")
    offset, m, d = _FILING_DEADLINE[month]
    return f"{year + offset:04d}-{m:02d}-{d:02d}"


# ─────────────── 月度資料的 TTM 視窗（月營收） ───────────────
#
# 月營收沒有「揭露頻率」的問題——每家公司都是一個月一筆，所以規則單純得多：
# 連續 12 個月，缺一個月就不算。獨立成函式只為了不讓這段邏輯在
# calculate_alt_valuations 與 calculate_quality_metrics 各長一份（那正是本模組的存在理由）。

TTM_MONTHS = 12


def month_index(ym) -> int:
    """YYYY-MM（多餘的字元會被忽略）→ 月份序號。轉成整數後加減月份不必處理跨年進位"""
    text = str(ym)
    return int(text[:4]) * 12 + int(text[5:7]) - 1


def ttm_month_window(available, end_month) -> list | None:
    """
    截至 end_month（含）的連續 12 個月，格式 YYYY-MM。缺任一個月回 None——
    用不足 12 個月的營收當分母會壓低分母、虛增比率（同 backtest_margin_filter 的規則）。
    """
    have = {str(m)[:7] for m in available}
    last = month_index(end_month)
    months = [f"{i // 12:04d}-{i % 12 + 1:02d}" for i in range(last - TTM_MONTHS + 1, last + 1)]
    return months if all(m in have for m in months) else None


def ttm_months(available) -> list | None:
    """
    最近一組完整 12 個月。最新一個月湊不齊時往前退，但最多退 12 個月——
    再舊的營收配今天的股價已無意義（同 ttm_periods 的理由）。
    """
    have = sorted({str(m)[:7] for m in available})
    if not have:
        return None
    newest = month_index(have[-1])
    for end in reversed(have):
        if newest - month_index(end) > TTM_MONTHS:
            return None
        window = ttm_month_window(have, end)
        if window:
            return window
    return None


def _year_of(value) -> int | None:
    """從 ISO 字串或 date/datetime 取出年份"""
    year = getattr(value, "year", None)
    if year is not None:
        return int(year) if year == year else None
    text = str(value or "")
    return int(text[:4]) if len(text) >= 4 and text[:4].isdigit() else None


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
