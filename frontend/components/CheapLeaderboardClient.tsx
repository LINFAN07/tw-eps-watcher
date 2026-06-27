'use client'
import { useState } from 'react'
import Link from 'next/link'

export interface LeaderboardRow {
  stock_id: string
  ttm_eps: number
  cheap_pe: number
  cheap_price: number
  current_price: number
  status: string
  warning?: string | null
  stocks: { name: string; industry: string; market: string } | null
}

const statusColor: Record<string, string> = {
  '便宜': 'bg-green-100 text-green-700',
  '合理': 'bg-blue-100 text-blue-700',
  '昂貴': 'bg-red-100 text-red-700',
}

export default function CheapLeaderboardClient({ rows }: { rows: LeaderboardRow[] }) {
  const [selected, setSelected] = useState<string>('全部')

  // 從資料中提取有出現的產業，依數量排序
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

  if (filtered.length === 0) {
    return (
      <>
        <FilterBar industries={industries} selected={selected} onSelect={setSelected} />
        <p className="text-gray-400 text-center py-8">此產業目前沒有被低估的股票</p>
      </>
    )
  }

  return (
    <>
      <FilterBar industries={industries} selected={selected} onSelect={setSelected} />
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
              const discount = (((r.cheap_price - r.current_price) / r.cheap_price) * 100).toFixed(1)
              const name = r.stocks?.name ?? '—'
              const industry = r.stocks?.industry ?? r.stocks?.market ?? '—'
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
                    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${statusColor[r.status] ?? ''}`}>
                      -{discount}%
                    </span>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </>
  )
}

function FilterBar({
  industries,
  selected,
  onSelect,
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
