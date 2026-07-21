/**
 * 估值帶穩定度：這支股票的估值帶有沒有「錨」？
 *
 * 帶寬 =（昂貴倍數 − 便宜倍數）÷ 合理倍數。
 * 帶太寬代表這支股票的歷史估值散得到處都是，所謂的「便宜價」只是統計上的第 20
 * 百分位，並不對應任何穩定的市場共識。
 *
 * ## 為什麼只有這一項，而不是 0–100 分的多因子分數
 *
 * 原規劃要把「樣本數、帶寬、EPS 波動度、警告旗標」加權成一個分數。
 * 2026-07-21 用回測資料驗證後，只有帶寬站得住（38,274 筆便宜訊號，持有 12 個月）：
 *
 *   帶寬五分位 Q1(0.17) → Q5(1.18)
 *   報酬中位數 +10.00% → +3.39%（差 6.6pp，幾乎單調遞減）
 *   正報酬率    66.4% → 54.9%
 *   P/E 與 P/B 分開看都成立（P/E 10.29%→4.03%、P/B 10.06%→4.90%）
 *
 * 而「歷史樣本數」完全沒有預測力（Q1 3.57% → Q2 12.43% → Q5 1.43%，不單調），
 * 硬湊進分數只會把雜訊包裝成精確的數字。
 *
 * ## 一個必須知道的分歧
 *
 * 「勝過 0050 的比率」在帶寬分組中是【反向】的（38.7% → 47.2%）——帶寬大的訊號
 * 絕對報酬差，但相對 0050 略好，因為它們較常發生在 0050 也不好的時期。
 * 三個指標中兩個支持帶寬有效，此處採信它們，但這個分歧是真的。
 *
 * 門檻取自現行 valuations 的實際三分位（P/E n=2239、P/B n=1931）。
 */

export type BandLevel = 'stable' | 'normal' | 'diffuse'

/** 只有 P/E 與 P/B 驗證過帶寬的預測力；其餘模型不顯示，不以這兩者的結論頂替 */
const THRESHOLDS: Record<'pe' | 'pb', [number, number]> = {
  pe: [0.65, 1.14],
  pb: [0.40, 0.68],
}

export interface BandStability {
  level: BandLevel
  width: number
  label: string
  hint: string
}

const LABEL: Record<BandLevel, string> = {
  stable: '估值帶穩定',
  normal: '估值帶普通',
  diffuse: '估值帶發散',
}

const HINT: Record<BandLevel, string> = {
  stable: '歷史估值集中，便宜價對應較明確的市場共識。回測中這類訊號 12 個月報酬中位數約 +10%、正報酬率 66%。',
  normal: '歷史估值的集中程度中等。',
  diffuse: '歷史估值散布很廣，「便宜價」只是相對它自己的歷史偏低，未必真的被低估。回測中這類訊號 12 個月報酬中位數僅約 +3%、正報酬率 55%。',
}

export function getBandStability(
  cheap: number | null | undefined,
  fair: number | null | undefined,
  expensive: number | null | undefined,
  model: string,
): BandStability | null {
  if (model !== 'pe' && model !== 'pb') return null
  if (cheap == null || fair == null || expensive == null || fair <= 0) return null

  const width = (expensive - cheap) / fair
  if (!Number.isFinite(width) || width <= 0) return null

  const [lo, hi] = THRESHOLDS[model]
  const level: BandLevel = width <= lo ? 'stable' : width <= hi ? 'normal' : 'diffuse'
  return { level, width, label: LABEL[level], hint: HINT[level] }
}
