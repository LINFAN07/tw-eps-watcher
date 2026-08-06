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
export const YIELD_BACKTEST_PERIOD = { from: '2016-07-29', to: '2026-08-06', months: 122 }

/** 分產業結果的持有期（月） */
export const YIELD_HORIZON = 12

export const YIELD_OVERALL: YieldOverallRow[] = [
  {"horizon": 6, "group": "全市場等權（對照）", "n": 222755, "median": 1.39, "mean": 9.2, "bench": 6.93, "winRate": 41.0, "positiveRate": 53.1},
  {"horizon": 12, "group": "全市場等權（對照）", "n": 208781, "median": 4.25, "mean": 19.16, "bench": 13.86, "winRate": 45.9, "positiveRate": 56.4},
  {"horizon": 24, "group": "全市場等權（對照）", "n": 182122, "median": 13.99, "mean": 38.99, "bench": 15.57, "winRate": 49.2, "positiveRate": 63.3},
  {"horizon": 6, "group": "P/E 便宜", "n": 14419, "median": 2.94, "mean": 8.75, "bench": 6.51, "winRate": 43.5, "positiveRate": 57.0},
  {"horizon": 12, "group": "P/E 便宜", "n": 13663, "median": 7.78, "mean": 21.18, "bench": 16.63, "winRate": 48.6, "positiveRate": 61.6},
  {"horizon": 24, "group": "P/E 便宜", "n": 11831, "median": 23.13, "mean": 50.39, "bench": 42.65, "winRate": 49.2, "positiveRate": 70.9},
  {"horizon": 6, "group": "P/E 便宜 × 高殖利率", "n": 2892, "median": 5.01, "mean": 8.88, "bench": 7.19, "winRate": 46.3, "positiveRate": 62.1},
  {"horizon": 12, "group": "P/E 便宜 × 高殖利率", "n": 2724, "median": 12.04, "mean": 21.35, "bench": 16.63, "winRate": 53.5, "positiveRate": 67.7},
  {"horizon": 24, "group": "P/E 便宜 × 高殖利率", "n": 2384, "median": 34.94, "mean": 57.14, "bench": 55.91, "winRate": 53.9, "positiveRate": 80.3}
]

/** 僅含 P/E 便宜 × 高殖利率 的分產業實績 */
export const YIELD_BY_INDUSTRY: YieldIndustryRow[] = [
  {"industry": "光電業", "n": 98, "median": 26.04, "winRate": 58.16, "peer": 3.69, "excess": 22.35},
  {"industry": "文化創意業", "n": 35, "median": 20.33, "winRate": 62.86, "peer": -1.74, "excess": 22.07},
  {"industry": "半導體業", "n": 167, "median": 27.91, "winRate": 61.68, "peer": 8.64, "excess": 19.26},
  {"industry": "其他電子類", "n": 56, "median": 26.44, "winRate": 60.71, "peer": 7.25, "excess": 19.19},
  {"industry": "綠能環保", "n": 33, "median": 16.59, "winRate": 36.36, "peer": -0.53, "excess": 17.12},
  {"industry": "電子工業", "n": 391, "median": 23.7, "winRate": 64.71, "peer": 7.25, "excess": 16.45},
  {"industry": "航運業", "n": 95, "median": 19.39, "winRate": 51.58, "peer": 5.62, "excess": 13.77},
  {"industry": "通信網路業", "n": 41, "median": 18.04, "winRate": 73.17, "peer": 5.26, "excess": 12.78},
  {"industry": "電子通路業", "n": 99, "median": 20.92, "winRate": 57.58, "peer": 9.5, "excess": 11.42},
  {"industry": "電子零組件業", "n": 273, "median": 17.65, "winRate": 62.64, "peer": 8.23, "excess": 9.43},
  {"industry": "汽車工業", "n": 34, "median": 6.19, "winRate": 58.82, "peer": -2.39, "excess": 8.58},
  {"industry": "居家生活", "n": 30, "median": 11.46, "winRate": 26.67, "peer": 3.69, "excess": 7.77},
  {"industry": "電機機械", "n": 91, "median": 10.12, "winRate": 21.98, "peer": 2.72, "excess": 7.41},
  {"industry": "居家生活類", "n": 38, "median": 7.24, "winRate": 57.89, "peer": 0.69, "excess": 6.55},
  {"industry": "資訊服務業", "n": 42, "median": 15.88, "winRate": 57.14, "peer": 10.2, "excess": 5.68},
  {"industry": "觀光餐旅", "n": 32, "median": 3.09, "winRate": 62.5, "peer": -1.74, "excess": 4.83},
  {"industry": "其他", "n": 122, "median": 6.3, "winRate": 56.56, "peer": 1.85, "excess": 4.45},
  {"industry": "生技醫療業", "n": 125, "median": 1.14, "winRate": 44.8, "peer": -2.81, "excess": 3.96},
  {"industry": "建材營造", "n": 218, "median": 11.62, "winRate": 58.72, "peer": 8.45, "excess": 3.17},
  {"industry": "鋼鐵工業", "n": 114, "median": 5.57, "winRate": 41.23, "peer": 2.73, "excess": 2.84},
  {"industry": "運動休閒", "n": 32, "median": 0.15, "winRate": 53.12, "peer": -0.78, "excess": 0.93},
  {"industry": "食品工業", "n": 34, "median": 5.24, "winRate": 41.18, "peer": 4.94, "excess": 0.31},
  {"industry": "運動休閒類", "n": 39, "median": 1.11, "winRate": 7.69, "peer": 2.33, "excess": -1.22},
  {"industry": "電腦及週邊設備業", "n": 213, "median": 4.66, "winRate": 51.64, "peer": 7.11, "excess": -2.45},
  {"industry": "紡織纖維", "n": 36, "median": -5.02, "winRate": 16.67, "peer": 0.77, "excess": -5.79},
  {"industry": "金融保險", "n": 35, "median": 0.38, "winRate": 51.43, "peer": 12.05, "excess": -11.67}
]
