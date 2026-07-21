/**
 * 回測結果的判讀邏輯（資料在 backtestStats.ts，由 Python 腳本產生）。
 *
 * 存在的理由：網站原本只說「這支便宜」，使用者很容易讀成「買了會賺」。
 * 回測顯示便宜訊號整體有 55% 的機率跑輸 0050，且在部分產業是價值陷阱，
 * 這些事實必須跟訊號本身一起出現，而不是藏在另一個頁面。
 */

import { BY_INDUSTRY, OVERALL, INDUSTRY_HORIZON, type IndustryRow } from './backtestStats'

/** 只有 P/E 與 P/B 做過回測；P/S、P/FCF 尚未驗證，一律不顯示實績（不可拿別的模型的數字頂替） */
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
const EXCESS_THRESHOLD = 3

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

  const dir = row.excess >= 0 ? '領先' : '落後'
  const verdict = {
    good: `歷史上此產業的 ${MODEL_LABEL[model]} 便宜訊號表現較佳`,
    neutral: `歷史上此產業的 ${MODEL_LABEL[model]} 便宜訊號與同業無明顯差異`,
    bad: `注意：歷史上此產業的 ${MODEL_LABEL[model]} 便宜訊號多為價值陷阱`,
  }[tone] + `——過去 ${INDUSTRY_HORIZON} 個月持有期，訊號股報酬中位數 ${row.median.toFixed(1)}%，`
    + `${dir}同業平均 ${Math.abs(row.excess).toFixed(1)} 個百分點（樣本 ${row.n.toLocaleString()} 筆）。`

  return { ...row, tone, verdict }
}

/**
 * 多模型共識列用：在該列共識的模型中，取實績最差的一個。
 * 共識代表「多個模型都說便宜」，但只要其中一個模型在這個產業是價值陷阱，
 * 使用者就該看到警告——取最差而非平均，是刻意讓警示不被好消息稀釋。
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
