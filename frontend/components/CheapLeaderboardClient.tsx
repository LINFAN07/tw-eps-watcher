'use client'
import { useState } from 'react'
import Link from 'next/link'

export interface LeaderboardRow {
  stock_id: string
  current_price: number
  cheap_price: number
  warning?: string | null
  stocks: { name: string; industry: string; market: string } | null
}

export interface LeaderboardData {
  pe: LeaderboardRow[]
  pb: LeaderboardRow[]
  ps: LeaderboardRow[]
  pfcf: LeaderboardRow[]
}

type Model = 'pe' | 'pb' | 'ps' | 'pfcf'

const MODEL_META: Record<Model, { label: string; desc: string }> = {
  pe:   { label: 'P/E',   desc: '獲利估值' },
  pb:   { label: 'P/B',   desc: '資產估值' },
  ps:   { label: 'P/S',   desc: '營收估值' },
  pfcf: { label: 'P/FCF', desc: '現金流估值' },
}

export default function CheapLeaderboardClient({ data }: { data: LeaderboardData }) {
  const [model, setModel]       = useState<Model>('pe')
  const [selected, setSelected] = useState<string>('全部')

  const rows = data[model]

  const industries = ['全部', ...Array.from(
    rows.reduce((map, r) => {
      const ind = r.stocks?.industry || '其他'
      map.set(ind, (map.get(ind) ?? 0) + 1)
      return map
    }, new Map<string, number>())
  ).sort((a, b) => b[1] - a[1]).map(([ind]) => ind)]

  const filtered = selected === '全部'
    ? rows
    : rows.filter(r => (r.stocks?.industry || '其他') === selected)

  return (
    <>
      {/* 估值模型 Tab */}
      <div className="flex gap-1 mb-4 bg-gray-100 rounded-xl p-1">
        {(Object.keys(MODEL_META) as Model[]).map(m => (
          <button
            key={m}
            onClick={() => { setModel(m); setSelected('全部') }}
            className={[
              'flex-1 py-1.5 rounded-lg text-sm font-medium transition-colors',
              model === m
                ? 'bg-white shadow-sm text-gray-800'
                : 'text-gray-500 hover:text-gray-700',
            ].join(' ')}
          >
            <span>{MODEL_META[m].label}</span>
            <span className="hidden sm:inline text-xs ml-1 opacity-60">{MODEL_META[m].desc}</span>
            {data[m].length > 0 && (
              <span className="ml-1 text-xs bg-green-100 text-green-700 px-1.5 rounded-full">
                {data[m].length}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* 產業篩選 */}
      <FilterBar industries={industries} selected={selected} onSelect={setSelected} />

      {filtered.length === 0 ? (
        <p className="text-gray-400 text-center py-8">此條件目前沒有被低估的股票</p>
      ) : (
        <div className="overflow-x-auto mt-4">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-200 text-gray-500 text-left">
                <th className="pb-3 pr-4 font-medium">#</th>
                <th className="pb-3 pr-4 font-medium">代碼</th>
                <th className="pb-3 pr-4 font-medium">公司</th>
                <th className="pb-3 pr-4 font-medium hidden md:table-cell">產業</th>
                <th className="pb-3 pr-4 font-medium text-right">現價</th>
                <th className="pb-3 pr-4 font-medium text-right hidden sm:table-cell">便宜價</th>
                <th className="pb-3 font-medium text-right">折價</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((r, i) => {
                const discount  = (((r.cheap_price - r.current_price) / r.cheap_price) * 100).toFixed(1)
                const name      = r.stocks?.name ?? '—'
                const industry  = r.stocks?.industry ?? r.stocks?.market ?? '—'
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
                        {name}
                      </Link>
                    </td>
                    <td className="py-3 pr-4 text-gray-400 hidden md:table-cell">{industry}</td>
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

function FilterBar({
  industries, selected, onSelect,
}: {
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
