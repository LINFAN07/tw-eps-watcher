'use client'
import { useEffect, useState } from 'react'
import Link from 'next/link'
import { useWatchlist } from '@/hooks/useWatchlist'

interface WatchItem {
  stock_id: string
  current_price: number
  status: string
  cheap_price: number
  warning?: string | null
  stocks: { name: string } | null
}

const statusStyle: Record<string, string> = {
  '便宜': 'text-green-700 bg-green-100',
  '合理': 'text-blue-700 bg-blue-100',
  '昂貴': 'text-red-700 bg-red-100',
}

export default function WatchlistPanel() {
  const { codes, toggle } = useWatchlist()
  const [items, setItems] = useState<WatchItem[]>([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (codes.length === 0) { setItems([]); return }
    setLoading(true)
    fetch(`/api/watchlist?codes=${codes.join(',')}`)
      .then(r => r.json())
      .then(data => { setItems(data); setLoading(false) })
  }, [codes])

  if (codes.length === 0) {
    return (
      <p className="text-gray-400 text-sm text-center py-6">
        尚未加入自選股，在個股頁面點「☆ 加入自選」
      </p>
    )
  }

  if (loading) {
    return <p className="text-gray-400 text-sm text-center py-6">載入中...</p>
  }

  return (
    <div className="space-y-2">
      {codes.map(code => {
        const item = items.find(i => i.stock_id === code)
        if (!item) return null
        const discount = item.status === '便宜' && item.cheap_price > 0
          ? (((item.cheap_price - item.current_price) / item.cheap_price) * 100).toFixed(1)
          : null

        return (
          <div key={code} className="flex items-center gap-3 p-3 rounded-xl bg-gray-50 hover:bg-gray-100 transition-colors">
            <Link href={`/stock/${code}`} className="flex-1 flex items-center gap-3 min-w-0">
              <span className="font-mono font-bold text-blue-600 w-14 shrink-0">{code}</span>
              <span className="text-gray-700 truncate">{item.stocks?.name ?? '—'}</span>
              <span className="ml-auto shrink-0 text-gray-600 font-medium">{item.current_price}</span>
              {discount && (
                <span className="shrink-0 text-xs text-green-600 font-semibold">↓{discount}%</span>
              )}
              <span className={`shrink-0 text-xs px-2 py-0.5 rounded-full ${statusStyle[item.status] ?? 'text-gray-500 bg-gray-100'}`}>
                {item.status}
              </span>
            </Link>
            {/* 移除按鈕 */}
            <button
              onClick={() => toggle(code)}
              className="text-gray-300 hover:text-red-400 text-xl leading-none shrink-0"
              title="移除自選"
            >
              ×
            </button>
          </div>
        )
      })}
    </div>
  )
}
