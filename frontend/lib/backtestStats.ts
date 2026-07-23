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
  {"horizon": 6, "group": "全市場等權（對照）", "n": 220497, "median": 1.44, "mean": 9.3, "bench": 6.93, "winRate": 41.3, "positiveRate": 53.2},
  {"horizon": 12, "group": "全市場等權（對照）", "n": 206590, "median": 4.36, "mean": 19.24, "bench": 13.86, "winRate": 46.3, "positiveRate": 56.6},
  {"horizon": 24, "group": "全市場等權（對照）", "n": 180015, "median": 14.29, "mean": 39.26, "bench": 16.86, "winRate": 48.8, "positiveRate": 63.6},
  {"horizon": 6, "group": "P/E 便宜", "n": 15368, "median": 2.61, "mean": 8.61, "bench": 7.19, "winRate": 42.1, "positiveRate": 56.0},
  {"horizon": 12, "group": "P/E 便宜", "n": 14648, "median": 7.26, "mean": 20.85, "bench": 20.63, "winRate": 45.8, "positiveRate": 60.9},
  {"horizon": 24, "group": "P/E 便宜", "n": 13105, "median": 22.42, "mean": 50.23, "bench": 56.7, "winRate": 45.3, "positiveRate": 70.8},
  {"horizon": 6, "group": "P/B 便宜", "n": 32377, "median": 2.08, "mean": 10.15, "bench": 12.74, "winRate": 39.1, "positiveRate": 54.5},
  {"horizon": 12, "group": "P/B 便宜", "n": 29518, "median": 7.01, "mean": 25.87, "bench": 23.0, "winRate": 44.8, "positiveRate": 60.0},
  {"horizon": 24, "group": "P/B 便宜", "n": 24333, "median": 22.98, "mean": 54.28, "bench": 58.79, "winRate": 46.3, "positiveRate": 69.9}
]

