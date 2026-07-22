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
