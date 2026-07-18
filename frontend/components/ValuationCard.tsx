'use client'

import { useState } from 'react'

interface EpsQuarter {
  quarter_end_date: string
  eps: number
}

interface Valuation {
  ttm_eps: number
  normalized_eps?: number | null
  cheap_pe: number
  fair_pe: number
  expensive_pe: number
  cheap_price: number | null
  fair_price: number | null
  expensive_price: number | null
  current_price: number
  status: string
  warning?: string | null
  nonop_warning?: string | null
  capital_change_warning?: string | null
  updated_at: string
  pb_book_value?: number | null
  pb_cheap_pb?: number | null
  pb_fair_pb?: number | null
  pb_expensive_pb?: number | null
  pb_cheap_price?: number | null
  pb_fair_price?: number | null
  pb_expensive_price?: number | null
  pb_status?: string | null
  operating_margin?: number | null
  debt_ratio?: number | null
  ps_revenue_per_share?: number | null
  ps_cheap_ps?: number | null
  ps_fair_ps?: number | null
  ps_expensive_ps?: number | null
  ps_cheap_price?: number | null
  ps_fair_price?: number | null
  ps_expensive_price?: number | null
  ps_status?: string | null
  pfcf_per_share?: number | null
  pfcf_cheap_pfcf?: number | null
  pfcf_fair_pfcf?: number | null
  pfcf_expensive_pfcf?: number | null
  pfcf_cheap_price?: number | null
  pfcf_fair_price?: number | null
  pfcf_expensive_price?: number | null
  pfcf_status?: string | null
  yield_ttm_div?: number | null
  yield_cheap_yield?: number | null
  yield_fair_yield?: number | null
  yield_expensive_yield?: number | null
  yield_cheap_price?: number | null
  yield_fair_price?: number | null
  yield_expensive_price?: number | null
  yield_status?: string | null
}

type Model = 'pe' | 'pb' | 'ps' | 'pfcf' | 'yield'

const MODEL_LABELS: Record<Model, string> = {
  pe: 'P/E', pb: 'P/B', ps: 'P/S', pfcf: 'P/FCF', yield: '殖利率',
}

// 品質門檻設定（新增指標時在此加一個陣列）
const ROE_TIERS = [
  { min: 15, valueColor: 'text-green-600', label: '優質', labelColor: 'text-green-500' },
  { min: 8,  valueColor: 'text-amber-500', label: '普通', labelColor: 'text-amber-400' },
  { min: 0,  valueColor: 'text-red-500',   label: '偏低', labelColor: 'text-red-400'   },
]

const MARGIN_TIERS = [
  { min: 20,                    valueColor: 'text-green-600', label: '優質', labelColor: 'text-green-500' },
  { min: 10,                    valueColor: 'text-amber-500', label: '普通', labelColor: 'text-amber-400' },
  { min: 0,                     valueColor: 'text-red-500',   label: '偏低', labelColor: 'text-red-400'   },
  { min: Number.NEGATIVE_INFINITY, valueColor: 'text-red-600', label: '虧損', labelColor: 'text-red-600' },
]

// 負債比：降序 min 方向，與 ROE_TIERS/MARGIN_TIERS 一致（find 回傳第一個 ratio >= min 的項）
// 金融業（銀行/保險/證券）天生高槓桿，閾值另計
const DEBT_TIERS_FINANCE = [
  { min: 94,                       valueColor: 'text-red-500',   label: '警示', labelColor: 'text-red-400'   },
  { min: 89,                       valueColor: 'text-amber-500', label: '偏高', labelColor: 'text-amber-400' },
  { min: Number.NEGATIVE_INFINITY, valueColor: 'text-green-600', label: '正常', labelColor: 'text-green-500' },
]
const DEBT_TIERS_GENERAL = [
  { min: 61,                       valueColor: 'text-red-500',   label: '偏高', labelColor: 'text-red-400'   },
  { min: 41,                       valueColor: 'text-amber-500', label: '中等', labelColor: 'text-amber-400' },
  { min: Number.NEGATIVE_INFINITY, valueColor: 'text-green-600', label: '健康', labelColor: 'text-green-500' },
]

const FINANCE_INDUSTRIES = /銀行|保險|證券|金融/

function getDebtTier(ratio: number, industry?: string | null) {
  const tiers = FINANCE_INDUSTRIES.test(industry ?? '') ? DEBT_TIERS_FINANCE : DEBT_TIERS_GENERAL
  return tiers.find(t => ratio >= t.min)!
}

