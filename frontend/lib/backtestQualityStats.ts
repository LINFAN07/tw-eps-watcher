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
export const QUALITY_BASELINE = { n: 13406, median: 8.01 }
export const QUALITY_HORIZON = 12

export const BADGES: QualityRow[] = [
  {"group": "便宜全體", "n": 13406, "median": 8.01, "mean": 21.54, "positiveRate": 62.0, "winRate": 49.1, "worst10": -23.77, "loss30": 5.9, "loss50": 0.9},
  {"group": "⭐ 頂級優質（置頂＋正面標記）", "n": 5030, "median": 4.73, "mean": 16.53, "positiveRate": 56.5, "winRate": 44.1, "worst10": -28.86, "loss30": 9.2, "loss50": 1.7},
  {"group": "🔍 潛力黑馬（正面標記）", "n": 2238, "median": 6.3, "mean": 18.67, "positiveRate": 61.3, "winRate": 53.4, "worst10": -20.45, "loss30": 3.8, "loss50": 0.4},
  {"group": "兩者皆非（無徽章）", "n": 6138, "median": 11.5, "mean": 26.69, "positiveRate": 66.9, "winRate": 51.5, "worst10": -20.87, "loss30": 4.0, "loss50": 0.5}
]

export const ROE_FILTER: QualityRow[] = [
  {"group": "便宜全體（有 ROE）", "n": 13406, "median": 8.01, "mean": 21.54, "positiveRate": 62.0, "winRate": 49.1, "worst10": -23.77, "loss30": 5.9, "loss50": 0.9},
  {"group": "ROE 0~8%", "n": 1555, "median": 12.62, "mean": 27.84, "positiveRate": 69.8, "winRate": 53.0, "worst10": -15.68, "loss30": 1.9, "loss50": 0.0},
  {"group": "ROE 8~15%", "n": 4459, "median": 8.6, "mean": 23.58, "positiveRate": 64.8, "winRate": 51.1, "worst10": -20.86, "loss30": 3.8, "loss50": 0.4},
  {"group": "ROE ≥ 15%（濾網保留）", "n": 7392, "median": 6.44, "mean": 18.98, "positiveRate": 58.7, "winRate": 47.0, "worst10": -27.26, "loss30": 8.0, "loss50": 1.4},
  {"group": "濾網擋掉的全部（<15 或未知）", "n": 6014, "median": 9.76, "mean": 24.69, "positiveRate": 66.1, "winRate": 51.6, "worst10": -19.4, "loss30": 3.3, "loss50": 0.3}
]

export const MARGIN_FILTER: QualityRow[] = [
  {"group": "便宜全體（有利益率）", "n": 12973, "median": 7.95, "mean": 21.24, "positiveRate": 61.9, "winRate": 49.0, "worst10": -23.81, "loss30": 6.0, "loss50": 0.9},
  {"group": "利益率未知（其中金融）", "n": 186, "median": 19.25, "mean": 19.3, "positiveRate": 75.3, "winRate": 42.5, "worst10": -13.91, "loss30": 0.0, "loss50": 0.0},
  {"group": "利益率未知（非金融，前端擋）", "n": 247, "median": 5.78, "mean": 38.74, "positiveRate": 59.5, "winRate": 58.7, "worst10": -23.91, "loss30": 5.7, "loss50": 1.2},
  {"group": "利益率 < 0（本業虧損）", "n": 422, "median": 10.69, "mean": 25.57, "positiveRate": 64.9, "winRate": 54.0, "worst10": -27.32, "loss30": 7.6, "loss50": 0.9},
  {"group": "利益率 0~10%", "n": 5167, "median": 11.89, "mean": 26.92, "positiveRate": 67.4, "winRate": 51.9, "worst10": -20.03, "loss30": 3.7, "loss50": 0.4},
  {"group": "利益率 ≥ 10%（濾網保留）", "n": 7384, "median": 5.13, "mean": 17.02, "positiveRate": 57.9, "winRate": 46.7, "worst10": -26.32, "loss30": 7.5, "loss50": 1.3},
  {"group": "濾網擋掉的全部（<10 或未知）", "n": 6022, "median": 11.72, "mean": 27.08, "positiveRate": 67.1, "winRate": 52.0, "worst10": -20.8, "loss30": 3.9, "loss50": 0.4}
]

export const FILTER_COMPARE: QualityRow[] = [
  {"group": "便宜全體（無任何濾網）", "n": 13418, "median": 8.01, "mean": 21.53, "positiveRate": 62.0, "winRate": 49.1, "worst10": -23.76, "loss30": 5.9, "loss50": 0.9},
  {"group": "A · 現狀（四濾網全開）", "n": 3717, "median": 6.26, "mean": 16.98, "positiveRate": 58.9, "winRate": 43.8, "worst10": -26.68, "loss30": 7.6, "loss50": 1.1},
  {"group": "B · 建議（關兩個品質濾網）", "n": 9804, "median": 9.78, "mean": 22.91, "positiveRate": 64.5, "winRate": 49.7, "worst10": -21.87, "loss30": 4.9, "loss50": 0.7},
  {"group": "└ B 比 A 多出的那批", "n": 6087, "median": 12.02, "mean": 26.53, "positiveRate": 67.9, "winRate": 53.3, "worst10": -18.41, "loss30": 3.3, "loss50": 0.5}
]
