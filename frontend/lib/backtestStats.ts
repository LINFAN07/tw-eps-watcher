// 由 scripts/backtest_valuation.py 產生，請勿手動編輯。
// 重跑回測後此檔會被覆寫；判讀邏輯寫在 lib/backtest.ts。

export interface OverallRow {
  horizon: number; group: string; n: number
  median: number; mean: number; bench: number; winRate: number; positiveRate: number
}

export interface IndustryRow {
  model: string; industry: string; n: number
  median: number; winRate: number; peer: number; excess: number
}

/** 回測期間取自資料本身的第一與最後一個月末交易日 */
export const BACKTEST_PERIOD = { from: '2016-07-29', to: '2026-07-21', months: 121 }

/** 持有 12 個月的分產業結果；其餘持有期見 OVERALL */
export const INDUSTRY_HORIZON = 12

export const OVERALL: OverallRow[] = [
  {"horizon": 6, "group": "全市場等權（對照）", "n": 220498, "median": 1.41, "mean": 9.25, "bench": 6.96, "winRate": 41.2, "positiveRate": 53.2},
  {"horizon": 12, "group": "全市場等權（對照）", "n": 206589, "median": 4.28, "mean": 19.15, "bench": 13.89, "winRate": 46.2, "positiveRate": 56.5},
  {"horizon": 24, "group": "全市場等權（對照）", "n": 180011, "median": 14.16, "mean": 39.06, "bench": 16.75, "winRate": 48.7, "positiveRate": 63.5},
  {"horizon": 6, "group": "P/E 便宜", "n": 15391, "median": 2.58, "mean": 8.56, "bench": 7.12, "winRate": 42.0, "positiveRate": 55.8},
  {"horizon": 12, "group": "P/E 便宜", "n": 14664, "median": 7.22, "mean": 20.84, "bench": 20.46, "winRate": 45.8, "positiveRate": 60.8},
  {"horizon": 24, "group": "P/E 便宜", "n": 13101, "median": 22.29, "mean": 50.08, "bench": 57.46, "winRate": 45.2, "positiveRate": 70.7},
  {"horizon": 6, "group": "P/B 便宜", "n": 32678, "median": 2.03, "mean": 10.12, "bench": 12.79, "winRate": 39.0, "positiveRate": 54.4},
  {"horizon": 12, "group": "P/B 便宜", "n": 29772, "median": 6.9, "mean": 25.75, "bench": 23.04, "winRate": 44.7, "positiveRate": 59.8},
  {"horizon": 24, "group": "P/B 便宜", "n": 24507, "median": 22.78, "mean": 54.19, "bench": 59.56, "winRate": 46.2, "positiveRate": 69.6}
]

