// 財報揭露頻率的判定 —— 與 scripts/periodicity.py 同一套規則。
// 兩邊必須同步修改，否則河流圖的估值帶會與估值卡的數字對不上。
//
// ## 為什麼前端也需要這個
//
// 河流圖的三條帶 = 各時點的 TTM 基準值 × 後端算好的倍數百分位。
// 倍數來自後端（用 report_window 判定期數），TTM 卻是前端自己重算的。
// 前端原本硬寫 4 期，對半年報公司（興櫃）就是把兩年的獲利當成一年：
// 帶會整體上移約一倍，圖上的線與卡片上的數字兜不起來——正是
// priceAdjust.ts 檔頭警告的那個症狀，只是發生在 TTM 而不是還原因子上。
//
// ## 判定規則（與 Python 版逐條對應）
//
// 半年報公司只揭露 6/30 與 12/31 兩期，TTM 取 2 期；季報取 4 期。
// 只看最近 6 期：早年揭露頻率不同或單筆資料異常，會讓整支股票被誤判
// （4546 長亨全是 6/12 月，只有一筆 2020-03-31 例外，看全歷史會被判成季報，
// TTM 因此變成兩年獲利、高估 71%）。
// 期數少於 3 期一律採季報：「月份都落在 6/12」對只有 1~2 期的公司必然成立
// （新上市、Q1/Q3 尚未揭露），判成半年報會讓 TTM 少掉一半。

/** 判定時回看幾期，與 Python 版的 LOOKBACK 相同 */
export const LOOKBACK = 6

/** 少於這個期數就不下「半年報」結論，與 Python 版的 MIN_PERIODS_TO_JUDGE 相同 */
export const MIN_PERIODS_TO_JUDGE = 3

/**
 * TTM 應加總的期數：半年報 2、季報 4。
 * quarterEnds 為 ISO 日期字串（"2026-03-31"），順序不拘。
 */
export function reportWindow(quarterEnds: string[]): number {
  // 先依日期排序取最近 LOOKBACK 期，再看月份——
  // 若直接對月份排序，拿到的會是月份數字最大的幾期，不是最近的幾期
  const recent = [...quarterEnds].filter(Boolean).sort().reverse().slice(0, LOOKBACK)
  if (recent.length < MIN_PERIODS_TO_JUDGE) return 4

  const months = new Set(recent.map(d => d.slice(5, 7)))
  return months.size > 0 && [...months].every(m => m === '06' || m === '12') ? 2 : 4
}

// ─────────────── TTM 視窗（哪幾期加起來剛好 12 個月） ───────────────
//
// reportWindow 給的是「季報還是半年報」這個單一標籤，下游拿它去加總最近 w 列。
// 公司在期間中途改變揭露頻率時，最近 w 列會橫跨不同頻率的期別，加起來就不是
// 12 個月——2026-08-06 的事故正是如此：一整批興櫃轉上市櫃的公司在 2026-03
// 交出第一份季報，reportWindow 看到 3 月判季報，加總最近 4 列變成
// 2026-03(Q1)+2025-12(H2)+2025-06(H1)+2024-12(H2)＝21 個月。
//
// ⚠️ 當時只修了 Python 端。前端直到 2026-08-09 才補上，期間 43 支在市股票的
// 河流圖估值帶用的是錯的 TTM（7843 用 3.16，正確為 -0.14），方向固定偏高
// → 帶上移 →【圖上看起來比實際便宜】，且與同一頁 ValuationCard 的數字矛盾。
// 教訓：規則寫成「一律 import periodicity」時，要指明**兩種語言都算**。

/** 12 個月 = 4 季，與 Python 版的 TTM_QUARTERS 相同 */
export const TTM_QUARTERS = 4

/** 退回的視窗最多可比最新一期舊 12 個月，與 Python 版的 MAX_STALENESS_QUARTERS 相同 */
export const MAX_STALENESS_QUARTERS = 4

/** 合法的揭露節奏 → 每一期涵蓋幾個季。進行中的年度取前綴亦可 */
const CADENCES: ReadonlyArray<readonly [readonly number[], number]> = [
  [[3, 6, 9, 12], 1],   // 季報
  [[6, 12], 2],         // 半年報
]

