/**
 * 回測結果的判讀邏輯（資料在 backtestStats.ts，由 Python 腳本產生）。
 *
 * 存在的理由：網站原本只說「這支便宜」，使用者很容易讀成「買了會賺」。
 * 回測顯示便宜訊號整體有 55% 的機率跑輸 0050，這個事實必須跟訊號本身
 * 一起出現，而不是藏在另一個頁面。
 *
 * 2026-07-22 修正呈現方式：分產業的數字原本被寫成「價值陷阱」等預警語，
 * 但樣本外檢驗證明產業差異不會延續（見 OOS_CAVEAT）。數字照給——本站定位
 * 是模型體檢報告——但一律中性陳述，不替使用者下「別碰」的判斷。
 */

import { BY_INDUSTRY, OVERALL, INDUSTRY_HORIZON, type IndustryRow } from './backtestStats'

/**
 * 個股卡片／排行榜的「就地實績」目前只注入 P/E 與 P/B。
 *
 * P/S、P/FCF 已回測（見 /backtest 報告頁，整體表現與 P/E/P/B 相近），但這兩者的
 * 「產業別」實績尚未做樣本外（前後期）持續性檢驗——P/E/P/B 做過、證明產業差異不會
 * 延續（見 OOS_CAVEAT）。在對這兩個新模型補做同樣的檢驗前，先不把它們的產業數字
 * 注入買賣決策畫面，以免被讀成選股依據。報告頁照常完整顯示四個模型（那是體檢不是推薦）。
 */
export type BacktestedModel = 'pe' | 'pb'

const MODEL_LABEL: Record<BacktestedModel, string> = { pe: 'P/E', pb: 'P/B' }

export function isBacktested(model: string): model is BacktestedModel {
  return model === 'pe' || model === 'pb'
}

export type Tone = 'good' | 'neutral' | 'bad'

export interface TrackRecord extends IndustryRow {
  tone: Tone
  /** 一句話結論，直接給使用者看 */
  verdict: string
}

/** 超額報酬多少才算有意義。±3 個百分點以內視為雜訊，不給使用者方向性暗示 */
export const EXCESS_THRESHOLD = 3

/**
 * 這句必須跟著每一則產業實績一起出現。
 *
 * 2026-07-22 樣本外檢驗：用前半期（2016-2021）算出各產業的超額報酬，
 * 看後半期（2022 起）是否延續——結果是不延續，而且方向相反：
 *
 *   前期被標「落後」的 16 個組合 → 後期仍落後僅 19%、反轉為領先 56%
 *   後期超額中位數 +3.91pp（前期 -6.09pp）
 *   前期被標「領先」者 → 後期超額中位數僅 +2.33pp，比前者還低
 *   前後期相關性 Pearson -0.06、Spearman -0.02
 *
 * 也就是說這些數字只描述過去，對未來沒有預測力。資料本身是真的、
 * 值得呈現（本站定位是模型體檢報告），但不可讓使用者讀成預警。
 */
export const OOS_CAVEAT = '這是過去的紀錄，不是預測——我們實際驗證過：一個產業以前落後，'
  + '之後不一定繼續落後，早期落後的產業後來反而常常稍微好一些。'

/**
 * 查某模型在某產業的歷史實績。
 * 找不到（樣本不足 30 筆、產業未回測、模型未回測）一律回傳 null——
 * 寧可不顯示，也不用其他產業的數字頂替。
 */
export function getTrackRecord(model: string, industry: string | null | undefined): TrackRecord | null {
  if (!isBacktested(model) || !industry) return null
  const row = BY_INDUSTRY.find(r => r.model === MODEL_LABEL[model] && r.industry === industry)
  if (!row) return null

  const tone: Tone = row.excess >= EXCESS_THRESHOLD ? 'good'
    : row.excess <= -EXCESS_THRESHOLD ? 'bad'
    : 'neutral'

  // 純陳述歷史，不下預測性判語。原本 bad 寫「注意：多為價值陷阱」、
  // good 寫「表現較佳」，都是把回顧當預測——樣本外檢驗證明不成立（見 OOS_CAVEAT）。
  const verdict = `這個產業裡被判「便宜」的 ${MODEL_LABEL[model]} 股，`
    + `過去買進後抱滿 ${INDUSTRY_HORIZON} 個月，報酬中位數 ${row.median.toFixed(1)}%，`
    + `比整個產業的平均水準${row.excess >= 0 ? '高' : '低'} ${Math.abs(row.excess).toFixed(1)} 個百分點`
    + `（${row.n.toLocaleString()} 筆歷史紀錄）。` + OOS_CAVEAT

  return { ...row, tone, verdict }
}

/**
 * 多模型共識列用：在該列共識的模型中，取實績最差的一個。
 * 取最差而非平均，是刻意不讓落後的那一項被好數字蓋掉——
 * 但呈現一律中性，這些數字描述過去、不預測未來（見 OOS_CAVEAT）。
 */
export function getWorstTrackRecord(
  modelLabels: string[] | undefined,
  industry: string | null | undefined,
): TrackRecord | null {
  if (!modelLabels?.length) return null
  const records = (Object.keys(MODEL_LABEL) as BacktestedModel[])
    .filter(m => modelLabels.includes(MODEL_LABEL[m]))
    .map(m => getTrackRecord(m, industry))
    .filter((r): r is TrackRecord => r !== null)
  return records.sort((a, b) => a.excess - b.excess)[0] ?? null
}

/** 整體結果查詢（group 用 backtestStats 裡的原始標籤） */
export function getOverall(group: string, horizon: number) {
  return OVERALL.find(r => r.group === group && r.horizon === horizon) ?? null
}

/**
 * 結果必須連同偏誤一起呈現。少了這段，上面的數字就是誤導。
 */
export const CAVEATS = [
  '已下市、停牌的股票不在統計範圍內（約 198 檔），因此結果偏樂觀。',
  '每個月都重新選股、持有期又長，同一段行情被重複計入，勝率看起來會比實際更穩定。',
  '沒有扣除手續費與證交稅，實際報酬會比這裡低一些。',
  '過去表現不代表未來。此為模型體檢，不是投資建議。',
]