export const BY_INDUSTRY: IndustryRow[] = [
  {"model": "P/B", "industry": "半導體業", "n": 1774, "median": 22.1, "winRate": 56.82, "peer": 8.43, "excess": 13.66},
  {"model": "P/B", "industry": "電子零組件業", "n": 2337, "median": 21.59, "winRate": 50.19, "peer": 8.19, "excess": 13.4},
  {"model": "P/B", "industry": "電腦及週邊設備業", "n": 1072, "median": 18.49, "winRate": 49.07, "peer": 7.16, "excess": 11.32},
  {"model": "P/B", "industry": "光電業", "n": 951, "median": 14.26, "winRate": 43.74, "peer": 3.79, "excess": 10.47},
  {"model": "P/B", "industry": "金融業", "n": 88, "median": 18.02, "winRate": 73.86, "peer": 7.61, "excess": 10.41},
  {"model": "P/B", "industry": "玻璃陶瓷", "n": 69, "median": 13.62, "winRate": 26.09, "peer": 3.3, "excess": 10.31},
  {"model": "P/B", "industry": "其他電子類", "n": 598, "median": 17.59, "winRate": 45.15, "peer": 7.33, "excess": 10.26},
  {"model": "P/B", "industry": "電子工業", "n": 2766, "median": 15.64, "winRate": 48.34, "peer": 7.27, "excess": 8.38},
  {"model": "P/B", "industry": "綠能環保類", "n": 181, "median": 12.54, "winRate": 58.01, "peer": 5.21, "excess": 7.33},
  {"model": "P/B", "industry": "通信網路業", "n": 781, "median": 12.27, "winRate": 45.84, "peer": 5.27, "excess": 7.0},
  {"model": "P/B", "industry": "航運業", "n": 391, "median": 12.13, "winRate": 42.2, "peer": 5.72, "excess": 6.41},
  {"model": "P/B", "industry": "電子通路業", "n": 373, "median": 14.98, "winRate": 49.33, "peer": 9.52, "excess": 5.46},
  {"model": "P/B", "industry": "居家生活", "n": 204, "median": 8.97, "winRate": 47.06, "peer": 3.83, "excess": 5.14},
  {"model": "P/B", "industry": "鋼鐵工業", "n": 670, "median": 7.42, "winRate": 38.21, "peer": 2.83, "excess": 4.6},
  {"model": "P/B", "industry": "造紙工業", "n": 82, "median": 4.2, "winRate": 42.68, "peer": -0.06, "excess": 4.26},
  {"model": "P/B", "industry": "汽車工業", "n": 983, "median": 1.12, "winRate": 39.98, "peer": -2.3, "excess": 3.42},
  {"model": "P/B", "industry": "化學工業", "n": 389, "median": 6.13, "winRate": 40.36, "peer": 2.78, "excess": 3.35},
  {"model": "P/B", "industry": "生技醫療業", "n": 3840, "median": 0.09, "winRate": 48.85, "peer": -2.59, "excess": 2.68},
  {"model": "P/B", "industry": "化學生技醫療", "n": 602, "median": 6.13, "winRate": 41.03, "peer": 3.74, "excess": 2.39},
  {"model": "P/B", "industry": "運動休閒", "n": 285, "median": 1.65, "winRate": 45.26, "peer": -0.66, "excess": 2.31},
  {"model": "P/B", "industry": "觀光餐旅", "n": 864, "median": 0.62, "winRate": 43.52, "peer": -1.48, "excess": 2.1},
  {"model": "P/B", "industry": "塑膠工業", "n": 579, "median": 1.38, "winRate": 40.41, "peer": -0.71, "excess": 2.09},
  {"model": "P/B", "industry": "建材營造", "n": 836, "median": 10.54, "winRate": 47.49, "peer": 8.62, "excess": 1.92},
  {"model": "P/B", "industry": "金融保險", "n": 313, "median": 13.08, "winRate": 36.42, "peer": 11.97, "excess": 1.11},
  {"model": "P/B", "industry": "電機機械", "n": 2132, "median": 3.86, "winRate": 37.52, "peer": 2.8, "excess": 1.07},
  {"model": "P/B", "industry": "資訊服務業", "n": 255, "median": 11.39, "winRate": 49.02, "peer": 10.44, "excess": 0.96},
  {"model": "P/B", "industry": "水泥工業", "n": 75, "median": 5.76, "winRate": 28.0, "peer": 4.91, "excess": 0.85},
  {"model": "P/B", "industry": "紡織纖維", "n": 882, "median": 1.02, "winRate": 38.44, "peer": 0.83, "excess": 0.19},
  {"model": "P/B", "industry": "文化創意業", "n": 545, "median": -1.52, "winRate": 45.69, "peer": -1.59, "excess": 0.06},
  {"model": "P/B", "industry": "電器電纜", "n": 106, "median": 8.88, "winRate": 38.68, "peer": 8.95, "excess": -0.07},
  {"model": "P/B", "industry": "居家生活類", "n": 303, "median": 0.72, "winRate": 43.89, "peer": 0.85, "excess": -0.13},
  {"model": "P/B", "industry": "貿易百貨", "n": 399, "median": -2.91, "winRate": 29.82, "peer": -1.51, "excess": -1.4},
  {"model": "P/B", "industry": "其他", "n": 1749, "median": 0.28, "winRate": 33.85, "peer": 1.91, "excess": -1.63},
  {"model": "P/B", "industry": "橡膠工業", "n": 231, "median": -2.48, "winRate": 31.6, "peer": 0.47, "excess": -2.95},
  {"model": "P/B", "industry": "數位雲端類", "n": 224, "median": -2.64, "winRate": 48.21, "peer": 0.32, "excess": -2.97},
  {"model": "P/B", "industry": "食品工業", "n": 497, "median": 1.58, "winRate": 36.82, "peer": 5.14, "excess": -3.56},
  {"model": "P/B", "industry": "油電燃氣業", "n": 121, "median": 1.5, "winRate": 52.07, "peer": 6.69, "excess": -5.18},
  {"model": "P/B", "industry": "農業科技業", "n": 83, "median": -3.47, "winRate": 39.76, "peer": 1.97, "excess": -5.44},
  {"model": "P/B", "industry": "數位雲端", "n": 102, "median": -9.98, "winRate": 54.9, "peer": -4.11, "excess": -5.86},
  {"model": "P/B", "industry": "綠能環保", "n": 412, "median": -6.23, "winRate": 45.87, "peer": -0.24, "excess": -6.0},
  {"model": "P/B", "industry": "運動休閒類", "n": 140, "median": -3.41, "winRate": 50.0, "peer": 2.59, "excess": -6.0},
  {"model": "P/B", "industry": "其他電子業", "n": 227, "median": 0.53, "winRate": 43.17, "peer": 7.98, "excess": -7.45},
  {"model": "P/E", "industry": "居家生活類", "n": 165, "median": 22.51, "winRate": 58.79, "peer": 0.85, "excess": 21.66},
  {"model": "P/E", "industry": "其他電子業", "n": 148, "median": 19.36, "winRate": 48.65, "peer": 7.98, "excess": 11.38},
  {"model": "P/E", "industry": "光電業", "n": 465, "median": 14.43, "winRate": 45.81, "peer": 3.79, "excess": 10.64},
  {"model": "P/E", "industry": "其他電子類", "n": 287, "median": 16.79, "winRate": 46.69, "peer": 7.33, "excess": 9.46},
  {"model": "P/E", "industry": "半導體業", "n": 933, "median": 16.2, "winRate": 49.84, "peer": 8.43, "excess": 7.76},
  {"model": "P/E", "industry": "通信網路業", "n": 319, "median": 12.81, "winRate": 52.35, "peer": 5.27, "excess": 7.53},
  {"model": "P/E", "industry": "電子通路業", "n": 349, "median": 16.51, "winRate": 60.46, "peer": 9.52, "excess": 6.99},
  {"model": "P/E", "industry": "水泥工業", "n": 67, "median": 11.77, "winRate": 25.37, "peer": 4.91, "excess": 6.85},
  {"model": "P/E", "industry": "生技醫療業", "n": 1215, "median": 3.65, "winRate": 44.12, "peer": -2.59, "excess": 6.24},
  {"model": "P/E", "industry": "居家生活", "n": 93, "median": 10.0, "winRate": 37.63, "peer": 3.83, "excess": 6.17},
  {"model": "P/E", "industry": "航運業", "n": 397, "median": 11.76, "winRate": 45.09, "peer": 5.72, "excess": 6.04},
  {"model": "P/E", "industry": "汽車工業", "n": 225, "median": 3.73, "winRate": 47.11, "peer": -2.3, "excess": 6.03},
  {"model": "P/E", "industry": "電子工業", "n": 1567, "median": 13.06, "winRate": 48.44, "peer": 7.27, "excess": 5.79},
  {"model": "P/E", "industry": "食品工業", "n": 219, "median": 10.04, "winRate": 51.6, "peer": 5.14, "excess": 4.91},
  {"model": "P/E", "industry": "文化創意業", "n": 162, "median": 3.08, "winRate": 46.91, "peer": -1.59, "excess": 4.67},
  {"model": "P/E", "industry": "電腦及週邊設備業", "n": 885, "median": 10.54, "winRate": 50.96, "peer": 7.16, "excess": 3.37},
  {"model": "P/E", "industry": "電子零組件業", "n": 1573, "median": 11.48, "winRate": 46.34, "peer": 8.19, "excess": 3.29},
  {"model": "P/E", "industry": "資訊服務業", "n": 237, "median": 13.3, "winRate": 58.65, "peer": 10.44, "excess": 2.86},
  {"model": "P/E", "industry": "電機機械", "n": 636, "median": 5.49, "winRate": 38.52, "peer": 2.8, "excess": 2.69},
  {"model": "P/E", "industry": "化學生技醫療", "n": 341, "median": 5.68, "winRate": 45.45, "peer": 3.74, "excess": 1.94},
  {"model": "P/E", "industry": "鋼鐵工業", "n": 514, "median": 4.36, "winRate": 43.0, "peer": 2.83, "excess": 1.53},
  {"model": "P/E", "industry": "運動休閒", "n": 211, "median": 0.24, "winRate": 29.38, "peer": -0.66, "excess": 0.9},
  {"model": "P/E", "industry": "電器電纜", "n": 124, "median": 9.55, "winRate": 55.65, "peer": 8.95, "excess": 0.59},
  {"model": "P/E", "industry": "化學工業", "n": 201, "median": 2.95, "winRate": 27.86, "peer": 2.78, "excess": 0.17},
  {"model": "P/E", "industry": "觀光餐旅", "n": 240, "median": -1.74, "winRate": 45.83, "peer": -1.48, "excess": -0.26},
  {"model": "P/E", "industry": "貿易百貨", "n": 114, "median": -2.17, "winRate": 35.09, "peer": -1.51, "excess": -0.66},
  {"model": "P/E", "industry": "綠能環保類", "n": 97, "median": 4.24, "winRate": 60.82, "peer": 5.21, "excess": -0.97},
  {"model": "P/E", "industry": "金融保險", "n": 220, "median": 10.33, "winRate": 41.82, "peer": 11.97, "excess": -1.65},
  {"model": "P/E", "industry": "紡織纖維", "n": 351, "median": -1.34, "winRate": 29.91, "peer": 0.83, "excess": -2.18},
  {"model": "P/E", "industry": "建材營造", "n": 655, "median": 6.39, "winRate": 51.91, "peer": 8.62, "excess": -2.23},
  {"model": "P/E", "industry": "其他", "n": 718, "median": -0.53, "winRate": 41.78, "peer": 1.91, "excess": -2.44},
  {"model": "P/E", "industry": "農業科技業", "n": 41, "median": -0.52, "winRate": 21.95, "peer": 1.97, "excess": -2.49},
  {"model": "P/E", "industry": "運動休閒類", "n": 132, "median": -1.93, "winRate": 24.24, "peer": 2.59, "excess": -4.52},
  {"model": "P/E", "industry": "油電燃氣業", "n": 57, "median": 1.7, "winRate": 56.14, "peer": 6.69, "excess": -4.98},
  {"model": "P/E", "industry": "橡膠工業", "n": 147, "median": -5.26, "winRate": 31.97, "peer": 0.47, "excess": -5.74},
  {"model": "P/E", "industry": "塑膠工業", "n": 169, "median": -6.6, "winRate": 40.83, "peer": -0.71, "excess": -5.89},
  {"model": "P/E", "industry": "綠能環保", "n": 160, "median": -7.28, "winRate": 30.63, "peer": -0.24, "excess": -7.04},
  {"model": "P/E", "industry": "數位雲端類", "n": 76, "median": -8.13, "winRate": 52.63, "peer": 0.32, "excess": -8.45},
  {"model": "P/E", "industry": "金融業", "n": 85, "median": -0.86, "winRate": 58.82, "peer": 7.61, "excess": -8.47}
]
