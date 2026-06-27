'use client'
import { useEffect, useState } from 'react'

interface Stats {
  cheap: number
  fair: number
  expensive: number
  total: number
  medianPE: number | null
}

// 依便宜/昂貴股比例判斷市場溫度
function tempLabel(cheapPct: number, expPct: number): { label: string; color: string } {
  if (cheapPct >= 35) return { label: '偏冷（低估偏多）', color: 'text-green-600' }
  if (expPct >= 50)   return { label: '偏熱（高估偏多）', color: 'text-red-500' }
  if (expPct >= 35)   return { label: '略熱', color: 'text-orange-500' }
  return { label: '適中', color: 'text-blue-600' }
}

export default function MarketThermometer() {
  const [stats, setStats] = useState<Stats | null>(null)

  useEffect(() => {
    fetch('/api/market-stats').then(r => r.json()).then(setStats)
  }, [])

  if (!stats) return <div className="h-16 animate-pulse bg-gray-100 rounded-xl" />

  const { cheap, fair, expensive, total, medianPE } = stats
  const cheapPct  = total > 0 ? (cheap     / total) * 100 : 0
  const fairPct   = total > 0 ? (fair      / total) * 100 : 0
  const expPct    = total > 0 ? (expensive / total) * 100 : 0
  const temp = tempLabel(cheapPct, expPct)

  return (
    <div className="space-y-3">
      {/* 溫度標籤列 */}
      <div className="flex items-center justify-between text-sm">
        <span className={`font-semibold ${temp.color}`}>市場溫度：{temp.label}</span>
        {medianPE != null && (
          <span className="text-gray-400">市場中位數 P/E <strong className="text-gray-700">{medianPE}</strong></span>
        )}
      </div>

      {/* 三色分佈長條 */}
      <div className="flex rounded-full overflow-hidden h-4 w-full bg-gray-100">
        {cheapPct > 0 && (
          <div className="bg-green-400 flex items-center justify-center" style={{ width: `${cheapPct}%` }} />
        )}
        {fairPct > 0 && (
          <div className="bg-blue-300 flex items-center justify-center" style={{ width: `${fairPct}%` }} />
        )}
        {expPct > 0 && (
          <div className="bg-red-400" style={{ width: `${expPct}%` }} />
        )}
      </div>

      {/* 數字說明 */}
      <div className="flex gap-4 text-xs text-gray-500">
        <span><span className="inline-block w-2.5 h-2.5 rounded-full bg-green-400 mr-1" />低估 {cheap} 檔（{cheapPct.toFixed(0)}%）</span>
        <span><span className="inline-block w-2.5 h-2.5 rounded-full bg-blue-300 mr-1" />合理 {fair} 檔（{fairPct.toFixed(0)}%）</span>
        <span><span className="inline-block w-2.5 h-2.5 rounded-full bg-red-400 mr-1" />高估 {expensive} 檔（{expPct.toFixed(0)}%）</span>
        <span className="ml-auto text-gray-400">共 {total} 檔</span>
      </div>
    </div>
  )
}
