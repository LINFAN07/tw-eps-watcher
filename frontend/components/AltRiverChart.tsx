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

interface Props {
  code: string
  model: 'pb' | 'ps'  // 對應 /api/chart/pb/ 或 /api/chart/ps/
}

const labelMap: Record<string, string> = {
  price: '現價', cheap: '便宜價', fair: '合理價', expensive: '昂貴價',
}

export default function AltRiverChart({ code, model }: Props) {
  const [data, setData]       = useState<Point[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState('')

  useEffect(() => {
    fetch(`/api/chart/${model}/${code}`)
      .then(r => r.json())
      .then(d => {
        if (d.error) { setError(d.error); return }
        setData(d.chartData)
      })
      .catch(() => setError('載入失敗'))
      .finally(() => setLoading(false))
  }, [code, model])

  if (loading)
    return <div className="h-80 flex items-center justify-center text-gray-400">載入圖表中...</div>
  if (error || data.length === 0)
    return <div className="h-80 flex items-center justify-center text-gray-400 text-sm px-4 text-center">{error || '圖表資料不足'}</div>

  const yearTicks = [...new Set(data.map(d => d.date.slice(0, 4)))].map(
    y => data.find(d => d.date.startsWith(y))!.date
  )

  return (
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
          <Line type="monotone" dataKey="cheap"     stroke="#16a34a" strokeWidth={1.5} dot={false} strokeDasharray="5 3" name="cheap" />
          <Line type="monotone" dataKey="fair"      stroke="#2563eb" strokeWidth={1.5} dot={false} strokeDasharray="5 3" name="fair" />
          <Line type="monotone" dataKey="expensive" stroke="#dc2626" strokeWidth={1.5} dot={false} strokeDasharray="5 3" name="expensive" />
          <Line type="monotone" dataKey="price"     stroke="#111827" strokeWidth={2}   dot={false} name="price" />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