export const BY_INDUSTRY: IndustryRow[] = [
  {"model": "P/B", "industry": "半導體業", "n": 1800, "median": 21.98, "winRate": 56.94, "peer": 8.42, "excess": 13.55},
  {"model": "P/B", "industry": "電子零組件業", "n": 2351, "median": 21.41, "winRate": 50.11, "peer": 8.1, "excess": 13.31},
  {"model": "P/B", "industry": "電腦及週邊設備業", "n": 1074, "median": 18.45, "winRate": 48.88, "peer": 7.12, "excess": 11.33},
  {"model": "P/B", "industry": "光電業", "n": 950, "median": 14.2, "winRate": 43.68, "peer": 3.75, "excess": 10.45},
  {"model": "P/B", "industry": "金融業", "n": 88, "median": 18.02, "winRate": 73.86, "peer": 7.61, "excess": 10.41},
  {"model": "P/B", "industry": "其他電子類", "n": 598, "median": 17.59, "winRate": 45.15, "peer": 7.27, "excess": 10.32},
  {"model": "P/B", "industry": "玻璃陶瓷", "n": 69, "median": 13.31, "winRate": 26.09, "peer": 3.36, "excess": 9.95},
  {"model": "P/B", "industry": "電子工業", "n": 2779, "median": 15.8, "winRate": 48.43, "peer": 7.25, "excess": 8.55},
  {"model": "P/B", "industry": "航運業", "n": 397, "median": 13.79, "winRate": 42.57, "peer": 5.56, "excess": 8.23},
  {"model": "P/B", "industry": "綠能環保類", "n": 182, "median": 12.76, "winRate": 57.69, "peer": 5.25, "excess": 7.51},
  {"model": "P/B", "industry": "通信網路業", "n": 781, "median": 12.14, "winRate": 45.45, "peer": 5.25, "excess": 6.89},
  {"model": "P/B", "industry": "電子通路業", "n": 381, "median": 15.18, "winRate": 49.61, "peer": 9.37, "excess": 5.81},
  {"model": "P/B", "industry": "居家生活", "n": 204, "median": 8.95, "winRate": 46.57, "peer": 3.8, "excess": 5.15},
  {"model": "P/B", "industry": "鋼鐵工業", "n": 678, "median": 7.16, "winRate": 38.05, "peer": 2.76, "excess": 4.4},
  {"model": "P/B", "industry": "造紙工業", "n": 84, "median": 3.65, "winRate": 42.86, "peer": -0.1, "excess": 3.75},
  {"model": "P/B", "industry": "化學工業", "n": 395, "median": 6.13, "winRate": 40.25, "peer": 2.64, "excess": 3.49},
  {"model": "P/B", "industry": "汽車工業", "n": 982, "median": 0.84, "winRate": 39.71, "peer": -2.33, "excess": 3.17},
  {"model": "P/B", "industry": "生技醫療業", "n": 3880, "median": 0.11, "winRate": 48.74, "peer": -2.61, "excess": 2.72},
  {"model": "P/B", "industry": "化學生技醫療", "n": 617, "median": 6.16, "winRate": 40.84, "peer": 3.67, "excess": 2.5},
  {"model": "P/B", "industry": "觀光餐旅", "n": 866, "median": 0.63, "winRate": 43.53, "peer": -1.48, "excess": 2.11},
  {"model": "P/B", "industry": "塑膠工業", "n": 578, "median": 1.41, "winRate": 40.48, "peer": -0.7, "excess": 2.1},
  {"model": "P/B", "industry": "建材營造", "n": 845, "median": 10.52, "winRate": 47.1, "peer": 8.58, "excess": 1.95},
  {"model": "P/B", "industry": "居家生活類", "n": 322, "median": 2.5, "winRate": 47.2, "peer": 0.82, "excess": 1.67},
  {"model": "P/B", "industry": "運動休閒", "n": 286, "median": 0.85, "winRate": 44.41, "peer": -0.71, "excess": 1.56},
  {"model": "P/B", "industry": "電機機械", "n": 2133, "median": 3.69, "winRate": 37.55, "peer": 2.74, "excess": 0.95},
  {"model": "P/B", "industry": "資訊服務業", "n": 255, "median": 11.38, "winRate": 48.63, "peer": 10.44, "excess": 0.94},
  {"model": "P/B", "industry": "水泥工業", "n": 75, "median": 5.76, "winRate": 28.0, "peer": 4.95, "excess": 0.82},
  {"model": "P/B", "industry": "紡織纖維", "n": 883, "median": 1.01, "winRate": 38.17, "peer": 0.81, "excess": 0.2},
  {"model": "P/B", "industry": "電器電纜", "n": 106, "median": 8.91, "winRate": 38.68, "peer": 8.83, "excess": 0.07},
  {"model": "P/B", "industry": "文化創意業", "n": 545, "median": -1.52, "winRate": 45.69, "peer": -1.54, "excess": 0.02},
  {"model": "P/B", "industry": "金融保險", "n": 344, "median": 11.3, "winRate": 38.08, "peer": 11.79, "excess": -0.49},
  {"model": "P/B", "industry": "貿易百貨", "n": 401, "median": -2.67, "winRate": 29.43, "peer": -1.51, "excess": -1.16},
  {"model": "P/B", "industry": "其他", "n": 1777, "median": 0.0, "winRate": 33.26, "peer": 1.82, "excess": -1.82},
  {"model": "P/B", "industry": "橡膠工業", "n": 233, "median": -2.8, "winRate": 31.76, "peer": 0.38, "excess": -3.18},
  {"model": "P/B", "industry": "數位雲端類", "n": 243, "median": -3.17, "winRate": 45.27, "peer": 0.34, "excess": -3.51},
  {"model": "P/B", "industry": "食品工業", "n": 498, "median": 1.51, "winRate": 36.55, "peer": 5.08, "excess": -3.57},
  {"model": "P/B", "industry": "油電燃氣業", "n": 120, "median": 1.65, "winRate": 52.5, "peer": 6.77, "excess": -5.12},
  {"model": "P/B", "industry": "農業科技業", "n": 83, "median": -3.47, "winRate": 39.76, "peer": 1.89, "excess": -5.36},
  {"model": "P/B", "industry": "綠能環保", "n": 412, "median": -6.21, "winRate": 45.87, "peer": -0.28, "excess": -5.92},
  {"model": "P/B", "industry": "運動休閒類", "n": 140, "median": -3.41, "winRate": 50.0, "peer": 2.59, "excess": -6.0},
  {"model": "P/B", "industry": "數位雲端", "n": 102, "median": -10.1, "winRate": 54.9, "peer": -4.09, "excess": -6.01},
  {"model": "P/B", "industry": "其他電子業", "n": 228, "median": 0.55, "winRate": 43.42, "peer": 8.02, "excess": -7.47},
  {"model": "P/E", "industry": "居家生活類", "n": 165, "median": 22.51, "winRate": 58.79, "peer": 0.82, "excess": 21.69},
  {"model": "P/E", "industry": "其他電子業", "n": 144, "median": 19.06, "winRate": 50.0, "peer": 8.02, "excess": 11.04},
  {"model": "P/E", "industry": "光電業", "n": 465, "median": 14.61, "winRate": 46.02, "peer": 3.75, "excess": 10.86},
  {"model": "P/E", "industry": "其他電子類", "n": 287, "median": 16.79, "winRate": 46.69, "peer": 7.27, "excess": 9.52},
  {"model": "P/E", "industry": "半導體業", "n": 934, "median": 16.06, "winRate": 49.89, "peer": 8.42, "excess": 7.64},
  {"model": "P/E", "industry": "通信網路業", "n": 319, "median": 12.8, "winRate": 52.35, "peer": 5.25, "excess": 7.55},
  {"model": "P/E", "industry": "電子通路業", "n": 354, "median": 16.28, "winRate": 60.17, "peer": 9.37, "excess": 6.91},
  {"model": "P/E", "industry": "水泥工業", "n": 67, "median": 11.83, "winRate": 25.37, "peer": 4.95, "excess": 6.88},
  {"model": "P/E", "industry": "居家生活", "n": 93, "median": 10.15, "winRate": 37.63, "peer": 3.8, "excess": 6.35},
  {"model": "P/E", "industry": "生技醫療業", "n": 1208, "median": 3.72, "winRate": 44.37, "peer": -2.61, "excess": 6.33},
  {"model": "P/E", "industry": "電子工業", "n": 1573, "median": 13.43, "winRate": 48.38, "peer": 7.25, "excess": 6.18},
  {"model": "P/E", "industry": "航運業", "n": 400, "median": 11.41, "winRate": 45.75, "peer": 5.56, "excess": 5.85},
  {"model": "P/E", "industry": "汽車工業", "n": 224, "median": 3.48, "winRate": 46.88, "peer": -2.33, "excess": 5.81},
  {"model": "P/E", "industry": "食品工業", "n": 216, "median": 10.1, "winRate": 50.93, "peer": 5.08, "excess": 5.02},
  {"model": "P/E", "industry": "文化創意業", "n": 167, "median": 2.94, "winRate": 48.5, "peer": -1.54, "excess": 4.48},
  {"model": "P/E", "industry": "電腦及週邊設備業", "n": 886, "median": 10.54, "winRate": 50.9, "peer": 7.12, "excess": 3.42},
  {"model": "P/E", "industry": "電子零組件業", "n": 1571, "median": 11.49, "winRate": 46.28, "peer": 8.1, "excess": 3.39},
  {"model": "P/E", "industry": "電機機械", "n": 637, "median": 5.95, "winRate": 38.78, "peer": 2.74, "excess": 3.21},
  {"model": "P/E", "industry": "資訊服務業", "n": 238, "median": 12.97, "winRate": 58.4, "peer": 10.44, "excess": 2.53},
  {"model": "P/E", "industry": "化學生技醫療", "n": 341, "median": 5.79, "winRate": 45.16, "peer": 3.67, "excess": 2.12},
  {"model": "P/E", "industry": "鋼鐵工業", "n": 517, "median": 4.22, "winRate": 43.33, "peer": 2.76, "excess": 1.46},
  {"model": "P/E", "industry": "運動休閒", "n": 213, "median": 0.22, "winRate": 29.58, "peer": -0.71, "excess": 0.93},
  {"model": "P/E", "industry": "電器電纜", "n": 123, "median": 9.44, "winRate": 54.47, "peer": 8.83, "excess": 0.61},
  {"model": "P/E", "industry": "化學工業", "n": 192, "median": 3.23, "winRate": 29.69, "peer": 2.64, "excess": 0.58},
  {"model": "P/E", "industry": "觀光餐旅", "n": 241, "median": -1.31, "winRate": 45.23, "peer": -1.48, "excess": 0.17},
  {"model": "P/E", "industry": "綠能環保類", "n": 97, "median": 4.24, "winRate": 60.82, "peer": 5.25, "excess": -1.01},
  {"model": "P/E", "industry": "貿易百貨", "n": 115, "median": -2.59, "winRate": 35.65, "peer": -1.51, "excess": -1.08},
  {"model": "P/E", "industry": "金融保險", "n": 223, "median": 10.31, "winRate": 40.36, "peer": 11.79, "excess": -1.48},
  {"model": "P/E", "industry": "建材營造", "n": 654, "median": 6.67, "winRate": 51.99, "peer": 8.58, "excess": -1.91},
  {"model": "P/E", "industry": "紡織纖維", "n": 352, "median": -1.32, "winRate": 29.55, "peer": 0.81, "excess": -2.12},
  {"model": "P/E", "industry": "農業科技業", "n": 41, "median": -0.52, "winRate": 21.95, "peer": 1.89, "excess": -2.41},
  {"model": "P/E", "industry": "其他", "n": 726, "median": -0.87, "winRate": 41.05, "peer": 1.82, "excess": -2.69},
  {"model": "P/E", "industry": "運動休閒類", "n": 132, "median": -1.93, "winRate": 24.24, "peer": 2.59, "excess": -4.52},
  {"model": "P/E", "industry": "油電燃氣業", "n": 57, "median": 1.82, "winRate": 56.14, "peer": 6.77, "excess": -4.95},
  {"model": "P/E", "industry": "橡膠工業", "n": 147, "median": -5.48, "winRate": 31.29, "peer": 0.38, "excess": -5.86},
  {"model": "P/E", "industry": "塑膠工業", "n": 170, "median": -6.78, "winRate": 40.59, "peer": -0.7, "excess": -6.09},
  {"model": "P/E", "industry": "綠能環保", "n": 161, "median": -7.47, "winRate": 30.43, "peer": -0.28, "excess": -7.19},
  {"model": "P/E", "industry": "數位雲端類", "n": 76, "median": -8.13, "winRate": 52.63, "peer": 0.34, "excess": -8.47},
  {"model": "P/E", "industry": "金融業", "n": 85, "median": -0.86, "winRate": 58.82, "peer": 7.61, "excess": -8.47}
]
