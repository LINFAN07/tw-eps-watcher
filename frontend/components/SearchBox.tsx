'use client'

import { useState, useEffect, useRef } from 'react'
import { useRouter } from 'next/navigation'

interface Stock { stock_id: string; name: string; market: string; industry: string }

export default function SearchBox() {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<Stock[]>([])
  const [open, setOpen] = useState(false)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const router = useRouter()

  useEffect(() => {
    if (!query.trim()) { setResults([]); return }
    if (timer.current) clearTimeout(timer.current)
    timer.current = setTimeout(async () => {
      try {
        const res = await fetch(`/api/search?q=${encodeURIComponent(query)}`)
        // 非 200 回應（如 API 錯誤頁）不繼續解析 JSON
        if (!res.ok) { setResults([]); return }
        setResults(await res.json())
        setOpen(true)
      } catch {
        // 網路錯誤或 JSON 解析失敗：清空結果，不顯示過時資料
        setResults([])
      }
    }, 300)
    // 元件卸載時清除計時器，避免在已卸載元件上呼叫 setState
    return () => { if (timer.current) clearTimeout(timer.current) }
  }, [query])

  function select(s: Stock) {
    setQuery('')
    setResults([])
    setOpen(false)
    router.push(`/stock/${s.stock_id}`)
  }

  return (
    <div className="relative w-full max-w-xl mx-auto">
      <input
        type="text"
        value={query}
        onChange={e => setQuery(e.target.value)}
        onFocus={() => results.length > 0 && setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        placeholder="輸入股票代碼或公司名稱，例如 2330 或 台積電"
        className="w-full px-5 py-3 text-base border border-gray-300 rounded-xl shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
      />
      {open && results.length > 0 && (
        <ul className="absolute z-10 w-full mt-1 bg-white border border-gray-200 rounded-xl shadow-lg overflow-hidden">
          {results.map(s => (
            <li
              key={s.stock_id}
              onMouseDown={() => select(s)}
              className="flex items-center justify-between px-4 py-3 hover:bg-blue-50 cursor-pointer"
            >
              <span className="font-mono font-semibold text-blue-700">{s.stock_id}</span>
              <span className="flex-1 mx-3 text-gray-800">{s.name}</span>
              <span className="text-xs text-gray-400">{s.industry ?? s.market}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
