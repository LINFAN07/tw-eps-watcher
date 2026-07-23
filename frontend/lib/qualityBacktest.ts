/**
 * Q4 品質濾網 + Q5 徽章的判讀邏輯（資料在 backtestQualityStats.ts，由 Python 腳本產生）。
 *
 * 這兩段的回測（backtest_badges/roe_filter/margin_filter）與主回測是分開的手動腳本，
 * 容易只重跑一部分造成數字漂移。除了 Python 端的一致性把關（見 export_quality_stats.py），
 * 前端再設一道 isQualityInSync()：品質基準必須等於 OVERALL 的 P/E 便宜 12m，
 * 失同步時頁面隱藏 Q4/Q5——寧可不顯示，也不給與其他段落對不起來的過時數字。
 */

import { OVERALL } from './backtestStats'
import { QUALITY_BASELINE, BADGES, ROE_FILTER, MARGIN_FILTER, type QualityRow } from './backtestQualityStats'

/** 兩份 lib 是否同源（同一次回測）。false 時頁面應隱藏 Q4/Q5。 */
export function isQualityInSync(): boolean {
  const pe = OVERALL.find(r => r.group === 'P/E 便宜' && r.horizon === 12)
  return !!pe && pe.n === QUALITY_BASELINE.n && Math.abs(pe.median - QUALITY_BASELINE.median) < 1e-6
}

/** 以穩定關鍵字取列，避免綁死含 emoji／門檻數字的完整字串 */
const pick = (rows: QualityRow[], kw: string) => rows.find(r => r.group.includes(kw))

export interface Q4Data {
  baseline: typeof QUALITY_BASELINE
  roeKept: QualityRow; roeDropped: QualityRow
  marginKept: QualityRow; marginDropped: QualityRow
}

/** Q4：便宜全體 vs 兩個濾網「保留 / 擋掉」。任一列缺失回傳 null（頁面據以隱藏）。 */
export function getQ4(): Q4Data | null {
  const roeKept = pick(ROE_FILTER, '濾網保留')
  const roeDropped = pick(ROE_FILTER, '濾網擋掉')
  const marginKept = pick(MARGIN_FILTER, '濾網保留')
  const marginDropped = pick(MARGIN_FILTER, '濾網擋掉')
  if (!roeKept || !roeDropped || !marginKept || !marginDropped) return null
  return { baseline: QUALITY_BASELINE, roeKept, roeDropped, marginKept, marginDropped }
}

export interface Q5Data { all: QualityRow; topQuality: QualityRow; potential: QualityRow; neither: QualityRow }

/** Q5：三種徽章分組。任一列缺失回傳 null。 */
export function getQ5(): Q5Data | null {
  const all = pick(BADGES, '便宜全體')
  const topQuality = pick(BADGES, '頂級優質')
  const potential = pick(BADGES, '潛力黑馬')
  const neither = pick(BADGES, '兩者皆非')
  if (!all || !topQuality || !potential || !neither) return null
  return { all, topQuality, potential, neither }
}