const yearOf  = (end: string) => Number(end.slice(0, 4))
const monthOf = (end: string) => Number(end.slice(5, 7))

/** 期末日 → 全域季序號（2026-03-31 → 2026×4+0）。可加減、可比較 */
const quarterIndex = (end: string) => yearOf(end) * 4 + Math.floor((monthOf(end) - 1) / 3)

/**
 * {期末日: 涵蓋幾個季}。年度的期別組合不合法時，該年度所有期別都不列入——
 * 寧可不給答案，也不要用推不出來的涵蓋範圍算出一個看似正常的 TTM。
 */
function coverageOf(periodEnds: string[]): Map<string, number> {
  const byYear = new Map<number, string[]>()
  for (const end of periodEnds) {
    const year = yearOf(end)
    if (!Number.isFinite(year)) continue
    const bucket = byYear.get(year)
    if (bucket) bucket.push(end)
    else byYear.set(year, [end])
  }

  const coverage = new Map<string, number>()
  for (const ends of byYear.values()) {
    const sorted = [...ends].sort((a, b) => monthOf(a) - monthOf(b))
    const months = sorted.map(monthOf)
    // 必須是某個節奏的「前綴」——[3,6,12]、[9,12]、[12] 都推不出來，整年跳過
    const hit = CADENCES.find(([pattern]) =>
      months.length <= pattern.length && months.every((m, i) => m === pattern[i]))
    if (!hit) continue
    for (const end of sorted) coverage.set(end, hit[1])
  }
  return coverage
}

/** 從 end 往前累加涵蓋季數，剛好 4 季就成立；跨過或不連續就是湊不出來 */
function windowEndingAt(ordered: string[], coverage: Map<string, number>,
                        end: string): string[] | null {
  const window: string[] = []
  let total = 0
  for (let i = ordered.indexOf(end); i >= 0; i--) {
    const period = ordered[i]
    const span = coverage.get(period)!
    // 連續性：後一期的季序號必須正好比前一期多出「前一期涵蓋的季數」
    if (window.length && quarterIndex(window[0]) - quarterIndex(period) !== span) return null
    window.unshift(period)
    total += span
    if (total === TTM_QUARTERS) return window
    if (total > TTM_QUARTERS) return null
  }
  return null
}

/**
 * {期末日: 以該期為結尾、剛好涵蓋 12 個月的期別清單（湊不出為 null）}，由舊到新。
 *
 * 逐期建 TTM 序列時請直接用這支——coverage 只會算一次。
 */
export function ttmWindows(periodEnds: string[]): Map<string, string[] | null> {
  const ends = [...new Set(periodEnds.filter(Boolean))]
  const coverage = coverageOf(ends)
  const ordered = [...coverage.keys()].sort((a, b) => quarterIndex(a) - quarterIndex(b))
  return new Map(ordered.map(end => [end, windowEndingAt(ordered, coverage, end)]))
}

/**
 * 最近一組完整 12 個月的期別。最新一期湊不出來時往前退，但最多退 12 個月——
 * 再舊的 TTM 配今天的股價已無意義。
 */
/**
 * 緊接在最近一組 12 個月【之前】的那組完整 12 個月（去年同期），湊不出回 null。
 *
 * **不可用「排序後往前退一格」代替**：那只保證前一組自己是 12 個月，不保證它
 * 緊接在後一組之前。中間缺一整年時會拿到兩年前那組，而畫面上照樣顯示
 * 「年增 N%」——值在合理範圍、內部一致性檢查全過，錯誤無從察覺。
 * 例：半年報公司只有 2023 與 2025 兩年，退一格會拿 FY2023 當 FY2025 的去年同期。
 */
