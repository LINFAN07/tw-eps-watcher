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
export const QUALITY_BASELINE = { n: 14648, median: 7.26 }
export const QUALITY_HORIZON = 12

export const BADGES: QualityRow[] = [
  {"group": "便宜全體", "n": 14648, "median": 7.26, "mean": 20.85, "positiveRate": 60.9, "winRate": 45.8, "worst10": -23.94, "loss30": 6.0, "loss50": 1.0},
  {"group": "⭐ 頂級優質（置頂＋正面標記）", "n": 5448, "median": 3.49, "mean": 15.88, "positiveRate": 55.0, "winRate": 42.2, "worst10": -29.62, "loss30": 9.8, "loss50": 2.0},
  {"group": "🔍 潛力黑馬（正面標記）", "n": 2379, "median": 7.25, "mean": 18.84, "positiveRate": 62.3, "winRate": 49.2, "worst10": -18.49, "loss30": 2.6, "loss50": 0.1},
  {"group": "兩者皆非（無徽章）", "n": 6821, "median": 10.23, "mean": 25.53, "positiveRate": 65.2, "winRate": 47.5, "worst10": -21.46, "loss30": 4.1, "loss50": 0.5}
]

export const ROE_FILTER: QualityRow[] = [
  {"group": "便宜全體（有 ROE）", "n": 14648, "median": 7.26, "mean": 20.85, "positiveRate": 60.9, "winRate": 45.8, "worst10": -23.94, "loss30": 6.0, "loss50": 1.0},
  {"group": "ROE 0~8%", "n": 1783, "median": 11.63, "mean": 29.35, "positiveRate": 67.5, "winRate": 47.6, "worst10": -17.74, "loss30": 2.8, "loss50": 0.4},
  {"group": "ROE 8~15%", "n": 4957, "median": 8.3, "mean": 22.2, "positiveRate": 64.3, "winRate": 47.2, "worst10": -19.86, "loss30": 3.2, "loss50": 0.3},
  {"group": "ROE ≥ 15%（濾網保留）", "n": 7908, "median": 5.4, "mean": 18.1, "positiveRate": 57.3, "winRate": 44.6, "worst10": -27.74, "loss30": 8.5, "loss50": 1.6},
  {"group": "濾網擋掉的全部（<15 或未知）", "n": 6740, "median": 9.21, "mean": 24.09, "positiveRate": 65.1, "winRate": 47.3, "worst10": -19.44, "loss30": 3.1, "loss50": 0.3}
]

export const MARGIN_FILTER: QualityRow[] = [
  {"group": "便宜全體（有利益率）", "n": 14272, "median": 7.09, "mean": 20.59, "positiveRate": 60.7, "winRate": 45.8, "worst10": -24.04, "loss30": 6.1, "loss50": 1.1},
  {"group": "利益率未知（其中金融）", "n": 175, "median": 15.41, "mean": 18.5, "positiveRate": 69.1, "winRate": 46.9, "worst10": -15.01, "loss30": 0.0, "loss50": 0.0},
  {"group": "利益率未知（非金融，前端擋）", "n": 201, "median": 12.71, "mean": 41.36, "positiveRate": 71.6, "winRate": 45.8, "worst10": -14.16, "loss30": 2.5, "loss50": 0.0},
  {"group": "利益率 < 0（本業虧損）", "n": 530, "median": 5.88, "mean": 21.57, "positiveRate": 60.2, "winRate": 50.9, "worst10": -24.81, "loss30": 6.2, "loss50": 0.4},
  {"group": "利益率 0~10%", "n": 5753, "median": 10.56, "mean": 25.93, "positiveRate": 65.6, "winRate": 47.8, "worst10": -21.25, "loss30": 4.1, "loss50": 0.5},
  {"group": "利益率 ≥ 10%（濾網保留）", "n": 7989, "median": 4.69, "mean": 16.69, "positiveRate": 57.2, "winRate": 44.0, "worst10": -26.3, "loss30": 7.6, "loss50": 1.5},
  {"group": "濾網擋掉的全部（<10 或未知）", "n": 6659, "median": 10.46, "mean": 25.85, "positiveRate": 65.4, "winRate": 48.0, "worst10": -21.4, "loss30": 4.1, "loss50": 0.5}
]

export const FILTER_COMPARE: QualityRow[] = [
  {"group": "便宜全體（無任何濾網）", "n": 14673, "median": 7.27, "mean": 20.9, "positiveRate": 61.0, "winRate": 45.8, "worst10": -23.93, "loss30": 6.0, "loss50": 1.0},
  {"group": "A · 現狀（四濾網全開）", "n": 3989, "median": 4.85, "mean": 16.04, "positiveRate": 56.8, "winRate": 42.1, "worst10": -27.96, "loss30": 8.8, "loss50": 1.4},
  {"group": "B · 建議（關兩個品質濾網）", "n": 10623, "median": 8.46, "mean": 21.49, "positiveRate": 62.6, "winRate": 46.2, "worst10": -22.81, "loss30": 5.4, "loss50": 0.8},
  {"group": "└ B 比 A 多出的那批", "n": 6634, "median": 10.49, "mean": 24.77, "positiveRate": 66.1, "winRate": 48.6, "worst10": -19.67, "loss30": 3.4, "loss50": 0.4}
]
