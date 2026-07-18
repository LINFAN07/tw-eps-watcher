// P/E 可靠性判斷（推薦模型與排行榜共用的單一真相來源）
//
// 這兩種警告代表 P/E 估值模型本身失真，不是「貴/便宜」的問題：
//   - 「EPS 長期偏低」：獲利太小，P/E 倍數失去意義
//   - 「顯著高於長期均值」：獲利高峰，TTM EPS 灌水使 P/E 假性偏低
// 另加 nonop_warning：本業以外的一次性收益撐高 EPS，同樣使 P/E 失真。
//
// 只要命中任一項，P/E 就不應被推薦為主模型，也不應據以進入便宜排行榜——
// 兩邊必須用同一套標準，否則同一股票會出現「推薦 P/E」與「P/E 榜排除」的矛盾。
export const PE_UNRELIABLE_WARNINGS = ['EPS 長期偏低', '顯著高於長期均值']

export function isPeUnreliable(v: { warning?: string | null; nonop_warning?: string | null }): boolean {
  if (v.nonop_warning) return true
  const w = v.warning ?? ''
  return PE_UNRELIABLE_WARNINGS.some(kw => w.includes(kw))
}
