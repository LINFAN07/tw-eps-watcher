// 除權息後向還原（即時計算、不儲存）——與 scripts/price_adjust.py 同一套邏輯。
//
// 原始收盤價在除息當天會機械性下跌，若直接畫進 P/E、P/B、P/S、P/FCF 河流圖，
// 會被誤讀成基本面訊號、扭曲高殖利率股的歷史估值帶。故河流圖價格線改用還原價。
// 免費層容量容不下把還原價存進資料庫，改在此即時計算。
// （殖利率河流圖不適用：殖利率本質是實際價 vs 股利，還原會虛增歷史殖利率。）

// 後向還原：adjusted(t) = close(t) × ∏ factor_d（所有除息日 d > t），
// factor_d = 1 − 現金股利 / 除息前一交易日收盤價。錨定今日 → 最新一日還原價==原始價。
// dates 須為升冪 ISO 字串；exList 為 [除息日, 現金股利]。回傳與 dates 對齊的還原價。
export function backAdjust(
  dates: string[], closes: number[], exList: [string, number][],
): number[] {
  if (dates.length === 0) return []
  const lastDate = dates[dates.length - 1]

  const factors: [string, number][] = []
  for (const [exDate, cash] of exList) {
    if (!cash || cash <= 0 || exDate > lastDate) continue
    // 第一個 >= exDate 的位置（dates 升冪，二分搜尋，等同 Python bisect_left）
    let lo = 0, hi = dates.length
    while (lo < hi) { const m = (lo + hi) >> 1; if (dates[m] < exDate) lo = m + 1; else hi = m }
    if (lo === 0) continue                    // 除息日早於所有股價，無基準
    const prevClose = closes[lo - 1]
    const f = 1 - cash / prevClose
    if (f <= 0 || f > 1) continue             // 股利 ≥ 前收（資料異常），跳過
    factors.push([exDate, f])
  }
  factors.sort((a, b) => (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0))

  const adjusted = new Array<number>(dates.length)
  let cum = 1
  let j = factors.length - 1
  for (let k = dates.length - 1; k >= 0; k--) {
    while (j >= 0 && factors[j][0] > dates[k]) { cum *= factors[j][1]; j-- }
    adjusted[k] = closes[k] * cum
  }
  return adjusted
}

// 便利函式：給一組（升冪）日收盤價與股利，回傳「日期 → 還原價」對照表。
export function adjustedMap(
  prices: { date: string; close_price: number }[],
  exList: [string, number][],
): Record<string, number> {
  const adj = backAdjust(prices.map(p => p.date), prices.map(p => Number(p.close_price)), exList)
  const m: Record<string, number> = {}
  prices.forEach((p, i) => { m[p.date] = adj[i] })
  return m
}
