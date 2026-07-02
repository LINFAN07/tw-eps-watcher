'use client'
import { useState, useMemo } from 'react'
import Link from 'next/link'

export interface LeaderboardRow {
  stock_id: string
  current_price: number
  cheap_price: number
  warning?: string | null
  nonop_warning?: string | null
  ttm_eps?: number | null
  pb_book_value?: number | null
  operating_margin?: number | null
  stocks: { name: string; industry: string; market: string } | null
  models?: string[]  // 多模型共識標籤，如 ['P/E', 'P/B', 'P/FCF']
}

export interface LeaderboardData {
  pe: LeaderboardRow[]
  pb: LeaderboardRow[]
  ps: LeaderboardRow[]
  pfcf: LeaderboardRow[]
  consensus: LeaderboardRow[]
}

type Model = 'pe' | 'pb' | 'ps' | 'pfcf' | 'consensus'

const MODEL_META: Record<Model, { label: string; desc: string }> = {
  pe:        { label: 'P/E',   desc: '獲利估值' },
  pb:        { label: 'P/B',   desc: '資產估值' },
  ps:        { label: 'P/S',   desc: '營收估值' },
  pfcf:      { label: 'P/FCF', desc: '現金流估值' },
  consensus: { label: '多模型', desc: '共識精選' },
}

// 從 TTM EPS 和每股淨值推算 ROE
function calcRoe(row: LeaderboardRow): number | null {
  if (row.ttm_eps != null && row.ttm_eps > 0 && row.pb_book_value != null && row.pb_book_value > 0) {
    return (row.ttm_eps / row.pb_book_value) * 100
  }
  return null
}

// 品質徽章樣式
function qualityBadge(value: number, tiers: { min: number; cls: string }[]): string {
  return tiers.find(t => value >= t.min)?.cls ?? 'text-gray-400'
}

const LOSS_TIERS   = [{ min: 0, cls: 'text-red-500' }, { min: -Infinity, cls: 'text-red-600' }]
const ROE_TIERS    = [{ min: 15, cls: 'text-green-600' }, { min: 8, cls: 'text-amber-500' }, ...LOSS_TIERS]
const MARGIN_TIERS = [{ min: 20, cls: 'text-green-600' }, { min: 10, cls: 'text-amber-500' }, ...LOSS_TIERS]

