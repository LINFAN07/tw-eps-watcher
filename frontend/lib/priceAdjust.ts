// 除權息後向還原（即時計算、不儲存）——與 scripts/price_adjust.py 同一套邏輯。
// 兩邊必須同步修改，否則圖表畫的線與後端算出的估值帶會對不上。
//
// 原始收盤價在除權息當天會機械性下跌，若直接畫進 P/E、P/B、P/S、P/FCF 河流圖，
// 會被誤讀成基本面訊號。免費層容量容不下把還原價存進資料庫，改在此即時計算。
// （殖利率河流圖不適用：殖利率本質是實際價 vs 股利，還原會虛增歷史殖利率。）
//
// 2026-07-22 修正：配股（除權）先前完全沒有還原。
// 實例 1436：2025-07-25 原始單日跌 32.9%（台股漲跌幅上限 10%，超過必為除權息），
// 只用現金股利還原後仍有 −26.7% 跳空，那是配股 3.0143 元造成的。
// 影響 1,790 支（74%）。方向：還原後歷史價更低 → 歷史倍數更低 → 目標價更低，
// 亦即未還原等於【高估目標價、讓股票看起來比實際便宜】（實測 1436 三價下修 25~28%）。

/** 除權息事件：[除權息日, 現金股利, 股票股利]。股票股利不可省略，理由見上。 */
export type ExEvent = [string, number, number]

// 後向還原：adjusted(t) = close(t) × ∏ factor_d（所有除權息日 d > t），
// factor_d =（前收盤 − 現金股利）÷（前收盤 × (1 + 股票股利 ÷ 10)）
//   分子處理除息、分母處理除權（配股率 = 股票股利 ÷ 10，面額 10 元）。
// 錨定今日 → 最新一日還原價 == 原始價，現價不受影響。
//
// official 為交易所公告的還原因子（參考價 ÷ 前收盤價），有就優先用——
// 上面那條自算公式涵蓋不了現金增資與減資。兩者的日期取聯集：
// 只辦現金增資的除權息（配息配股皆為 0）根本不會出現在 exList。
export function backAdjust(
  dates: string[], closes: number[], exList: ExEvent[],
  official?: Record<string, number>,
): number[] {
  if (dates.length === 0) return []
  const lastDate = dates[dates.length - 1]

  const events = new Map(exList.map(([d, c, s]) => [d, [c || 0, s || 0] as const]))
  const allDates = [...new Set([...events.keys(), ...Object.keys(official ?? {})])].sort()

  const factors: [string, number][] = []
  for (const exDate of allDates) {
    if (exDate > lastDate) continue
    // 第一個 >= exDate 的位置（dates 升冪，二分搜尋，等同 Python bisect_left）
    let lo = 0, hi = dates.length
    while (lo < hi) { const m = (lo + hi) >> 1; if (dates[m] < exDate) lo = m + 1; else hi = m }
    if (lo === 0) continue                    // 除權息日早於所有股價，無基準

    let f = official?.[exDate]
    if (f !== undefined) {
      // 官方因子容許 >1：減資會使參考價高於前收，那是真實情況不是異常。
      // 上限 5 純為防呆（因子再大就不可能是除權息了）。
      if (!(f > 0 && f <= 5)) continue
    } else {
      const [cash, stock] = events.get(exDate)!
      if (cash <= 0 && stock <= 0) continue
      const prevClose = closes[lo - 1]
      f = (prevClose - cash) / (prevClose * (1 + stock / 10))
      if (f <= 0 || f > 1) continue           // 股利 ≥ 前收（資料異常），跳過
    }
    factors.push([exDate, f])
  }
  // factors 由已排序的 allDates 迭代產生，天然升冪，不需再排序

  const adjusted = new Array<number>(dates.length)
  let cum = 1
  let j = factors.length - 1
  for (let k = dates.length - 1; k >= 0; k--) {
    while (j >= 0 && factors[j][0] > dates[k]) { cum *= factors[j][1]; j-- }
    adjusted[k] = closes[k] * cum
  }
  return adjusted
}

// 便利函式：給一組（升冪）日收盤價與除權息事件，回傳「日期 → 還原價」對照表。
export function adjustedMap(
  prices: { date: string; close_price: number }[],
  exList: ExEvent[],
  official?: Record<string, number>,
): Record<string, number> {
  const adj = backAdjust(prices.map(p => p.date), prices.map(p => Number(p.close_price)),
                         exList, official)
  const m: Record<string, number> = {}
  prices.forEach((p, i) => { m[p.date] = adj[i] })
  return m
}
