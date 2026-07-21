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
export const BACKTEST_PERIOD = { from: '2016-06-30', to: '2026-07-20', months: 122 }

/** 持有 12 個月的分產業結果；其餘持有期見 OVERALL */
export const INDUSTRY_HORIZON = 12

export const OVERALL: OverallRow[] = [
  {"horizon": 6, "group": "全市場等權（對照）", "n": 222277, "median": 1.09, "mean": 8.79, "bench": 6.92, "winRate": 40.6, "positiveRate": 52.4},
  {"horizon": 12, "group": "全市場等權（對照）", "n": 208349, "median": 3.65, "mean": 18.27, "bench": 13.46, "winRate": 45.3, "positiveRate": 55.5},
  {"horizon": 24, "group": "全市場等權（對照）", "n": 181741, "median": 12.52, "mean": 36.78, "bench": 16.46, "winRate": 47.3, "positiveRate": 62.1},
  {"horizon": 6, "group": "P/E 便宜", "n": 14546, "median": 2.19, "mean": 7.86, "bench": 7.39, "winRate": 41.2, "positiveRate": 55.1},
  {"horizon": 12, "group": "P/E 便宜", "n": 13917, "median": 6.26, "mean": 20.0, "bench": 17.35, "winRate": 45.0, "positiveRate": 59.3},
  {"horizon": 24, "group": "P/E 便宜", "n": 12535, "median": 20.62, "mean": 46.62, "bench": 59.55, "winRate": 43.8, "positiveRate": 68.7},
  {"horizon": 6, "group": "P/B 便宜", "n": 26703, "median": 2.21, "mean": 10.39, "bench": 11.65, "winRate": 39.2, "positiveRate": 54.8},
  {"horizon": 12, "group": "P/B 便宜", "n": 24357, "median": 7.16, "mean": 27.19, "bench": 23.24, "winRate": 44.2, "positiveRate": 60.1},
  {"horizon": 24, "group": "P/B 便宜", "n": 20152, "median": 23.32, "mean": 55.34, "bench": 61.0, "winRate": 44.1, "positiveRate": 70.4}
]

