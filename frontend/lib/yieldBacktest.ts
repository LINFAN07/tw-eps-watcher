/**
 * 「便宜 × 高殖利率」榜單的回測判讀（資料在 backtestYieldStats.ts，由
 * scripts/backtest_yield.py 產生）。
 *
 * 為什麼要單獨一支模組：這個榜單的篩選條件是「P/E 便宜」與「當月全市場殖利率
 * 前 20%」的交集，跟 lib/backtest.ts 那套單模型實績是不同的策略，數字不可互換。
 * 資料庫另有 valuations.yield_status（該股相對「自己」歷史殖利率的百分位），
 * 那又是第三種定義，同樣不能拿來當這個榜單的篩選條件——見 HIGH_YIELD_PCTILE。
 */

import { EXCESS_THRESHOLD, OOS_CAVEAT, type Tone } from './backtest'
import {
  YIELD_BY_INDUSTRY, YIELD_OVERALL, YIELD_HORIZON, YIELD_RANK_GROUP,
  type YieldIndustryRow,
} from './backtestYieldStats'

/**
 * 高殖利率的定義：當下全市場（有 TTM 現金股利者）殖利率的第 80 百分位以上。
 *
 * 用橫斷面百分位而非固定門檻（如 5%），與回測完全一致：固定門檻會讓低利率年份
 * 全市場入選、高利率年份全數落榜，選出的族群隨市場環境漂移。
 */
export const HIGH_YIELD_PCTILE = 0.80

export interface YieldTrackRecord extends YieldIndustryRow {
  tone: Tone
  verdict: string
}

/**
 * 查某產業在此榜單策略下的歷史實績。
 * 樣本不足 30 筆或該產業未回測時回傳 null——寧可不顯示，也不用別的數字頂替。
 */
export function getYieldTrackRecord(industry: string | null | undefined): YieldTrackRecord | null {
  if (!industry) return null
  const row = YIELD_BY_INDUSTRY.find(r => r.industry === industry)
  if (!row) return null

  const tone: Tone = row.excess >= EXCESS_THRESHOLD ? 'good'
    : row.excess <= -EXCESS_THRESHOLD ? 'bad'
    : 'neutral'

  // 一律中性陳述，不下「別碰」這類預測性判語（理由見 backtest.ts 的 OOS_CAVEAT）
  const verdict = `過去 ${YIELD_HORIZON} 個月持有期，此產業的「便宜×高殖利率」訊號`
    + `報酬中位數 ${row.median.toFixed(1)}%，`
    + `${row.excess >= 0 ? '領先' : '落後'}同業 ${Math.abs(row.excess).toFixed(1)} 個百分點`
    + `（樣本 ${row.n.toLocaleString()} 筆）。` + OOS_CAVEAT

  return { ...row, tone, verdict }
}

/** 榜單本身、單獨 P/E、全市場等權三組的整體實績 */
export function getYieldOverall(group: string, horizon = YIELD_HORIZON) {
  return YIELD_OVERALL.find(r => r.group === group && r.horizon === horizon) ?? null
}

export { YIELD_HORIZON, YIELD_RANK_GROUP }

/**
 * 榜單頁必須同時出現的但書。前四條與 lib/backtest.ts 的 CAVEATS 同源，
 * 後兩條是這個榜單獨有的——高殖利率族群受倖存者偏差的影響比其他組更重。
 */
export const YIELD_CAVEATS = [
  '已下市、停牌的股票不在統計範圍內，因此結果偏樂觀。這一點對高殖利率族群的殺傷力'
  + '特別大：配不出股利、最後走向下市的公司，正是被移出統計的那一群。',
  '殖利率用的是過去 12 個月「已經配出」的現金股利，不是對未來配息的預測。'
  + '資料無法辨識一次性配發（處分資產、資本公積），這類公司的殖利率會虛高。',
  '每個月都重新選股、持有期又長，同一段行情被重複計入，勝率看起來會比實際更穩定。',
  '沒有扣除手續費與證交稅，實際報酬會比這裡低一些。',
  '過去表現不代表未來。此為模型體檢，不是投資建議。',
]
