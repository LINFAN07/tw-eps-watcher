'use client'

import { useEffect, useState } from 'react'
import {
  ComposedChart, Bar, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ReferenceLine, ResponsiveContainer,
} from 'recharts'

interface Point {
  month: string
  revenueYi: number      // 億元（單位換算在 /api/revenue 完成，此處不再換算）
  yoy: number | null     // 基期 ≤ 0 或缺值時為 null
}

interface Summary {
  latestMonth: string
  latestRevenueYi: number
  yoy: number | null
  yoyNote: string | null
  ytdYoy: number | null
  ytdMonths: number | null
  ytdNote: string | null
}

const labelMap: Record<string, string> = { revenueYi: '月營收（億元）', yoy: '年增率' }

/**
 * 極端值以文字表達而非數字。營收基期極小的公司年增率可達數千 %，
 * 那種數字既難讀又沒有參考性（同 ValuationCard 對營業利益率的處理）。
 * 資料本身保留真實值，只有顯示層這樣做。
 */
function pctText(v: number): string {
  if (v > 1000) return '暴增（逾 10 倍）'
  if (v < -99.5) return '幾乎歸零'
  return `${v > 0 ? '+' : ''}${v.toFixed(1)}%`
}

function toneOf(v: number | null): string {
  if (v === null) return 'text-gray-400'
  return v > 0 ? 'text-red-600' : v < 0 ? 'text-green-600' : 'text-gray-600'
}

export default function RevenueChart({ code }: { code: string }) {
  const [points, setPoints]   = useState<Point[]>([])
  const [summary, setSummary] = useState<Summary | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState('')

  useEffect(() => {
    fetch(`/api/revenue/${code}`)
      .then(r => r.json())
      .then(d => {
        if (d.error) { setError(d.error); return }
        setPoints(d.points)
        setSummary(d.summary)
      })
      .catch(() => setError('載入失敗'))
      .finally(() => setLoading(false))
  }, [code])

  if (loading)
    return <div className="h-[260px] sm:h-[380px] flex items-center justify-center text-gray-400">載入圖表中...</div>

  if (error === 'NO_REVENUE')
    return <div className="h-32 flex items-center justify-center text-gray-400 text-sm">此股票無月營收紀錄</div>

  if (error || points.length === 0)
    return <div className="h-32 flex items-center justify-center text-gray-400 text-sm px-4 text-center">{error || '月營收資料不足'}</div>

  // 每年一月當刻度，避免 36 個月份標籤擠在一起
  const yearTicks = points.filter(p => p.month.endsWith('-01')).map(p => p.month)

  return (
    <div>
      {summary && (
        <div className="flex flex-wrap items-baseline gap-x-5 gap-y-1 text-sm mb-3 px-1">
          <span className="text-gray-500">
            {summary.latestMonth.replace('-', '/')} 營收
            <strong className="ml-1.5 text-gray-800">{summary.latestRevenueYi.toFixed(2)} 億</strong>
          </span>
          <span className="text-gray-500">
            單月年增
            {summary.yoy !== null
              ? <strong className={`ml-1.5 ${toneOf(summary.yoy)}`}>{pctText(summary.yoy)}</strong>
              : <span className="ml-1.5 text-gray-400">{summary.yoyNote}</span>}
          </span>
          <span className="text-gray-500">
            {summary.ytdMonths ? `累計年增（1~${summary.ytdMonths} 月）` : '累計年增'}
            {summary.ytdYoy !== null
              ? <strong className={`ml-1.5 ${toneOf(summary.ytdYoy)}`}>{pctText(summary.ytdYoy)}</strong>
              : <span className="ml-1.5 text-gray-400">{summary.ytdNote}</span>}
          </span>
        </div>
      )}

      <div className="h-[260px] sm:h-[380px]">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={points} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
            <XAxis
              dataKey="month"
              ticks={yearTicks}
              tickFormatter={(m: string) => m.slice(0, 4)}
              tick={{ fontSize: 12, fill: '#9ca3af' }}
            />
            <YAxis yAxisId="rev" tick={{ fontSize: 12, fill: '#9ca3af' }} width={50} />
            <YAxis
              yAxisId="yoy" orientation="right"
              tickFormatter={(v: number) => `${v}%`}
              tick={{ fontSize: 12, fill: '#9ca3af' }} width={55}
            />
            <Tooltip
              content={({ active, payload, label }) => {
                if (!active || !payload?.length) return null
                const p = payload[0].payload as Point
                return (
                  <div className="bg-white border border-gray-200 rounded-lg shadow p-2 text-xs">
                    <p className="text-gray-500 mb-1">{String(label).replace('-', '/')}</p>
                    <p className="text-gray-800">月營收：{p.revenueYi.toFixed(2)} 億元</p>
                    <p className={toneOf(p.yoy)}>
                      {/* null 不是 0，也不是「沒成長」——是這個月的比率算不出來 */}
                      年增率：{p.yoy === null ? '不適用（去年同期為零、負數或無資料）' : pctText(p.yoy)}
                    </p>
                  </div>
                )
              }}
            />
            <Legend formatter={(v: string) => labelMap[v] ?? v} />
            <ReferenceLine yAxisId="yoy" y={0} stroke="#d1d5db" />
            <Bar yAxisId="rev" dataKey="revenueYi" fill="#bfdbfe" name="revenueYi" />
            {/* connectNulls 保持預設的 false：基期無效的月份要斷開，
                連起來會讓「算不出來」看起來像一條平順的趨勢 */}
            <Line yAxisId="yoy" type="monotone" dataKey="yoy" stroke="#f97316"
                  strokeWidth={2} dot={false} name="yoy" />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