const statusStyle: Record<string, { bg: string; text: string; label: string }> = {
  '便宜': { bg: 'bg-green-50 border-green-200', text: 'text-green-700 bg-green-100', label: '低估' },
  '合理': { bg: 'bg-blue-50 border-blue-200',   text: 'text-blue-700 bg-blue-100',   label: '合理' },
  '昂貴': { bg: 'bg-red-50 border-red-200',     text: 'text-red-700 bg-red-100',     label: '高估' },
}

function toQuarterLabel(dateStr: string): string {
  const month = +dateStr.slice(5, 7)
  return `Q${Math.ceil(month / 3)}/${dateStr.slice(2, 4)}`
}

function hasModel(v: Valuation, m: Model): boolean {
  if (m === 'pe')    return !!(v.status       && v.status       !== '無法計算' && v.cheap_price       != null)
  if (m === 'pb')    return !!(v.pb_status    && v.pb_status    !== '無法計算' && v.pb_cheap_price    != null)
  if (m === 'ps')    return !!(v.ps_status    && v.ps_status    !== '無法計算' && v.ps_cheap_price    != null)
  if (m === 'pfcf')  return !!(v.pfcf_status  && v.pfcf_status  !== '無法計算' && v.pfcf_cheap_price  != null)
  return !!(v.yield_status && v.yield_status !== '無法計算' && v.yield_cheap_price != null)
}

function getRecommendedModel(industry: string | null | undefined, v: Valuation): Model {
  const ind = industry ?? ''
  // 金融業 + 景氣循環股 + 資產重型（營建）→ P/B 定錨最穩
  // 營建股獲利依完工認列、忽高忽低，P/E 天生失真，須用淨值定錨
  if (/銀行|保險|證券|金融|航運|鋼鐵|水泥|面板|造紙|玻璃|塑膠|建材營造/.test(ind)) {
    if (hasModel(v, 'pb')) return 'pb'
  }
  // 虧損股 → P/S（FCF 也常為負，P/E 無意義）
  if (v.ttm_eps <= 0) {
    if (hasModel(v, 'ps')) return 'ps'
    if (hasModel(v, 'pb')) return 'pb'
    if (hasModel(v, 'pfcf')) return 'pfcf'
    return 'pe'
  }
  // 一般情況 fallback: P/E → P/B → P/S → P/FCF
  for (const m of ['pe', 'pb', 'ps', 'pfcf'] as Model[]) {
    if (hasModel(v, m)) return m
  }
  return 'pe'
}

function getModelStatus(v: Valuation, m: Model): string {
  if (m === 'pe') return v.status
  if (m === 'pb')   return v.pb_status    ?? '未知'
  if (m === 'ps')   return v.ps_status    ?? '未知'
  if (m === 'pfcf') return v.pfcf_status  ?? '未知'
  return v.yield_status ?? '未知'
}

// 各項資料的實際基準日期。顯示這個而非寫入時間戳，
// 使用者才能自行判斷資料新鮮度（排程延遲、來源落後都看得出來）。
type AsOf = {
  price?: string | null   // 股價：收盤日
  pe?: string | null      // P/E：EPS 最新季度
  pb?: string | null      // P/B：淨值最新季度
  ps?: string | null      // P/S：月營收最新月份
  pfcf?: string | null    // P/FCF：現金流最新季度
  yield?: string | null   // 殖利率：最近除息日
}

// "2026-03-31" → "2026 Q1"
function fmtQuarter(iso: string): string {
  return `${iso.slice(0, 4)} Q${Math.ceil(+iso.slice(5, 7) / 3)}`
}
// "2026-06-01" → "2026/06"
function fmtMonth(iso: string): string {
  return `${iso.slice(0, 4)}/${iso.slice(5, 7)}`
}
// "2026-07-17" → "2026/07/17"
function fmtDay(iso: string): string {
  return iso.slice(0, 10).replace(/-/g, '/')
}

