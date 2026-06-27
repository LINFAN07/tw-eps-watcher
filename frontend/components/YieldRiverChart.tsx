'use client'
import { useEffect, useState } from 'react'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer,
} from 'recharts'

interface Point {
  date: string
  price: number
  cheap: number
  fair: number
  expensive: number
}

interface Summary {
  ttmDiv: number
  currentYield: number | null
  cheapYield: number
  fairYield: number
  expensiveYield: number
  cheapPrice: number
  fairPrice: number
  expensivePrice: number
}

const labelMap: Record<string, string> = {
  price: '現價', cheap: '高殖利率（便宜）', fair: '中殖利率（合理）', expensive: '低殖利率（昂貴）',
}

export default function YieldRiverChart({ code }: { code: string }) {
  const [data, setData]       = useState<Point[]>([])
  const [summary, setSummary] = useState<Summary | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState('')

  useEffect(() => {
    fetch(`/api/yield-chart/${code}`)
      .then(r => r.json())
      .then(d => {
        if (d.error === 'NO_DIVIDEND') { setError('NO_DIVIDEND'); return }
        if (d.error) { setError(d.error); return }
        setData(d.chartData)
        setSummary(d.summary)
      })
      .catch(() => setError('載入失敗'))
      .finally(() => setLoading(false))
  }, [code])

  if (loading) return <div className="h-[260px] sm:h-[380px] flex items-center justify-center text-gray-400">載入圖表中...</div>

  if (error === 'NO_DIVIDEND') {
    return (
      <div className="h-32 flex items-center justify-center text-gray-400 text-sm">
        此股票無現金股利紀錄，無法計算殖利率估值帶
      </div>
    )
  }

  if (error || data.length === 0) {
    return <div className="h-32 flex items-center justify-center text-gray-400">殖利率資料不足</div>
  }

  const yearTicks = [...new Set(data.map(d => d.date.slice(0, 4)))].map(
    y => data.find(d => d.date.startsWith(y))!.date
  )

  return (
    <div className="space-y-4">
      {/* 摘要列 */}
      {summary && (
        <div className="flex flex-wrap gap-4 text-sm text-gray-600">
          <span>TTM 股利 <strong className="text-gray-800">{summary.ttmDiv} 元</strong></span>
          {summary.currentYield != null && (
            <span>目前殖利率 <strong className="text-gray-800">{summary.currentYield}%</strong></span>
          )}
          <span className="text-green-600">便宜殖利率 {summary.cheapYield}%（≥{summary.cheapPrice} 以下）</span>
          <span className="text-red-500">昂貴殖利率 {summary.expensiveYield}%（≤{summary.expensivePrice} 以上）</span>
        </div>
      )}

      {/* 殖利率河流圖 */}
      <div className="h-[260px] sm:h-[380px]">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 10, right: 10, left: 10, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
            <XAxis
              dataKey="date"
              ticks={yearTicks}
              tickFormatter={(d: string) => d.slice(0, 4)}
              tick={{ fontSize: 12, fill: '#9ca3af' }}
            />
            <YAxis
              tickFormatter={(v: number) => v >= 1000 ? `${Math.round(v / 1000)}k` : String(v)}
              tick={{ fontSize: 12, fill: '#9ca3af' }}
              width={50}
            />
            <Tooltip
              content={({ active, payload, label }) => {
                if (!active || !payload?.length) return null
                return (
                  <div className="bg-white border border-gray-200 rounded-lg shadow p-2 text-xs">
                    <p className="text-gray-500 mb-1">{String(label)}</p>
                    {payload.map(p => (
                      <p key={String(p.dataKey)} style={{ color: p.stroke ?? p.color }}>
                        {labelMap[String(p.dataKey)] ?? String(p.dataKey)}：{Number(p.value).toFixed(2)}
                      </p>
                    ))}
                  </div>
                )
              }}
            />
            <Legend formatter={(v: string) => labelMap[v] ?? v} />
            <Line type="monotone" dataKey="cheap"     stroke="#16a34a" strokeWidth={1.5} dot={false} strokeDasharray="5 3" />
            <Line type="monotone" dataKey="fair"      stroke="#2563eb" strokeWidth={1.5} dot={false} strokeDasharray="5 3" />
            <Line type="monotone" dataKey="expensive" stroke="#dc2626" strokeWidth={1.5} dot={false} strokeDasharray="5 3" />
            <Line type="monotone" dataKey="price"     stroke="#0f172a" strokeWidth={2}   dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
