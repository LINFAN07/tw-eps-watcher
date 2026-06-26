'use client'

import { useEffect, useState } from 'react'
import {
  ComposedChart, Line, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer,
} from 'recharts'

interface Point {
  date: string
  price: number
  cheap: number
  fair: number
  expensive: number
}

export default function PERiverChart({ code }: { code: string }) {
  const [data, setData] = useState<Point[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    fetch(`/api/chart/${code}`)
      .then(r => r.json())
      .then(d => {
        if (d.error) { setError(d.error); return }
        setData(d.chartData)
      })
      .catch(() => setError('載入失敗'))
      .finally(() => setLoading(false))
  }, [code])

  if (loading) return <div className="h-80 flex items-center justify-center text-gray-400">載入圖表中...</div>
  if (error || data.length === 0) return <div className="h-80 flex items-center justify-center text-gray-400">圖表資料不足</div>

  // X 軸：每年顯示一個刻度
  const yearTicks = [...new Set(data.map(d => d.date.slice(0, 4)))].map(
    y => data.find(d => d.date.startsWith(y))!.date
  )

  return (
    <ResponsiveContainer width="100%" height={380}>
      <ComposedChart data={data} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
        <XAxis
          dataKey="date"
          ticks={yearTicks}
          tickFormatter={d => d.slice(0, 4)}
          tick={{ fontSize: 12, fill: '#9ca3af' }}
        />
        <YAxis
          tick={{ fontSize: 12, fill: '#9ca3af' }}
          tickFormatter={v => v >= 1000 ? `${(v / 1000).toFixed(0)}k` : String(v)}
          width={50}
        />
        <Tooltip
          formatter={(v, name) => {
            const labels: Record<string, string> = {
              price: '現價', cheap: '便宜價', fair: '合理價', expensive: '昂貴價',
            }
            const num = typeof v === 'number' ? v.toFixed(2) : String(v ?? '')
            return [num, labels[String(name)] ?? String(name)]
          }}
          labelFormatter={l => `日期：${l}`}
        />
        <Legend formatter={v => ({ price: '現價', cheap: '便宜價', fair: '合理價', expensive: '昂貴價' }[v] ?? v)} />

        {/* 便宜～合理：綠色帶 */}
        <Area type="monotone" dataKey="fair"  fill="#dcfce7" stroke="none" legendType="none" />
        <Area type="monotone" dataKey="cheap" fill="#ffffff" stroke="none" legendType="none" baseLine={0} />

        {/* 合理～昂貴：橘色帶 */}
        <Area type="monotone" dataKey="expensive" fill="#fef3c7" stroke="none" legendType="none" />
        <Area type="monotone" dataKey="fair"       fill="#ffffff" stroke="none" legendType="none" />

        {/* 三條帶狀邊界線 */}
        <Line type="monotone" dataKey="cheap"     stroke="#16a34a" strokeWidth={1.5} dot={false} strokeDasharray="4 2" />
        <Line type="monotone" dataKey="fair"      stroke="#2563eb" strokeWidth={1.5} dot={false} strokeDasharray="4 2" />
        <Line type="monotone" dataKey="expensive" stroke="#dc2626" strokeWidth={1.5} dot={false} strokeDasharray="4 2" />

        {/* 現價（實線，最顯眼） */}
        <Line type="monotone" dataKey="price" stroke="#0f172a" strokeWidth={2} dot={false} />
      </ComposedChart>
    </ResponsiveContainer>
  )
}