export default function ValuationCard({
  v,
  ttmQuarters = [],
  prevYearQuarters = [],
  industry,
  asOf = {},
}: {
  v: Valuation
  ttmQuarters?: EpsQuarter[]
  prevYearQuarters?: EpsQuarter[]
  industry?: string | null
  asOf?: AsOf
}) {
  const recommended = getRecommendedModel(industry, v)
  const [active, setActive] = useState<Model>(recommended)

  const activeStatus = getModelStatus(v, active)
  const style = statusStyle[activeStatus] ?? { bg: 'bg-gray-50 border-gray-200', text: 'text-gray-500 bg-gray-100', label: '未知' }

  const useNormalizedPE = v.ttm_eps <= 0 && v.normalized_eps != null && v.normalized_eps > 0
  const currentPE = v.ttm_eps > 0
    ? (v.current_price / v.ttm_eps).toFixed(1)
    : useNormalizedPE
      ? (v.current_price / v.normalized_eps!).toFixed(1)
      : '—'

  // 當前模型基準資料的實際日期（季報→「2026 Q1」、月營收→「2026/06」、股利→除息日）
  const basisAsOf = (() => {
    if (active === 'pe')   return asOf.pe   ? fmtQuarter(asOf.pe)  : null
    if (active === 'pb')   return asOf.pb   ? fmtQuarter(asOf.pb)  : null
    if (active === 'ps')   return asOf.ps   ? fmtMonth(asOf.ps)    : null
    if (active === 'pfcf') return asOf.pfcf ? fmtQuarter(asOf.pfcf): null
    return asOf.yield ? `${fmtDay(asOf.yield)} 除息` : null
  })()

  // ROE = TTM EPS ÷ 每股淨值（每股基礎，單位抵銷）
  const roe = (v.ttm_eps > 0 && v.pb_book_value != null && v.pb_book_value > 0)
    ? (v.ttm_eps / v.pb_book_value) * 100
    : null
  const roeTier = roe != null ? ROE_TIERS.find(t => roe >= t.min) ?? null : null

  const marginTier = (v.operating_margin != null)
    ? MARGIN_TIERS.find(t => v.operating_margin! >= t.min) ?? null
    : null

  const debtTier = (v.debt_ratio != null)
    ? getDebtTier(v.debt_ratio, industry)
    : null

  const prevTTM = prevYearQuarters.length === 4
    ? prevYearQuarters.reduce((s, q) => s + q.eps, 0)
    : null
  const trendPct = prevTTM != null && prevTTM !== 0
    ? ((v.ttm_eps - prevTTM) / Math.abs(prevTTM)) * 100
    : null

  return (
    <div className={`rounded-2xl border p-6 ${style.bg}`}>
      {/* P/E 估值品質警告（EPS 異常時顯示）*/}
      {active === 'pe' && v.warning && (
        <div className="flex gap-2 items-start bg-amber-50 border border-amber-200 rounded-xl px-4 py-3 mb-4 text-sm text-amber-800">
          <span className="mt-0.5 shrink-0">⚠️</span>
          <span>{v.warning}</span>
        </div>
      )}
      {/* 業外收益警告（任何模型皆顯示，因為 TTM EPS 本身受影響）*/}
      {v.nonop_warning && (
        <div className="flex gap-2 items-start bg-orange-50 border border-orange-200 rounded-xl px-4 py-3 mb-4 text-sm text-orange-800">
          <span className="mt-0.5 shrink-0">🏭</span>
          <span>{v.nonop_warning}</span>
        </div>
      )}
      {/* 股本變動警告（減資/增資/分割，任何模型皆顯示，因每股序列基準受影響）*/}
      {v.capital_change_warning && (
        <div className="flex gap-2 items-start bg-sky-50 border border-sky-200 rounded-xl px-4 py-3 mb-4 text-sm text-sky-800">
          <span className="mt-0.5 shrink-0">🔀</span>
          <span>{v.capital_change_warning}</span>
        </div>
      )}

      {/* 現價 + 狀態標籤 */}
      <div className="flex items-start justify-between mb-4">
        <div>
          <p className="text-sm text-gray-500 mb-1">
            現價
            {asOf.price && <span className="text-xs text-gray-400 ml-1.5">{fmtDay(asOf.price)} 收盤</span>}
          </p>
          <p className="text-4xl font-bold text-gray-900">{v.current_price ?? '—'}</p>
        </div>
        <span className={`px-3 py-1 rounded-full text-sm font-semibold ${style.text}`}>
          {style.label}
        </span>
      </div>

      {/* 估值模型 Tab 列 */}
      <div className="flex gap-1 mb-5 bg-black/5 rounded-xl p-1">
        {(['pe', 'pb', 'ps', 'pfcf', 'yield'] as Model[]).map(m => {
          const available = hasModel(v, m)
          const isRec = m === recommended
          return (
            <button
              key={m}
              onClick={() => available && setActive(m)}
              disabled={!available}
              className={[
                'relative flex-1 py-1.5 rounded-lg text-sm font-medium transition-colors',
                active === m ? 'bg-white shadow-sm text-gray-800' : 'text-gray-500',
                available ? 'hover:text-gray-700 cursor-pointer' : 'opacity-40 cursor-not-allowed',
              ].join(' ')}
            >
              {MODEL_LABELS[m]}
              {isRec && (
                <span className="absolute -top-1.5 right-0 text-[9px] bg-blue-500 text-white px-1 py-0.5 rounded-full leading-none">
                  推薦
                </span>
              )}
            </button>
          )
        })}
      </div>

      {/* 目標三價格子 */}
      <div className="grid grid-cols-3 gap-3 mb-5">
        {active === 'pe' && <>
          <PriceLevel label="便宜價" price={v.cheap_price}     ratio={v.cheap_pe}     color="text-green-600" ratioLabel="P/E" />
          <PriceLevel label="合理價" price={v.fair_price}      ratio={v.fair_pe}      color="text-blue-600"  ratioLabel="P/E" />
          <PriceLevel label="昂貴價" price={v.expensive_price} ratio={v.expensive_pe} color="text-red-500"   ratioLabel="P/E" />
        </>}
        {active === 'pb' && <>
          <PriceLevel label="便宜價" price={v.pb_cheap_price!}     ratio={v.pb_cheap_pb!}     color="text-green-600" ratioLabel="P/B" />
          <PriceLevel label="合理價" price={v.pb_fair_price!}      ratio={v.pb_fair_pb!}      color="text-blue-600"  ratioLabel="P/B" />
          <PriceLevel label="昂貴價" price={v.pb_expensive_price!} ratio={v.pb_expensive_pb!} color="text-red-500"   ratioLabel="P/B" />
        </>}
        {active === 'ps' && <>
          <PriceLevel label="便宜價" price={v.ps_cheap_price!}     ratio={v.ps_cheap_ps!}     color="text-green-600" ratioLabel="P/S" />
          <PriceLevel label="合理價" price={v.ps_fair_price!}      ratio={v.ps_fair_ps!}      color="text-blue-600"  ratioLabel="P/S" />
          <PriceLevel label="昂貴價" price={v.ps_expensive_price!} ratio={v.ps_expensive_ps!} color="text-red-500"   ratioLabel="P/S" />
        </>}
        {active === 'pfcf' && <>
          <PriceLevel label="便宜價" price={v.pfcf_cheap_price!}     ratio={v.pfcf_cheap_pfcf!}     color="text-green-600" ratioLabel="P/FCF" />
          <PriceLevel label="合理價" price={v.pfcf_fair_price!}      ratio={v.pfcf_fair_pfcf!}      color="text-blue-600"  ratioLabel="P/FCF" />
          <PriceLevel label="昂貴價" price={v.pfcf_expensive_price!} ratio={v.pfcf_expensive_pfcf!} color="text-red-500"   ratioLabel="P/FCF" />
        </>}
        {active === 'yield' && <>
          <PriceLevel label="便宜價" price={v.yield_cheap_price!}     ratio={v.yield_cheap_yield!}     color="text-green-600" ratioLabel="殖利率≥" ratioSuffix="%" />
          <PriceLevel label="合理價" price={v.yield_fair_price!}      ratio={v.yield_fair_yield!}      color="text-blue-600"  ratioLabel="殖利率" ratioSuffix="%" />
          <PriceLevel label="昂貴價" price={v.yield_expensive_price!} ratio={v.yield_expensive_yield!} color="text-red-500"   ratioLabel="殖利率≤" ratioSuffix="%" />
        </>}
      </div>

      {/* 模型基準值 + 更新時間 */}
      <div className="flex flex-wrap gap-4 text-sm text-gray-600 border-t border-current/10 pt-4">
        {active === 'pe' && <>
          <span>
            TTM EPS <strong className="text-gray-800 ml-1">{v.ttm_eps}</strong>
            {trendPct != null && (
              trendPct > 10
                ? <span className="ml-1.5 text-xs font-semibold text-green-600">↑ 年增 {trendPct.toFixed(0)}%</span>
                : trendPct < -10
                  ? <span className="ml-1.5 text-xs font-semibold text-red-500">↓ 年減 {Math.abs(trendPct).toFixed(0)}%</span>
                  : <span className="ml-1.5 text-xs text-gray-400">持平</span>
            )}
          </span>
          {v.normalized_eps != null && v.ttm_eps < v.normalized_eps * 0.3 && (
            <span>
              計算基準 EPS <strong className="text-gray-800 ml-1">{v.normalized_eps}</strong>
              <span className="text-xs text-gray-400 ml-1">（5 年均值）</span>
            </span>
          )}
          <span>
            目前 P/E <strong className="text-gray-800 ml-1">{currentPE}</strong>
            {useNormalizedPE && <span className="text-xs text-gray-400 ml-1">（常態化）</span>}
          </span>
        </>}
        {active === 'pb' && v.pb_book_value != null && (
          <span>每股淨值 <strong className="text-gray-800 ml-1">{v.pb_book_value} 元</strong></span>
        )}
        {active === 'ps' && v.ps_revenue_per_share != null && (
          <span>TTM 每股營收 <strong className="text-gray-800 ml-1">{v.ps_revenue_per_share.toFixed(1)} 元</strong></span>
        )}
        {active === 'pfcf' && v.pfcf_per_share != null && (
          <span>TTM 每股 FCF <strong className="text-gray-800 ml-1">{v.pfcf_per_share.toFixed(1)} 元</strong></span>
        )}
        {active === 'yield' && v.yield_ttm_div != null && (
          <span>TTM 現金股利 <strong className="text-gray-800 ml-1">{v.yield_ttm_div} 元</strong></span>
        )}
        {basisAsOf && (
          <span className="basis-full text-xs text-gray-400 mt-1">
            估值基準資料截至 {basisAsOf}
          </span>
        )}
      </div>

      {/* 品質指標列（固定顯示，不隨 Tab 切換）*/}
      {(roeTier != null || marginTier != null || debtTier != null) && (
        <div className="mt-3 pt-3 border-t border-current/10 flex items-center gap-3 text-sm text-gray-600 flex-wrap">
          <span className="text-xs text-gray-400">品質</span>
          {roeTier != null && (
            <span className="flex items-center gap-1">
              <span>ROE</span>
              <strong className={roeTier.valueColor}>{roe!.toFixed(1)}%</strong>
              <span className={`text-xs ${roeTier.labelColor}`}>{roeTier.label}</span>
            </span>
          )}
          {roeTier != null && marginTier != null && <span className="text-gray-300">·</span>}
          {marginTier != null && (
            <span className="flex items-center gap-1">
              <span>營業利益率</span>
              <strong className={marginTier.valueColor}>{v.operating_margin!.toFixed(1)}%</strong>
              <span className={`text-xs ${marginTier.labelColor}`}>{marginTier.label}</span>
            </span>
          )}
          {(roeTier != null || marginTier != null) && debtTier != null && <span className="text-gray-300">·</span>}
          {debtTier != null && (
            <span className="flex items-center gap-1">
              <span>負債比</span>
              <strong className={debtTier.valueColor}>{v.debt_ratio!.toFixed(1)}%</strong>
              <span className={`text-xs ${debtTier.labelColor}`}>{debtTier.label}</span>
            </span>
          )}
        </div>
      )}

      {/* 近 4 季 EPS 明細（P/E 頁籤專屬）*/}
      {active === 'pe' && ttmQuarters.length === 4 && (
        <div className="mt-3 pt-3 border-t border-current/10">
          <p className="text-xs text-gray-400 mb-2">近 4 季 EPS 明細（合計 = TTM）</p>
          <div className="flex gap-2">
            {ttmQuarters.map(q => (
              <div key={q.quarter_end_date} className="flex-1 text-center bg-white/60 rounded-lg px-2 py-1.5">
                <p className="text-xs text-gray-400">{toQuarterLabel(q.quarter_end_date)}</p>
                <p className={`text-sm font-semibold ${q.eps < 0 ? 'text-red-500' : 'text-gray-800'}`}>
                  {q.eps}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function PriceLevel({
  label, price, ratio, color, ratioLabel, ratioSuffix = '',
}: {
  label: string; price: number | null; ratio: number; color: string; ratioLabel: string; ratioSuffix?: string
}) {
  return (
    <div className="bg-white/70 rounded-xl px-3 py-2 text-center">
      <p className="text-xs text-gray-500 mb-1">{label}</p>
      <p className={`text-lg font-bold ${color}`}>{price ?? '—'}</p>
      <p className="text-xs text-gray-400">{ratioLabel} {ratio}{ratioSuffix}</p>
    </div>
  )
}
