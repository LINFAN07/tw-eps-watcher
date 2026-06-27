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
  cheap_price: number
  fair_price: number
  expensive_price: number
  current_price: number
  status: string
  warning?: string | null
  updated_at: string
}

const statusStyle: Record<string, { bg: string; text: string; label: string }> = {
  '便宜': { bg: 'bg-green-50 border-green-200', text: 'text-green-700 bg-green-100', label: '低估' },
  '合理': { bg: 'bg-blue-50 border-blue-200',  text: 'text-blue-700 bg-blue-100',   label: '合理' },
  '昂貴': { bg: 'bg-red-50 border-red-200',    text: 'text-red-700 bg-red-100',     label: '高估' },
}

// "2025-03-31" → "Q1/25"（用字串切割，無時區問題）
function toQuarterLabel(dateStr: string): string {
  const month = +dateStr.slice(5, 7)
  return `Q${Math.ceil(month / 3)}/${dateStr.slice(2, 4)}`
}

export default function ValuationCard({
  v,
  ttmQuarters = [],
  prevYearQuarters = [],
}: {
  v: Valuation
  ttmQuarters?: EpsQuarter[]
  prevYearQuarters?: EpsQuarter[]
}) {
  const style = statusStyle[v.status] ?? { bg: 'bg-gray-50 border-gray-200', text: 'text-gray-500 bg-gray-100', label: '未知' }

  // 目前本益比：TTM EPS 為負時改用常態化 EPS
  const useNormalizedPE = v.ttm_eps <= 0 && v.normalized_eps != null && v.normalized_eps > 0
  const currentPE = v.ttm_eps > 0
    ? (v.current_price / v.ttm_eps).toFixed(1)
    : useNormalizedPE
      ? (v.current_price / v.normalized_eps!).toFixed(1)
      : '—'

  const updated = v.updated_at ? new Date(v.updated_at).toLocaleString('zh-TW', { timeZone: 'Asia/Taipei' }) : '—'

  // EPS 趨勢：比較近一年 TTM vs 前一年 TTM
  const prevTTM = prevYearQuarters.length === 4
    ? prevYearQuarters.reduce((s, q) => s + q.eps, 0)
    : null
  const trendPct = prevTTM != null && prevTTM !== 0
    ? ((v.ttm_eps - prevTTM) / Math.abs(prevTTM)) * 100
    : null

  return (
    <div className={`rounded-2xl border p-6 ${style.bg}`}>
      {v.warning && (
        <div className="flex gap-2 items-start bg-amber-50 border border-amber-200 rounded-xl px-4 py-3 mb-4 text-sm text-amber-800">
          <span className="mt-0.5 shrink-0">⚠️</span>
          <span>{v.warning}</span>
        </div>
      )}

      <div className="flex items-start justify-between mb-4">
        <div>
          <p className="text-sm text-gray-500 mb-1">現價</p>
          <p className="text-4xl font-bold text-gray-900">{v.current_price ?? '—'}</p>
        </div>
        <span className={`px-3 py-1 rounded-full text-sm font-semibold ${style.text}`}>
          {style.label}
        </span>
      </div>

      <div className="grid grid-cols-3 gap-3 mb-5">
        <PriceLevel label="便宜價" price={v.cheap_price} pe={v.cheap_pe} color="text-green-600" />
        <PriceLevel label="合理價" price={v.fair_price}  pe={v.fair_pe}  color="text-blue-600" />
        <PriceLevel label="昂貴價" price={v.expensive_price} pe={v.expensive_pe} color="text-red-500" />
      </div>

      {/* 摘要列：TTM EPS（含年增減趨勢）、目前 P/E、更新時間 */}
      <div className="flex flex-wrap gap-4 text-sm text-gray-600 border-t border-current/10 pt-4">
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
        <span className="basis-full text-xs text-gray-400 mt-1">更新：{updated}</span>
      </div>

      {/* TTM 季度明細：顯示組成 TTM 的 4 季 EPS */}
      {ttmQuarters.length === 4 && (
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

function PriceLevel({ label, price, pe, color }: { label: string; price: number; pe: number; color: string }) {
  return (
    <div className="bg-white/70 rounded-xl px-3 py-2 text-center">
      <p className="text-xs text-gray-500 mb-1">{label}</p>
      <p className={`text-lg font-bold ${color}`}>{price ?? '—'}</p>
      <p className="text-xs text-gray-400">P/E {pe}</p>
    </div>
  )
}
