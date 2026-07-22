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
export const BACKTEST_PERIOD = { from: '2016-07-29', to: '2026-07-22', months: 121 }

/** 持有 12 個月的分產業結果；其餘持有期見 OVERALL */
export const INDUSTRY_HORIZON = 12

export const OVERALL: OverallRow[] = [
  {"horizon": 6, "group": "全市場等權（對照）", "n": 219633, "median": 1.46, "mean": 9.29, "bench": 6.92, "winRate": 41.4, "positiveRate": 53.3},
  {"horizon": 12, "group": "全市場等權（對照）", "n": 205731, "median": 4.36, "mean": 19.2, "bench": 13.86, "winRate": 46.5, "positiveRate": 56.6},
  {"horizon": 24, "group": "全市場等權（對照）", "n": 179171, "median": 14.38, "mean": 39.33, "bench": 16.86, "winRate": 48.7, "positiveRate": 63.7},
  {"horizon": 6, "group": "P/E 便宜", "n": 15302, "median": 2.66, "mean": 8.64, "bench": 7.19, "winRate": 42.3, "positiveRate": 56.1},
  {"horizon": 12, "group": "P/E 便宜", "n": 14570, "median": 7.3, "mean": 20.92, "bench": 16.63, "winRate": 46.1, "positiveRate": 61.1},
  {"horizon": 24, "group": "P/E 便宜", "n": 13054, "median": 22.58, "mean": 50.38, "bench": 56.7, "winRate": 45.3, "positiveRate": 71.0},
  {"horizon": 6, "group": "P/B 便宜", "n": 32192, "median": 2.12, "mean": 10.21, "bench": 12.74, "winRate": 39.2, "positiveRate": 54.6},
  {"horizon": 12, "group": "P/B 便宜", "n": 29315, "median": 7.07, "mean": 25.9, "bench": 23.0, "winRate": 45.1, "positiveRate": 60.1},
  {"horizon": 24, "group": "P/B 便宜", "n": 24256, "median": 23.1, "mean": 54.4, "bench": 58.79, "winRate": 46.2, "positiveRate": 70.0}
]

