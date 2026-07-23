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
  {"horizon": 6, "group": "全市場等權（對照）", "n": 220497, "median": 1.44, "mean": 9.3, "bench": 6.93, "winRate": 41.3, "positiveRate": 53.2},
  {"horizon": 12, "group": "全市場等權（對照）", "n": 206590, "median": 4.36, "mean": 19.24, "bench": 13.86, "winRate": 46.3, "positiveRate": 56.6},
  {"horizon": 24, "group": "全市場等權（對照）", "n": 180015, "median": 14.29, "mean": 39.26, "bench": 16.86, "winRate": 48.8, "positiveRate": 63.6},
  {"horizon": 6, "group": "P/E 便宜", "n": 15368, "median": 2.61, "mean": 8.61, "bench": 7.19, "winRate": 42.1, "positiveRate": 56.0},
  {"horizon": 12, "group": "P/E 便宜", "n": 14648, "median": 7.26, "mean": 20.85, "bench": 20.63, "winRate": 45.8, "positiveRate": 60.9},
  {"horizon": 24, "group": "P/E 便宜", "n": 13105, "median": 22.42, "mean": 50.23, "bench": 56.7, "winRate": 45.3, "positiveRate": 70.8},
  {"horizon": 6, "group": "P/E 便宜 × 高殖利率", "n": 2954, "median": 3.95, "mean": 8.71, "bench": 7.19, "winRate": 45.2, "positiveRate": 60.2},
  {"horizon": 12, "group": "P/E 便宜 × 高殖利率", "n": 2780, "median": 10.93, "mean": 21.9, "bench": 16.63, "winRate": 51.7, "positiveRate": 66.2},
  {"horizon": 24, "group": "P/E 便宜 × 高殖利率", "n": 2480, "median": 32.89, "mean": 56.27, "bench": 61.8, "winRate": 50.2, "positiveRate": 79.3}
]

/** 僅含 P/E 便宜 × 高殖利率 的分產業實績 */
export const YIELD_BY_INDUSTRY: YieldIndustryRow[] = [
  {"industry": "其他電子類", "n": 57, "median": 29.4, "winRate": 61.4, "peer": 7.33, "excess": 22.07},
  {"industry": "光電業", "n": 111, "median": 23.97, "winRate": 58.56, "peer": 3.79, "excess": 20.17},
  {"industry": "半導體業", "n": 168, "median": 26.96, "winRate": 64.29, "peer": 8.43, "excess": 18.53},
  {"industry": "電子工業", "n": 382, "median": 21.34, "winRate": 62.04, "peer": 7.27, "excess": 14.07},
  {"industry": "電子通路業", "n": 120, "median": 23.03, "winRate": 61.67, "peer": 9.52, "excess": 13.51},
  {"industry": "通信網路業", "n": 34, "median": 18.13, "winRate": 61.76, "peer": 5.27, "excess": 12.86},
  {"industry": "航運業", "n": 110, "median": 18.45, "winRate": 51.82, "peer": 5.72, "excess": 12.73},
  {"industry": "居家生活類", "n": 52, "median": 9.53, "winRate": 55.77, "peer": 0.85, "excess": 8.68},
  {"industry": "其他", "n": 121, "median": 8.59, "winRate": 51.24, "peer": 1.91, "excess": 6.68},
  {"industry": "資訊服務業", "n": 39, "median": 16.27, "winRate": 64.1, "peer": 10.44, "excess": 5.83},
  {"industry": "生技醫療業", "n": 125, "median": 3.09, "winRate": 43.2, "peer": -2.59, "excess": 5.68},
  {"industry": "電子零組件業", "n": 295, "median": 13.34, "winRate": 57.29, "peer": 8.19, "excess": 5.14},
  {"industry": "居家生活", "n": 41, "median": 8.6, "winRate": 36.59, "peer": 3.83, "excess": 4.77},
  {"industry": "文化創意業", "n": 47, "median": 1.29, "winRate": 55.32, "peer": -1.59, "excess": 2.88},
  {"industry": "食品工業", "n": 34, "median": 7.3, "winRate": 41.18, "peer": 5.14, "excess": 2.16},
  {"industry": "鋼鐵工業", "n": 122, "median": 3.52, "winRate": 36.07, "peer": 2.83, "excess": 0.7},
  {"industry": "建材營造", "n": 199, "median": 9.15, "winRate": 55.78, "peer": 8.62, "excess": 0.53},
  {"industry": "紡織纖維", "n": 46, "median": 1.33, "winRate": 23.91, "peer": 0.83, "excess": 0.5},
  {"industry": "運動休閒", "n": 31, "median": -2.31, "winRate": 48.39, "peer": -0.66, "excess": -1.65},
  {"industry": "塑膠工業", "n": 33, "median": -3.16, "winRate": 21.21, "peer": -0.71, "excess": -2.46},
  {"industry": "電腦及週邊設備業", "n": 219, "median": 3.21, "winRate": 47.95, "peer": 7.16, "excess": -3.96},
  {"industry": "運動休閒類", "n": 36, "median": -1.55, "winRate": 5.56, "peer": 2.59, "excess": -4.14},
  {"industry": "電機機械", "n": 101, "median": -2.48, "winRate": 17.82, "peer": 2.8, "excess": -5.28}
]
