// 由 scripts/backtest_yield.py 產生，請勿手動編輯。
// 重跑回測後此檔會被覆寫；判讀邏輯寫在 lib/yieldBacktest.ts。

export interface YieldOverallRow {
  horizon: number; group: string; n: number
  median: number; mean: number; bench: number; winRate: number; positiveRate: number
}

export interface YieldIndustryRow {
  industry: string; n: number
  median: number; winRate: number; peer: number; excess: number
}

/** 榜單的篩選條件，也是 OVERALL 中代表榜單本身的那一組 */
export const YIELD_RANK_GROUP = 'P/E 便宜 × 高殖利率'

/** 回測期間取自資料本身的第一與最後一個月末交易日 */
export const YIELD_BACKTEST_PERIOD = { from: '2016-07-29', to: '2026-07-22', months: 121 }

/** 分產業結果的持有期（月） */
export const YIELD_HORIZON = 12

export const YIELD_OVERALL: YieldOverallRow[] = [
  {"horizon": 6, "group": "全市場等權（對照）", "n": 219633, "median": 1.46, "mean": 9.29, "bench": 6.92, "winRate": 41.4, "positiveRate": 53.3},
  {"horizon": 12, "group": "全市場等權（對照）", "n": 205731, "median": 4.36, "mean": 19.2, "bench": 13.86, "winRate": 46.5, "positiveRate": 56.6},
  {"horizon": 24, "group": "全市場等權（對照）", "n": 179171, "median": 14.38, "mean": 39.33, "bench": 16.86, "winRate": 48.7, "positiveRate": 63.7},
  {"horizon": 6, "group": "P/E 便宜", "n": 15325, "median": 2.64, "mean": 8.64, "bench": 7.19, "winRate": 42.3, "positiveRate": 56.0},
  {"horizon": 12, "group": "P/E 便宜", "n": 14591, "median": 7.27, "mean": 20.87, "bench": 16.63, "winRate": 46.0, "positiveRate": 61.0},
  {"horizon": 24, "group": "P/E 便宜", "n": 13080, "median": 22.5, "mean": 50.31, "bench": 56.7, "winRate": 45.2, "positiveRate": 70.9},
  {"horizon": 6, "group": "P/E 便宜 × 高殖利率", "n": 2948, "median": 3.9, "mean": 8.64, "bench": 7.19, "winRate": 44.9, "positiveRate": 60.0},
  {"horizon": 12, "group": "P/E 便宜 × 高殖利率", "n": 2773, "median": 10.92, "mean": 21.68, "bench": 16.63, "winRate": 51.5, "positiveRate": 66.2},
  {"horizon": 24, "group": "P/E 便宜 × 高殖利率", "n": 2472, "median": 32.82, "mean": 56.08, "bench": 61.8, "winRate": 49.5, "positiveRate": 79.5}
]

/** 僅含 P/E 便宜 × 高殖利率 的分產業實績 */
export const YIELD_BY_INDUSTRY: YieldIndustryRow[] = [
  {"industry": "其他電子類", "n": 56, "median": 29.81, "winRate": 62.5, "peer": 7.1, "excess": 22.71},
  {"industry": "光電業", "n": 110, "median": 24.55, "winRate": 59.09, "peer": 3.81, "excess": 20.75},
  {"industry": "半導體業", "n": 170, "median": 27.79, "winRate": 64.71, "peer": 8.21, "excess": 19.58},
  {"industry": "電子工業", "n": 387, "median": 21.18, "winRate": 62.27, "peer": 7.27, "excess": 13.91},
  {"industry": "電子通路業", "n": 120, "median": 23.03, "winRate": 60.83, "peer": 9.54, "excess": 13.49},
  {"industry": "通信網路業", "n": 36, "median": 18.13, "winRate": 66.67, "peer": 5.24, "excess": 12.89},
  {"industry": "航運業", "n": 115, "median": 17.93, "winRate": 51.3, "peer": 5.73, "excess": 12.21},
  {"industry": "其他", "n": 117, "median": 8.51, "winRate": 50.43, "peer": 1.92, "excess": 6.59},
  {"industry": "資訊服務業", "n": 38, "median": 16.79, "winRate": 65.79, "peer": 10.82, "excess": 5.97},
  {"industry": "居家生活類", "n": 49, "median": 6.49, "winRate": 55.1, "peer": 1.05, "excess": 5.44},
  {"industry": "生技醫療業", "n": 125, "median": 2.61, "winRate": 44.0, "peer": -2.53, "excess": 5.14},
  {"industry": "居家生活", "n": 41, "median": 8.6, "winRate": 36.59, "peer": 3.83, "excess": 4.77},
  {"industry": "電子零組件業", "n": 292, "median": 12.54, "winRate": 55.82, "peer": 8.11, "excess": 4.43},
  {"industry": "文化創意業", "n": 44, "median": 2.17, "winRate": 52.27, "peer": -1.39, "excess": 3.57},
  {"industry": "食品工業", "n": 36, "median": 7.84, "winRate": 41.67, "peer": 5.16, "excess": 2.68},
  {"industry": "紡織纖維", "n": 47, "median": 2.9, "winRate": 25.53, "peer": 0.85, "excess": 2.06},
  {"industry": "鋼鐵工業", "n": 120, "median": 3.98, "winRate": 36.67, "peer": 2.85, "excess": 1.13},
  {"industry": "建材營造", "n": 201, "median": 9.17, "winRate": 53.23, "peer": 8.67, "excess": 0.5},
  {"industry": "運動休閒", "n": 32, "median": -2.49, "winRate": 46.88, "peer": -0.66, "excess": -1.83},
  {"industry": "塑膠工業", "n": 33, "median": -3.16, "winRate": 21.21, "peer": -0.7, "excess": -2.46},
  {"industry": "電機機械", "n": 98, "median": -1.06, "winRate": 18.37, "peer": 2.84, "excess": -3.9},
  {"industry": "電腦及週邊設備業", "n": 214, "median": 3.27, "winRate": 49.07, "peer": 7.17, "excess": -3.9},
  {"industry": "運動休閒類", "n": 36, "median": -1.55, "winRate": 5.56, "peer": 2.93, "excess": -4.48}
]
