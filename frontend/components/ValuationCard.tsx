interface Valuation {
  ttm_eps: number
  cheap_pe: number
  fair_pe: number
  expensive_pe: number
  cheap_price: number
  fair_price: number
  expensive_price: number
  current_price: number
  status: string
  updated_at: string
}

const statusStyle: Record<string, { bg: string; text: string; label: string }> = {
  '便宜': { bg: 'bg-green-50 border-green-200', text: 'text-green-700 bg-green-100', label: '低估' },
  '合理': { bg: 'bg-blue-50 border-blue-200',  text: 'text-blue-700 bg-blue-100',   label: '合理' },
  '昂貴': { bg: 'bg-red-50 border-red-200',    text: 'text-red-700 bg-red-100',     label: '高估' },
}

export default function ValuationCard({ v }: { v: Valuation }) {
  const style = statusStyle[v.status] ?? { bg: 'bg-gray-50 border-gray-200', text: 'text-gray-500 bg-gray-100', label: '未知' }
  const currentPE = v.ttm_eps > 0 ? (v.current_price / v.ttm_eps).toFixed(1) : '—'
  const updated = v.updated_at ? new Date(v.updated_at).toLocaleString('zh-TW', { timeZone: 'Asia/Taipei' }) : '—'

  return (
    <div className={`rounded-2xl border p-6 ${style.bg}`}>
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

      <div className="flex flex-wrap gap-4 text-sm text-gray-600 border-t border-current/10 pt-4">
        <span>TTM EPS <strong className="text-gray-800 ml-1">{v.ttm_eps}</strong></span>
        <span>目前 P/E <strong className="text-gray-800 ml-1">{currentPE}</strong></span>
        <span className="ml-auto text-xs text-gray-400">更新：{updated}</span>
      </div>
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