export const BY_INDUSTRY: IndustryRow[] = [
  {"model": "P/B", "industry": "金融業", "n": 64, "median": 38.62, "winRate": 67.19, "peer": 7.27, "excess": 31.36},
  {"model": "P/B", "industry": "電子零組件業", "n": 1968, "median": 23.92, "winRate": 50.56, "peer": 7.99, "excess": 15.93},
  {"model": "P/B", "industry": "半導體業", "n": 1370, "median": 22.34, "winRate": 55.33, "peer": 7.63, "excess": 14.71},
  {"model": "P/B", "industry": "通信網路業", "n": 513, "median": 18.81, "winRate": 43.27, "peer": 4.99, "excess": 13.82},
  {"model": "P/B", "industry": "光電業", "n": 776, "median": 15.82, "winRate": 45.23, "peer": 3.26, "excess": 12.55},
  {"model": "P/B", "industry": "航運業", "n": 306, "median": 14.48, "winRate": 42.48, "peer": 4.69, "excess": 9.79},
  {"model": "P/B", "industry": "其他電子類", "n": 482, "median": 15.8, "winRate": 45.64, "peer": 6.53, "excess": 9.26},
  {"model": "P/B", "industry": "電腦及週邊設備業", "n": 932, "median": 15.7, "winRate": 46.89, "peer": 6.61, "excess": 9.09},
  {"model": "P/B", "industry": "電子工業", "n": 2498, "median": 15.43, "winRate": 48.04, "peer": 7.17, "excess": 8.26},
  {"model": "P/B", "industry": "綠能環保類", "n": 139, "median": 11.45, "winRate": 53.96, "peer": 3.96, "excess": 7.48},
  {"model": "P/B", "industry": "玻璃陶瓷", "n": 69, "median": 11.05, "winRate": 24.64, "peer": 3.65, "excess": 7.4},
  {"model": "P/B", "industry": "造紙工業", "n": 86, "median": 6.57, "winRate": 39.53, "peer": 0.0, "excess": 6.57},
  {"model": "P/B", "industry": "水泥工業", "n": 38, "median": 10.7, "winRate": 23.68, "peer": 4.47, "excess": 6.23},
  {"model": "P/B", "industry": "居家生活", "n": 188, "median": 9.5, "winRate": 47.34, "peer": 3.51, "excess": 5.99},
  {"model": "P/B", "industry": "運動休閒", "n": 243, "median": 4.74, "winRate": 47.33, "peer": -1.04, "excess": 5.77},
  {"model": "P/B", "industry": "汽車工業", "n": 891, "median": 1.71, "winRate": 40.4, "peer": -2.65, "excess": 4.35},
  {"model": "P/B", "industry": "化學生技醫療", "n": 558, "median": 6.44, "winRate": 42.47, "peer": 2.55, "excess": 3.89},
  {"model": "P/B", "industry": "化學工業", "n": 332, "median": 4.84, "winRate": 34.94, "peer": 1.33, "excess": 3.51},
  {"model": "P/B", "industry": "鋼鐵工業", "n": 469, "median": 5.8, "winRate": 33.69, "peer": 2.35, "excess": 3.45},
  {"model": "P/B", "industry": "塑膠工業", "n": 543, "median": 2.67, "winRate": 43.09, "peer": -0.73, "excess": 3.4},
  {"model": "P/B", "industry": "觀光餐旅", "n": 607, "median": 0.77, "winRate": 43.49, "peer": -2.56, "excess": 3.33},
  {"model": "P/B", "industry": "生技醫療業", "n": 2852, "median": -0.52, "winRate": 49.12, "peer": -3.71, "excess": 3.18},
  {"model": "P/B", "industry": "電子通路業", "n": 303, "median": 12.12, "winRate": 47.85, "peer": 9.25, "excess": 2.87},
  {"model": "P/B", "industry": "金融保險", "n": 223, "median": 12.85, "winRate": 32.74, "peer": 10.05, "excess": 2.8},
  {"model": "P/B", "industry": "文化創意業", "n": 502, "median": -1.68, "winRate": 47.21, "peer": -3.65, "excess": 1.98},
  {"model": "P/B", "industry": "建材營造", "n": 647, "median": 8.97, "winRate": 38.79, "peer": 7.13, "excess": 1.84},
  {"model": "P/B", "industry": "紡織纖維", "n": 749, "median": 2.36, "winRate": 39.92, "peer": 0.65, "excess": 1.71},
  {"model": "P/B", "industry": "居家生活類", "n": 248, "median": 1.41, "winRate": 43.55, "peer": -0.09, "excess": 1.51},
  {"model": "P/B", "industry": "電機機械", "n": 1719, "median": 3.49, "winRate": 38.16, "peer": 2.49, "excess": 1.0},
  {"model": "P/B", "industry": "運動休閒類", "n": 103, "median": 2.96, "winRate": 63.11, "peer": 2.5, "excess": 0.46},
  {"model": "P/B", "industry": "其他", "n": 1544, "median": 0.08, "winRate": 32.12, "peer": 1.39, "excess": -1.31},
  {"model": "P/B", "industry": "橡膠工業", "n": 224, "median": -1.84, "winRate": 30.8, "peer": -0.33, "excess": -1.51},
  {"model": "P/B", "industry": "貿易百貨", "n": 391, "median": -3.32, "winRate": 29.41, "peer": -1.75, "excess": -1.57},
  {"model": "P/B", "industry": "電器電纜", "n": 102, "median": 6.21, "winRate": 43.14, "peer": 8.15, "excess": -1.94},
  {"model": "P/B", "industry": "數位雲端類", "n": 186, "median": -5.44, "winRate": 51.61, "peer": -2.82, "excess": -2.62},
  {"model": "P/B", "industry": "資訊服務業", "n": 188, "median": 6.51, "winRate": 48.94, "peer": 9.22, "excess": -2.71},
  {"model": "P/B", "industry": "農業科技業", "n": 40, "median": -4.46, "winRate": 37.5, "peer": -0.73, "excess": -3.74},
  {"model": "P/B", "industry": "綠能環保", "n": 341, "median": -5.98, "winRate": 45.45, "peer": -1.13, "excess": -4.85},
  {"model": "P/B", "industry": "食品工業", "n": 466, "median": -1.2, "winRate": 33.48, "peer": 3.91, "excess": -5.11},
  {"model": "P/B", "industry": "其他電子業", "n": 254, "median": 3.09, "winRate": 44.09, "peer": 8.27, "excess": -5.18},
  {"model": "P/B", "industry": "數位雲端", "n": 102, "median": -11.81, "winRate": 54.9, "peer": -4.44, "excess": -7.37},
  {"model": "P/B", "industry": "油電燃氣業", "n": 96, "median": -1.67, "winRate": 51.04, "peer": 5.97, "excess": -7.63},
  {"model": "P/E", "industry": "居家生活類", "n": 159, "median": 14.78, "winRate": 56.6, "peer": -0.09, "excess": 14.88},
  {"model": "P/E", "industry": "其他電子業", "n": 144, "median": 17.6, "winRate": 46.53, "peer": 8.27, "excess": 9.33},
  {"model": "P/E", "industry": "光電業", "n": 469, "median": 11.51, "winRate": 44.56, "peer": 3.26, "excess": 8.24},
  {"model": "P/E", "industry": "食品工業", "n": 202, "median": 11.93, "winRate": 49.01, "peer": 3.91, "excess": 8.02},
  {"model": "P/E", "industry": "汽車工業", "n": 198, "median": 5.2, "winRate": 52.02, "peer": -2.65, "excess": 7.84},
  {"model": "P/E", "industry": "半導體業", "n": 887, "median": 15.25, "winRate": 48.93, "peer": 7.63, "excess": 7.62},
  {"model": "P/E", "industry": "航運業", "n": 380, "median": 12.3, "winRate": 43.16, "peer": 4.69, "excess": 7.62},
  {"model": "P/E", "industry": "文化創意業", "n": 146, "median": 3.27, "winRate": 42.47, "peer": -3.65, "excess": 6.93},
  {"model": "P/E", "industry": "通信網路業", "n": 284, "median": 11.77, "winRate": 52.46, "peer": 4.99, "excess": 6.79},
  {"model": "P/E", "industry": "水泥工業", "n": 58, "median": 10.66, "winRate": 25.86, "peer": 4.47, "excess": 6.19},
  {"model": "P/E", "industry": "生技醫療業", "n": 1134, "median": 1.79, "winRate": 42.24, "peer": -3.71, "excess": 5.5},
  {"model": "P/E", "industry": "電子通路業", "n": 315, "median": 13.78, "winRate": 60.32, "peer": 9.25, "excess": 4.53},
  {"model": "P/E", "industry": "電子工業", "n": 1519, "median": 11.62, "winRate": 48.45, "peer": 7.17, "excess": 4.45},
  {"model": "P/E", "industry": "電器電纜", "n": 157, "median": 12.27, "winRate": 56.05, "peer": 8.15, "excess": 4.12},
  {"model": "P/E", "industry": "化學生技醫療", "n": 301, "median": 6.49, "winRate": 45.18, "peer": 2.55, "excess": 3.94},
  {"model": "P/E", "industry": "其他電子類", "n": 264, "median": 10.36, "winRate": 43.56, "peer": 6.53, "excess": 3.83},
  {"model": "P/E", "industry": "居家生活", "n": 95, "median": 7.07, "winRate": 45.26, "peer": 3.51, "excess": 3.56},
  {"model": "P/E", "industry": "電腦及週邊設備業", "n": 899, "median": 9.71, "winRate": 52.61, "peer": 6.61, "excess": 3.1},
  {"model": "P/E", "industry": "鋼鐵工業", "n": 473, "median": 5.1, "winRate": 40.38, "peer": 2.35, "excess": 2.75},
  {"model": "P/E", "industry": "電子零組件業", "n": 1436, "median": 10.52, "winRate": 45.61, "peer": 7.99, "excess": 2.53},
  {"model": "P/E", "industry": "運動休閒", "n": 209, "median": 0.61, "winRate": 28.71, "peer": -1.04, "excess": 1.64},
  {"model": "P/E", "industry": "電機機械", "n": 613, "median": 4.01, "winRate": 39.15, "peer": 2.49, "excess": 1.52},
  {"model": "P/E", "industry": "觀光餐旅", "n": 216, "median": -1.36, "winRate": 42.13, "peer": -2.56, "excess": 1.2},
  {"model": "P/E", "industry": "化學工業", "n": 188, "median": 2.43, "winRate": 26.6, "peer": 1.33, "excess": 1.1},
  {"model": "P/E", "industry": "綠能環保類", "n": 82, "median": 3.49, "winRate": 57.32, "peer": 3.96, "excess": -0.47},
  {"model": "P/E", "industry": "資訊服務業", "n": 200, "median": 7.98, "winRate": 52.0, "peer": 9.22, "excess": -1.24},
  {"model": "P/E", "industry": "建材營造", "n": 669, "median": 5.17, "winRate": 50.67, "peer": 7.13, "excess": -1.96},
  {"model": "P/E", "industry": "油電燃氣業", "n": 58, "median": 3.68, "winRate": 51.72, "peer": 5.97, "excess": -2.29},
  {"model": "P/E", "industry": "金融保險", "n": 201, "median": 7.38, "winRate": 35.82, "peer": 10.05, "excess": -2.67},
  {"model": "P/E", "industry": "紡織纖維", "n": 369, "median": -2.44, "winRate": 32.25, "peer": 0.65, "excess": -3.09},
  {"model": "P/E", "industry": "其他", "n": 664, "median": -1.8, "winRate": 41.72, "peer": 1.39, "excess": -3.19},
  {"model": "P/E", "industry": "貿易百貨", "n": 118, "median": -4.96, "winRate": 32.2, "peer": -1.75, "excess": -3.21},
  {"model": "P/E", "industry": "運動休閒類", "n": 123, "median": -1.29, "winRate": 27.64, "peer": 2.5, "excess": -3.79},
  {"model": "P/E", "industry": "綠能環保", "n": 128, "median": -5.85, "winRate": 25.0, "peer": -1.13, "excess": -4.72},
  {"model": "P/E", "industry": "數位雲端類", "n": 65, "median": -7.75, "winRate": 52.31, "peer": -2.82, "excess": -4.93},
  {"model": "P/E", "industry": "塑膠工業", "n": 168, "median": -5.84, "winRate": 34.52, "peer": -0.73, "excess": -5.1},
  {"model": "P/E", "industry": "橡膠工業", "n": 152, "median": -5.52, "winRate": 32.24, "peer": -0.33, "excess": -5.19},
  {"model": "P/E", "industry": "農業科技業", "n": 42, "median": -5.96, "winRate": 21.43, "peer": -0.73, "excess": -5.23},
  {"model": "P/E", "industry": "金融業", "n": 74, "median": -6.87, "winRate": 48.65, "peer": 7.27, "excess": -14.14}
]
