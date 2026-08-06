// 由 scripts/export_quality_stats.py 產生，請勿手動編輯。
// Q4 品質濾網 + Q5 徽章的回測結果。重跑會覆寫此檔。
// 重跑：python scripts/export_quality_stats.py（會一起跑四支回測並做一致性把關）。

export interface QualityRow {
  group: string; n: number; median: number; mean: number
  positiveRate: number; winRate: number; worst10: number; loss30: number; loss50: number
}

/**
 * 便宜全體基準，等於 backtestStats.OVERALL 的「P/E 便宜」12 個月。
 * 前端以此對照兩份 lib 是否同步（見 lib/qualityBacktest.ts 的 isQualityInSync）——
 * 不同步時隱藏 Q4/Q5，寧可不顯示也不給過時數字。
 */
export const QUALITY_BASELINE = { n: 13663, median: 7.78 }
export const QUALITY_HORIZON = 12

export const BADGES: QualityRow[] = [
  {"group": "便宜全體", "n": 13663, "median": 7.78, "mean": 21.18, "positiveRate": 61.6, "winRate": 48.6, "worst10": -24.02, "loss30": 6.2, "loss50": 1.0},
  {"group": "⭐ 頂級優質（置頂＋正面標記）", "n": 5128, "median": 4.26, "mean": 16.18, "positiveRate": 56.0, "winRate": 43.5, "worst10": -29.35, "loss30": 9.6, "loss50": 1.8},
  {"group": "🔍 潛力黑馬（正面標記）", "n": 2260, "median": 6.19, "mean": 18.43, "positiveRate": 61.0, "winRate": 52.9, "worst10": -20.74, "loss30": 4.0, "loss50": 0.4},
  {"group": "兩者皆非（無徽章）", "n": 6275, "median": 11.23, "mean": 26.25, "positiveRate": 66.4, "winRate": 51.2, "worst10": -21.43, "loss30": 4.3, "loss50": 0.6}
]

export const ROE_FILTER: QualityRow[] = [
  {"group": "便宜全體（有 ROE）", "n": 13663, "median": 7.78, "mean": 21.18, "positiveRate": 61.6, "winRate": 48.6, "worst10": -24.02, "loss30": 6.2, "loss50": 1.0},
  {"group": "ROE 0~8%", "n": 1599, "median": 12.15, "mean": 27.0, "positiveRate": 69.0, "winRate": 52.5, "worst10": -16.95, "loss30": 2.9, "loss50": 0.6},
  {"group": "ROE 8~15%", "n": 4532, "median": 8.55, "mean": 23.39, "positiveRate": 64.7, "winRate": 50.8, "worst10": -21.04, "loss30": 4.0, "loss50": 0.4},
  {"group": "ROE ≥ 15%（濾網保留）", "n": 7532, "median": 6.06, "mean": 18.61, "positiveRate": 58.2, "winRate": 46.5, "worst10": -27.66, "loss30": 8.3, "loss50": 1.5},
  {"group": "濾網擋掉的全部（<15 或未知）", "n": 6131, "median": 9.61, "mean": 24.33, "positiveRate": 65.8, "winRate": 51.2, "worst10": -19.93, "loss30": 3.7, "loss50": 0.5}
]

export const MARGIN_FILTER: QualityRow[] = [
  {"group": "便宜全體（有利益率）", "n": 13198, "median": 7.74, "mean": 20.94, "positiveRate": 61.6, "winRate": 48.6, "worst10": -24.17, "loss30": 6.3, "loss50": 1.0},
  {"group": "利益率未知（其中金融）", "n": 190, "median": 18.11, "mean": 18.7, "positiveRate": 73.7, "winRate": 43.7, "worst10": -13.1, "loss30": 0.0, "loss50": 0.0},
  {"group": "利益率未知（非金融，前端擋）", "n": 275, "median": 4.03, "mean": 34.3, "positiveRate": 56.0, "winRate": 53.8, "worst10": -24.2, "loss30": 6.5, "loss50": 1.1},
  {"group": "利益率 < 0（本業虧損）", "n": 426, "median": 10.69, "mean": 25.87, "positiveRate": 64.8, "winRate": 53.8, "worst10": -27.61, "loss30": 7.7, "loss50": 0.9},
  {"group": "利益率 0~10%", "n": 5257, "median": 11.59, "mean": 26.52, "positiveRate": 67.0, "winRate": 51.6, "worst10": -20.87, "loss30": 4.1, "loss50": 0.5},
  {"group": "利益率 ≥ 10%（濾網保留）", "n": 7515, "median": 4.9, "mean": 16.76, "positiveRate": 57.6, "winRate": 46.1, "worst10": -26.87, "loss30": 7.8, "loss50": 1.4},
  {"group": "濾網擋掉的全部（<10 或未知）", "n": 6148, "median": 11.41, "mean": 26.58, "positiveRate": 66.6, "winRate": 51.6, "worst10": -21.43, "loss30": 4.3, "loss50": 0.6}
]

export const FILTER_COMPARE: QualityRow[] = [
  {"group": "便宜全體（無任何濾網）", "n": 13675, "median": 7.78, "mean": 21.17, "positiveRate": 61.6, "winRate": 48.6, "worst10": -24.02, "loss30": 6.2, "loss50": 1.0},
  {"group": "A · 現狀（四濾網全開）", "n": 3770, "median": 6.06, "mean": 16.97, "positiveRate": 58.8, "winRate": 43.5, "worst10": -26.83, "loss30": 7.7, "loss50": 1.1},
  {"group": "B · 建議（關兩個品質濾網）", "n": 9985, "median": 9.51, "mean": 22.6, "positiveRate": 64.2, "winRate": 49.3, "worst10": -22.25, "loss30": 5.2, "loss50": 0.8},
  {"group": "└ B 比 A 多出的那批", "n": 6215, "median": 11.68, "mean": 26.02, "positiveRate": 67.4, "winRate": 52.8, "worst10": -19.32, "loss30": 3.7, "loss50": 0.6}
]