export default function CheapLeaderboardClient({ data }: { data: LeaderboardData }) {
  const [model, setModel]               = useState<Model>('pe')
  const [industry, setIndustry]         = useState<string>('全部')
  const [filterRoe, setFilterRoe]       = useState(true)   // ROE ≥ 15%
  const [filterMargin, setFilterMargin] = useState(true)   // 利益率 ≥ 10%

  const rows = data[model]

  // ROE 預先計算一次，filter 和 render 共用（避免雙重計算）
  const rowsWithRoe = useMemo(() => rows.map(r => ({ ...r, roe: calcRoe(r) })), [rows])

  const industries = useMemo(() => ['全部', ...Array.from(
    rows.reduce((map, r) => {
      const ind = r.stocks?.industry || '其他'
      map.set(ind, (map.get(ind) ?? 0) + 1)
      return map
    }, new Map<string, number>())
  ).sort((a, b) => b[1] - a[1]).map(([ind]) => ind)], [rows])

  const filtered = rowsWithRoe
    .filter(r => industry === '全部' || (r.stocks?.industry || '其他') === industry)
    .filter(r => !filterRoe    || (r.roe ?? 0) >= 15)
    .filter(r => !filterMargin || r.operating_margin == null || r.operating_margin >= 10)

  return (
    <>
      {/* 估值模型 Tab */}
      <div className="flex gap-1 mb-4 bg-gray-100 rounded-xl p-1">
        {(Object.keys(MODEL_META) as Model[]).map(m => (
          <button
            key={m}
            onClick={() => { setModel(m); setIndustry('全部') }}
            className={[
              'flex-1 py-1.5 rounded-lg text-sm font-medium transition-colors',
              model === m ? 'bg-white shadow-sm text-gray-800' : 'text-gray-500 hover:text-gray-700',
            ].join(' ')}
          >
            <span>{MODEL_META[m].label}</span>
            <span className="hidden sm:inline text-xs ml-1 opacity-60">{MODEL_META[m].desc}</span>
            {data[m].length > 0 && (
              <span className={`ml-1 text-xs px-1.5 rounded-full ${
                m === 'consensus'
                  ? 'bg-blue-100 text-blue-700'
                  : 'bg-green-100 text-green-700'
              }`}>
                {data[m].length}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* 產業篩選 */}
      <FilterBar industries={industries} selected={industry} onSelect={setIndustry} />

      {/* 品質篩選 */}
      <div className="flex items-center gap-2 mt-3 mb-1">
        <span className="text-xs text-gray-400">品質篩選</span>
        <QualityToggle active={filterRoe}    onClick={() => setFilterRoe(v => !v)}    label="ROE ≥ 15%" />
        <QualityToggle active={filterMargin} onClick={() => setFilterMargin(v => !v)} label="利益率 ≥ 10%" />
      </div>

      {/* 多模型共識說明 */}
      {model === 'consensus' && (
        <p className="text-xs text-gray-400 mt-1 mb-2">
          同時被 2 個以上估值模型認定為便宜，訊號可信度更高。排序：共識模型數量多 → 折價幅度大。
        </p>
      )}

      {filtered.length === 0 ? (
        <p className="text-gray-400 text-center py-8">此條件目前沒有符合的股票</p>
      ) : (
        <div className="overflow-x-auto mt-4">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-200 text-gray-500 text-left">
                <th className="pb-3 pr-4 font-medium">#</th>
                <th className="pb-3 pr-4 font-medium">代碼</th>
                <th className="pb-3 pr-4 font-medium">公司</th>
                <th className="pb-3 pr-4 font-medium hidden md:table-cell">產業</th>
                <th className="pb-3 pr-4 font-medium text-right hidden lg:table-cell">ROE</th>
                <th className="pb-3 pr-4 font-medium text-right hidden lg:table-cell">利益率</th>
                <th className="pb-3 pr-4 font-medium text-right">現價</th>
                <th className="pb-3 pr-4 font-medium text-right hidden sm:table-cell">
                  {model === 'consensus' ? '參考便宜價' : '便宜價'}
                </th>
                <th className="pb-3 font-medium text-right">折價</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((r, i) => {
                const discount = (((r.cheap_price - r.current_price) / r.cheap_price) * 100).toFixed(1)
                return (
                  <tr key={r.stock_id} className="border-b border-gray-50 hover:bg-gray-50 transition-colors">
                    <td className="py-3 pr-4 text-gray-400">{i + 1}</td>
                    <td className="py-3 pr-4">
                      <Link href={`/stock/${r.stock_id}`} className="font-mono font-bold text-blue-600 hover:underline">
                        {r.stock_id}
                      </Link>
                    </td>
                    <td className="py-3 pr-4">
                      <Link href={`/stock/${r.stock_id}`} className="text-gray-800 hover:text-blue-600">
                        {r.stocks?.name ?? '—'}
                      </Link>
                      {/* 多模型共識徽章 */}
                      {r.models && (
                        <div className="flex gap-1 mt-0.5 flex-wrap">
                          {r.models.map(m => (
                            <span key={m} className="text-[10px] px-1.5 py-0.5 rounded bg-blue-50 text-blue-600 font-medium leading-tight">
                              {m}
                            </span>
                          ))}
                        </div>
                      )}
                    </td>
                    <td className="py-3 pr-4 text-gray-400 hidden md:table-cell">
                      {r.stocks?.industry ?? r.stocks?.market ?? '—'}
                    </td>
                    <td className={`py-3 pr-4 text-right font-medium hidden lg:table-cell ${r.roe != null ? qualityBadge(r.roe, ROE_TIERS) : 'text-gray-300'}`}>
                      {r.roe != null ? `${r.roe.toFixed(1)}%` : '—'}
                    </td>
                    <td className={`py-3 pr-4 text-right font-medium hidden lg:table-cell ${r.operating_margin != null ? qualityBadge(r.operating_margin, MARGIN_TIERS) : 'text-gray-300'}`}>
                      {r.operating_margin != null ? `${r.operating_margin.toFixed(1)}%` : '—'}
                    </td>
                    <td className="py-3 pr-4 text-right font-medium">{r.current_price}</td>
                    <td className="py-3 pr-4 text-right text-green-600 hidden sm:table-cell">{r.cheap_price}</td>
                    <td className="py-3 text-right">
                      <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-700">
                        -{discount}%
                      </span>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}

function FilterBar({ industries, selected, onSelect }: {
  industries: string[]
  selected: string
  onSelect: (v: string) => void
}) {
  return (
    <div className="flex flex-wrap gap-2 mb-1">
      {industries.map(ind => (
        <button
          key={ind}
          onClick={() => onSelect(ind)}
          className={`text-xs px-3 py-1 rounded-full border transition-colors ${
            selected === ind
              ? 'bg-gray-800 text-white border-gray-800'
              : 'bg-gray-50 text-gray-500 border-gray-200 hover:border-gray-400 hover:text-gray-700'
          }`}
        >
          {ind}
        </button>
      ))}
    </div>
  )
}

function QualityToggle({ active, onClick, label }: {
  active: boolean
  onClick: () => void
  label: string
}) {
  return (
    <button
      onClick={onClick}
      className={`text-xs px-3 py-1 rounded-full border transition-colors font-medium ${
        active
          ? 'bg-green-600 text-white border-green-600'
          : 'bg-white text-gray-500 border-gray-300 hover:border-green-400 hover:text-green-600'
      }`}
    >
      {active ? '✓ ' : ''}{label}
    </button>
  )
}