export function previousTtmPeriods(periodEnds: string[]): string[] | null {
  const ends = [...new Set(periodEnds.filter(Boolean))].sort(
    (a, b) => quarterIndex(a) - quarterIndex(b))
  const current = ttmPeriods(ends)
  if (!current) return null
  const coverage = coverageOf(ends)
  const ordered = [...coverage.keys()].sort((a, b) => quarterIndex(a) - quarterIndex(b))
  const idx = ordered.indexOf(current[0])
  if (idx <= 0) return null
  const prevEnd = ordered[idx - 1]
  // 相鄰性：current 的第一期必須正好接在 prevEnd 之後，跨距等於 prevEnd 的涵蓋季數
  if (quarterIndex(current[0]) - quarterIndex(prevEnd) !== coverage.get(prevEnd)) return null
  return windowEndingAt(ordered, coverage, prevEnd)
}

export function ttmPeriods(periodEnds: string[]): string[] | null {
  const ends = periodEnds.filter(Boolean)
  if (!ends.length) return null
  // 落後程度以「實際最新一期」為準，不是「有合法視窗的最新一期」——
  // 否則最新年度整年不合法時，會把一年前的 TTM 當成最新的而不自知
  const newest = Math.max(...ends.map(quarterIndex))
  const windows = ttmWindows(ends)
  for (const end of [...windows.keys()].sort((a, b) => quarterIndex(b) - quarterIndex(a))) {
    if (newest - quarterIndex(end) > MAX_STALENESS_QUARTERS) return null
    const window = windows.get(end)
    if (window) return window
  }
  return null
}

// ─────────────── 財報真正可得的日期 ───────────────

/**
 * 主管機關的申報期限：[年份加幾年, 月, 日]。
 * 半年報公司（興櫃）6/30 的期限是 8/31，取兩者較晚者以策保守。
 */
const FILING_DEADLINE: Record<number, [number, number, number]> = {
  3: [0, 5, 15], 6: [0, 8, 31], 9: [0, 11, 14], 12: [1, 3, 31],
}

/**
 * 期末日 → 該期財報在市場上真正可得的日期（ISO 字串）。
 *
 * 直接拿期末日當可用日，等於偷看未來：2026-04-30 不可能知道 2026Q1 的 EPS，
 * 那要到 5/15 才申報。訊號回放（`/api/signals`）與 `backtest_valuation.py`
 * 必須用同一份定義，否則兩邊對「那天算不算便宜」會給出不同答案。
 */
export function availableDate(periodEnd: string): string {
  const deadline = FILING_DEADLINE[monthOf(periodEnd)]
  // 非季末月份代表資料本身有問題，出聲比安靜地給一個日期好
  if (!deadline) throw new Error(`不是合法的期末日：${periodEnd}`)
  const [offset, month, day] = deadline
  return `${String(yearOf(periodEnd) + offset).padStart(4, '0')}-`
    + `${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`
}

// ─────────────── 月度資料的 TTM 視窗（月營收） ───────────────
//
// 月營收沒有揭露頻率的問題（每家每月一筆），規則單純：連續 12 個月，缺一個月就不算。
// 「最近 12 列」不等於「連續 12 個月」——全市場 42 支有缺月（共 388 個月），
// 取 12 列會橫跨 13 個月以上，TTM 營收灌水。

/** 12 個月，與 Python 版的 TTM_MONTHS 相同 */
export const TTM_MONTHS = 12

/** YYYY-MM（多餘字元忽略）→ 月份序號。轉成整數後加減月份不必處理跨年進位 */
export function monthIndex(ym: string): number {
  return Number(ym.slice(0, 4)) * 12 + Number(ym.slice(5, 7)) - 1
}

/** 截至 endMonth（含）的連續 12 個月，格式 YYYY-MM。缺任一個月回 null */
export function ttmMonthWindow(available: string[], endMonth: string): string[] | null {
  const have = new Set(available.map(m => m.slice(0, 7)))
  const last = monthIndex(endMonth)
  const months = Array.from({ length: TTM_MONTHS }, (_, i) => {
    const n = last - TTM_MONTHS + 1 + i
    return `${String(Math.floor(n / 12)).padStart(4, '0')}-${String((n % 12) + 1).padStart(2, '0')}`
  })
  return months.every(m => have.has(m)) ? months : null
}