export const BY_INDUSTRY: IndustryRow[] = [
  {"model": "P/B", "industry": "半導體業", "n": 1747, "median": 21.76, "winRate": 57.3, "peer": 8.21, "excess": 13.55},
  {"model": "P/B", "industry": "電子零組件業", "n": 2316, "median": 21.53, "winRate": 50.3, "peer": 8.11, "excess": 13.42},
  {"model": "P/B", "industry": "電腦及週邊設備業", "n": 1067, "median": 18.52, "winRate": 49.3, "peer": 7.17, "excess": 11.35},
  {"model": "P/B", "industry": "光電業", "n": 941, "median": 14.48, "winRate": 44.1, "peer": 3.81, "excess": 10.67},
  {"model": "P/B", "industry": "金融業", "n": 88, "median": 18.02, "winRate": 73.86, "peer": 7.56, "excess": 10.46},
  {"model": "P/B", "industry": "玻璃陶瓷", "n": 69, "median": 13.62, "winRate": 26.09, "peer": 3.3, "excess": 10.31},
  {"model": "P/B", "industry": "其他電子類", "n": 590, "median": 17.35, "winRate": 45.59, "peer": 7.1, "excess": 10.25},
  {"model": "P/B", "industry": "電子工業", "n": 2766, "median": 15.64, "winRate": 48.34, "peer": 7.27, "excess": 8.38},
  {"model": "P/B", "industry": "綠能環保類", "n": 177, "median": 13.14, "winRate": 59.32, "peer": 5.38, "excess": 7.76},
  {"model": "P/B", "industry": "通信網路業", "n": 773, "median": 12.25, "winRate": 45.92, "peer": 5.24, "excess": 7.0},
  {"model": "P/B", "industry": "航運業", "n": 390, "median": 12.17, "winRate": 42.31, "peer": 5.73, "excess": 6.45},
  {"model": "P/B", "industry": "電子通路業", "n": 371, "median": 14.98, "winRate": 49.6, "peer": 9.54, "excess": 5.44},
  {"model": "P/B", "industry": "居家生活", "n": 204, "median": 8.97, "winRate": 47.06, "peer": 3.83, "excess": 5.14},
  {"model": "P/B", "industry": "鋼鐵工業", "n": 662, "median": 7.54, "winRate": 38.67, "peer": 2.85, "excess": 4.69},
  {"model": "P/B", "industry": "造紙工業", "n": 82, "median": 4.2, "winRate": 42.68, "peer": -0.06, "excess": 4.26},
  {"model": "P/B", "industry": "汽車工業", "n": 983, "median": 1.12, "winRate": 39.98, "peer": -2.3, "excess": 3.42},
  {"model": "P/B", "industry": "化學工業", "n": 387, "median": 6.13, "winRate": 40.31, "peer": 2.74, "excess": 3.4},
  {"model": "P/B", "industry": "生技醫療業", "n": 3802, "median": 0.21, "winRate": 49.34, "peer": -2.53, "excess": 2.74},
  {"model": "P/B", "industry": "化學生技醫療", "n": 602, "median": 6.13, "winRate": 41.03, "peer": 3.74, "excess": 2.39},
  {"model": "P/B", "industry": "運動休閒", "n": 285, "median": 1.65, "winRate": 45.26, "peer": -0.66, "excess": 2.31},
  {"model": "P/B", "industry": "塑膠工業", "n": 578, "median": 1.4, "winRate": 40.48, "peer": -0.7, "excess": 2.11},
  {"model": "P/B", "industry": "觀光餐旅", "n": 854, "median": 0.72, "winRate": 44.03, "peer": -1.37, "excess": 2.09},
  {"model": "P/B", "industry": "建材營造", "n": 830, "median": 10.68, "winRate": 47.83, "peer": 8.67, "excess": 2.01},
  {"model": "P/B", "industry": "金融保險", "n": 313, "median": 13.08, "winRate": 36.42, "peer": 11.97, "excess": 1.11},
  {"model": "P/B", "industry": "電機機械", "n": 2119, "median": 3.92, "winRate": 37.71, "peer": 2.84, "excess": 1.09},
  {"model": "P/B", "industry": "水泥工業", "n": 75, "median": 5.76, "winRate": 28.0, "peer": 4.91, "excess": 0.85},
  {"model": "P/B", "industry": "資訊服務業", "n": 253, "median": 11.55, "winRate": 49.41, "peer": 10.82, "excess": 0.72},
  {"model": "P/B", "industry": "居家生活類", "n": 299, "median": 1.41, "winRate": 45.15, "peer": 1.05, "excess": 0.37},
  {"model": "P/B", "industry": "文化創意業", "n": 539, "median": -1.04, "winRate": 46.38, "peer": -1.39, "excess": 0.35},
  {"model": "P/B", "industry": "紡織纖維", "n": 879, "median": 1.2, "winRate": 38.57, "peer": 0.85, "excess": 0.35},
  {"model": "P/B", "industry": "電器電纜", "n": 106, "median": 8.88, "winRate": 38.68, "peer": 8.93, "excess": -0.04},
  {"model": "P/B", "industry": "貿易百貨", "n": 399, "median": -2.91, "winRate": 29.82, "peer": -1.51, "excess": -1.4},
  {"model": "P/B", "industry": "其他", "n": 1740, "median": 0.33, "winRate": 34.02, "peer": 1.92, "excess": -1.59},
  {"model": "P/B", "industry": "數位雲端類", "n": 217, "median": -2.54, "winRate": 49.77, "peer": 0.4, "excess": -2.93},
  {"model": "P/B", "industry": "橡膠工業", "n": 231, "median": -2.48, "winRate": 31.6, "peer": 0.47, "excess": -2.95},
  {"model": "P/B", "industry": "食品工業", "n": 495, "median": 1.58, "winRate": 36.97, "peer": 5.16, "excess": -3.59},
  {"model": "P/B", "industry": "農業科技業", "n": 81, "median": -1.93, "winRate": 40.74, "peer": 1.97, "excess": -3.9},
  {"model": "P/B", "industry": "油電燃氣業", "n": 121, "median": 1.5, "winRate": 52.07, "peer": 6.78, "excess": -5.28},
  {"model": "P/B", "industry": "數位雲端", "n": 102, "median": -9.98, "winRate": 54.9, "peer": -4.11, "excess": -5.86},
  {"model": "P/B", "industry": "綠能環保", "n": 412, "median": -6.23, "winRate": 45.87, "peer": -0.24, "excess": -6.0},
  {"model": "P/B", "industry": "運動休閒類", "n": 136, "median": -3.41, "winRate": 51.47, "peer": 2.93, "excess": -6.34},
  {"model": "P/B", "industry": "其他電子業", "n": 227, "median": 0.53, "winRate": 43.17, "peer": 7.98, "excess": -7.45},
  {"model": "P/E", "industry": "居家生活類", "n": 161, "median": 22.51, "winRate": 59.63, "peer": 1.05, "excess": 21.46},
  {"model": "P/E", "industry": "其他電子業", "n": 146, "median": 18.78, "winRate": 49.32, "peer": 7.98, "excess": 10.79},
  {"model": "P/E", "industry": "光電業", "n": 463, "median": 14.43, "winRate": 46.0, "peer": 3.81, "excess": 10.63},
  {"model": "P/E", "industry": "其他電子類", "n": 284, "median": 15.39, "winRate": 46.83, "peer": 7.1, "excess": 8.29},
  {"model": "P/E", "industry": "通信網路業", "n": 315, "median": 13.31, "winRate": 53.02, "peer": 5.24, "excess": 8.06},
  {"model": "P/E", "industry": "半導體業", "n": 931, "median": 16.2, "winRate": 49.95, "peer": 8.21, "excess": 7.99},
  {"model": "P/E", "industry": "電子通路業", "n": 346, "median": 16.48, "winRate": 60.69, "peer": 9.54, "excess": 6.94},
  {"model": "P/E", "industry": "水泥工業", "n": 67, "median": 11.77, "winRate": 25.37, "peer": 4.91, "excess": 6.85},
  {"model": "P/E", "industry": "生技醫療業", "n": 1193, "median": 3.96, "winRate": 44.84, "peer": -2.53, "excess": 6.49},
  {"model": "P/E", "industry": "居家生活", "n": 93, "median": 10.0, "winRate": 37.63, "peer": 3.83, "excess": 6.17},
  {"model": "P/E", "industry": "汽車工業", "n": 225, "median": 3.73, "winRate": 47.11, "peer": -2.3, "excess": 6.03},
  {"model": "P/E", "industry": "航運業", "n": 397, "median": 11.76, "winRate": 45.09, "peer": 5.73, "excess": 6.03},
  {"model": "P/E", "industry": "電子工業", "n": 1567, "median": 13.06, "winRate": 48.44, "peer": 7.27, "excess": 5.79},
  {"model": "P/E", "industry": "食品工業", "n": 219, "median": 10.04, "winRate": 51.6, "peer": 5.16, "excess": 4.88},
  {"model": "P/E", "industry": "文化創意業", "n": 166, "median": 3.08, "winRate": 48.19, "peer": -1.39, "excess": 4.47},
  {"model": "P/E", "industry": "電子零組件業", "n": 1562, "median": 11.5, "winRate": 46.48, "peer": 8.11, "excess": 3.38},
  {"model": "P/E", "industry": "電腦及週邊設備業", "n": 884, "median": 10.51, "winRate": 51.13, "peer": 7.17, "excess": 3.33},
  {"model": "P/E", "industry": "資訊服務業", "n": 235, "median": 14.13, "winRate": 59.15, "peer": 10.82, "excess": 3.31},
  {"model": "P/E", "industry": "電機機械", "n": 634, "median": 5.76, "winRate": 38.8, "peer": 2.84, "excess": 2.92},
  {"model": "P/E", "industry": "化學生技醫療", "n": 341, "median": 5.68, "winRate": 45.45, "peer": 3.74, "excess": 1.94},
  {"model": "P/E", "industry": "鋼鐵工業", "n": 511, "median": 4.41, "winRate": 43.25, "peer": 2.85, "excess": 1.56},
  {"model": "P/E", "industry": "化學工業", "n": 189, "median": 3.65, "winRate": 29.1, "peer": 2.74, "excess": 0.91},
  {"model": "P/E", "industry": "運動休閒", "n": 211, "median": 0.24, "winRate": 29.38, "peer": -0.66, "excess": 0.9},
  {"model": "P/E", "industry": "電器電纜", "n": 124, "median": 9.55, "winRate": 55.65, "peer": 8.93, "excess": 0.62},
  {"model": "P/E", "industry": "觀光餐旅", "n": 237, "median": -1.31, "winRate": 45.57, "peer": -1.37, "excess": 0.06},
  {"model": "P/E", "industry": "貿易百貨", "n": 114, "median": -2.17, "winRate": 35.09, "peer": -1.51, "excess": -0.66},
  {"model": "P/E", "industry": "綠能環保類", "n": 97, "median": 4.24, "winRate": 60.82, "peer": 5.38, "excess": -1.14},
  {"model": "P/E", "industry": "金融保險", "n": 220, "median": 10.33, "winRate": 41.82, "peer": 11.97, "excess": -1.65},
  {"model": "P/E", "industry": "紡織纖維", "n": 349, "median": -1.29, "winRate": 30.09, "peer": 0.85, "excess": -2.13},
  {"model": "P/E", "industry": "建材營造", "n": 654, "median": 6.46, "winRate": 52.14, "peer": 8.67, "excess": -2.2},
  {"model": "P/E", "industry": "農業科技業", "n": 41, "median": -0.52, "winRate": 21.95, "peer": 1.97, "excess": -2.49},
  {"model": "P/E", "industry": "其他", "n": 720, "median": -0.58, "winRate": 41.81, "peer": 1.92, "excess": -2.5},
  {"model": "P/E", "industry": "油電燃氣業", "n": 56, "median": 1.96, "winRate": 57.14, "peer": 6.78, "excess": -4.83},
  {"model": "P/E", "industry": "運動休閒類", "n": 132, "median": -1.93, "winRate": 24.24, "peer": 2.93, "excess": -4.86},
  {"model": "P/E", "industry": "塑膠工業", "n": 168, "median": -6.44, "winRate": 41.07, "peer": -0.7, "excess": -5.73},
  {"model": "P/E", "industry": "橡膠工業", "n": 147, "median": -5.26, "winRate": 31.97, "peer": 0.47, "excess": -5.74},
  {"model": "P/E", "industry": "綠能環保", "n": 160, "median": -7.28, "winRate": 30.63, "peer": -0.24, "excess": -7.04},
  {"model": "P/E", "industry": "數位雲端類", "n": 73, "median": -7.42, "winRate": 54.79, "peer": 0.4, "excess": -7.81},
  {"model": "P/E", "industry": "金融業", "n": 85, "median": -0.86, "winRate": 58.82, "peer": 7.56, "excess": -8.43}
]
