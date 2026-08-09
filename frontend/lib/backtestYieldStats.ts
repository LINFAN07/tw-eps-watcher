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
export const YIELD_BACKTEST_PERIOD = { from: '2016-07-29', to: '2026-08-07', months: 122 }

/** 分產業結果的持有期（月） */
export const YIELD_HORIZON = 12

export const YIELD_OVERALL: YieldOverallRow[] = [
  {"horizon": 6, "group": "全市場等權（對照）", "n": 215480, "median": 1.49, "mean": 9.39, "bench": 6.93, "winRate": 41.3, "positiveRate": 53.4},
  {"horizon": 12, "group": "全市場等權（對照）", "n": 202173, "median": 4.47, "mean": 19.53, "bench": 13.86, "winRate": 46.4, "positiveRate": 56.8},
  {"horizon": 24, "group": "全市場等權（對照）", "n": 176747, "median": 14.48, "mean": 39.76, "bench": 15.57, "winRate": 49.6, "positiveRate": 63.8},
  {"horizon": 6, "group": "P/E 便宜", "n": 14147, "median": 3.04, "mean": 8.93, "bench": 6.51, "winRate": 43.8, "positiveRate": 57.3},
  {"horizon": 12, "group": "P/E 便宜", "n": 13406, "median": 8.01, "mean": 21.54, "bench": 16.63, "winRate": 49.1, "positiveRate": 62.0},
  {"horizon": 24, "group": "P/E 便宜", "n": 11696, "median": 23.48, "mean": 50.91, "bench": 42.65, "winRate": 49.3, "positiveRate": 71.2},
  {"horizon": 6, "group": "P/E 便宜 × 高殖利率", "n": 2836, "median": 5.16, "mean": 9.14, "bench": 7.19, "winRate": 46.9, "positiveRate": 62.6},
  {"horizon": 12, "group": "P/E 便宜 × 高殖利率", "n": 2668, "median": 12.42, "mean": 21.91, "bench": 16.63, "winRate": 54.2, "positiveRate": 68.4},
  {"horizon": 24, "group": "P/E 便宜 × 高殖利率", "n": 2345, "median": 35.38, "mean": 57.36, "bench": 55.91, "winRate": 53.8, "positiveRate": 80.4}
]

/** 僅含 P/E 便宜 × 高殖利率 的分產業實績 */
export const YIELD_BY_INDUSTRY: YieldIndustryRow[] = [
  {"industry": "文化創意業", "n": 32, "median": 23.02, "winRate": 68.75, "peer": -0.65, "excess": 23.67},
  {"industry": "半導體業", "n": 320, "median": 31.86, "winRate": 64.38, "peer": 9.61, "excess": 22.25},
  {"industry": "其他電子類", "n": 56, "median": 26.44, "winRate": 60.71, "peer": 7.46, "excess": 18.98},
  {"industry": "綠能環保", "n": 33, "median": 16.59, "winRate": 36.36, "peer": -0.53, "excess": 17.12},
  {"industry": "光電業", "n": 139, "median": 20.07, "winRate": 59.71, "peer": 4.28, "excess": 15.79},
  {"industry": "其他電子業", "n": 45, "median": 22.49, "winRate": 60.0, "peer": 8.24, "excess": 14.25},
  {"industry": "航運業", "n": 96, "median": 19.39, "winRate": 51.04, "peer": 5.68, "excess": 13.71},
  {"industry": "電子零組件業", "n": 294, "median": 20.86, "winRate": 61.56, "peer": 8.24, "excess": 12.62},
  {"industry": "電子通路業", "n": 113, "median": 20.92, "winRate": 55.75, "peer": 9.99, "excess": 10.93},
  {"industry": "通信網路業", "n": 65, "median": 15.54, "winRate": 80.0, "peer": 4.74, "excess": 10.8},
  {"industry": "居家生活類", "n": 36, "median": 9.53, "winRate": 61.11, "peer": 0.82, "excess": 8.7},
  {"industry": "汽車工業", "n": 34, "median": 6.19, "winRate": 58.82, "peer": -2.04, "excess": 8.24},
  {"industry": "居家生活", "n": 30, "median": 11.46, "winRate": 26.67, "peer": 3.69, "excess": 7.77},
  {"industry": "電機機械", "n": 90, "median": 9.9, "winRate": 22.22, "peer": 2.89, "excess": 7.02},
  {"industry": "觀光餐旅", "n": 31, "median": 4.72, "winRate": 64.52, "peer": -1.37, "excess": 6.08},
  {"industry": "資訊服務業", "n": 84, "median": 15.88, "winRate": 66.67, "peer": 11.89, "excess": 3.99},
  {"industry": "其他", "n": 118, "median": 6.13, "winRate": 57.63, "peer": 2.25, "excess": 3.89},
  {"industry": "鋼鐵工業", "n": 112, "median": 6.28, "winRate": 41.96, "peer": 2.83, "excess": 3.45},
  {"industry": "生技醫療業", "n": 132, "median": 0.93, "winRate": 48.48, "peer": -2.43, "excess": 3.37},
  {"industry": "建材營造", "n": 218, "median": 11.62, "winRate": 58.72, "peer": 8.67, "excess": 2.95},
  {"industry": "運動休閒類", "n": 30, "median": 4.15, "winRate": 10.0, "peer": 2.1, "excess": 2.05},
  {"industry": "運動休閒", "n": 32, "median": 0.15, "winRate": 53.12, "peer": -0.81, "excess": 0.96},
  {"industry": "食品工業", "n": 34, "median": 5.24, "winRate": 41.18, "peer": 5.24, "excess": 0.0},
  {"industry": "電腦及週邊設備業", "n": 252, "median": 5.14, "winRate": 55.56, "peer": 6.65, "excess": -1.51},
  {"industry": "紡織纖維", "n": 35, "median": -4.64, "winRate": 17.14, "peer": 0.81, "excess": -5.45},
  {"industry": "金融保險", "n": 35, "median": 0.38, "winRate": 51.43, "peer": 12.31, "excess": -11.93}
]
