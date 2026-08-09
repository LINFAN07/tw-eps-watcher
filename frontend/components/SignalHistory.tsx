'use client'

import { useEffect, useState } from 'react'

interface Episode {
  startMonth: string
  endMonth: string
  months: number
  priceAtStart: number
  cheapAtStart: number
  forwardMonth: string | null
  forwardReturn: number | null
}

interface Summary {
  firstMonth: string
  lastMonth: string
  evaluated: boolean
  ongoing: boolean
  horizonMonths: number
}

const ym = (m: string) => m.replace('-', '/')

/** 台股慣例：漲紅跌綠 */
const tone = (v: number) => (v > 0 ? 'text-red-600' : v < 0 ? 'text-green-600' : 'text-gray-600')

export default function SignalHistory({ code }: { code: string }) {
  const [episodes, setEpisodes] = useState<Episode[]>([])
  const [summary, setSummary]   = useState<Summary | null>(null)
  const [loading, setLoading]   = useState(true)
  const [error, setError]       = useState('')

  useEffect(() => {
    fetch(`/api/signals/${code}`)
      .then(r => r.json())
      .then(d => {
        if (d.error) { setError(d.error); return }
        setEpisodes(d.episodes)
        setSummary(d.summary)
      })
      .catch(() => setError('載入失敗'))
      .finally(() => setLoading(false))
  }, [code])

  if (loading)
    return <div className="h-24 flex items-center justify-center text-gray-400">載入中...</div>

  if (error || !summary)
    return (
      <div className="h-24 flex items-center justify-center text-gray-400 text-sm px-4 text-center">
        {error === 'NO_EPS' ? '此股票無 EPS 紀錄，無法重算歷史訊號'
          : error === 'NO_PRICE' ? '此股票無股價紀錄'
          : error || '資料不足'}
      </div>
    )

  // 「資料不足以建立百分位帶」與「算得出來但從未便宜」是兩件事，不可混為一談
  if (!summary.evaluated)
    return (
      <div className="py-6 text-center text-sm text-gray-400">
        歷史樣本不足兩年，無法以當時的資料重建估值帶
      </div>
    )

  if (episodes.length === 0)
    return (
      <div className="py-6 text-center text-sm text-gray-500">
        {ym(summary.firstMonth)} 以來，這支股票不曾被判為「便宜」。
      </div>
    )

  const settled = episodes.filter(e => e.forwardReturn !== null)

  return (
    <div>
      <p className="text-sm text-gray-600 mb-3">
        {ym(summary.firstMonth)} 以來共 <strong>{episodes.length}</strong> 段被判為便宜
        {summary.ongoing && <span className="text-green-600 font-medium">（最後一段延續至今）</span>}
      </p>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-gray-400 border-b">
              <th className="pb-2 pr-4 font-medium">期間</th>
              <th className="pb-2 pr-4 font-medium text-right">持續</th>
              <th className="pb-2 pr-4 font-medium text-right">當時股價</th>
              <th className="pb-2 pr-4 font-medium text-right hidden sm:table-cell">當時便宜價</th>
              <th className="pb-2 font-medium text-right">
                {summary.horizonMonths} 個月後含息報酬
              </th>
            </tr>
          </thead>
          <tbody>
            {episodes.map(e => (
              <tr key={e.startMonth} className="border-b border-gray-50">
                <td className="py-2.5 pr-4 font-mono text-gray-700">
                  {ym(e.startMonth)}{e.months > 1 && ` ~ ${ym(e.endMonth)}`}
                </td>
                <td className="py-2.5 pr-4 text-right text-gray-500">{e.months} 個月</td>
                <td className="py-2.5 pr-4 text-right text-gray-700">{e.priceAtStart}</td>
                <td className="py-2.5 pr-4 text-right text-gray-400 hidden sm:table-cell">
                  {e.cheapAtStart}
                </td>
                <td className="py-2.5 text-right">
                  {e.forwardReturn === null
                    ? <span className="text-gray-400">尚未滿 {summary.horizonMonths} 個月</span>
                    : <strong className={tone(e.forwardReturn)}>
                        {e.forwardReturn > 0 ? '+' : ''}{e.forwardReturn}%
                      </strong>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* 刻意不給中位數或勝率：{settled.length} 段算不出有意義的統計量，
          給了只會讓人把它當預測。這裡列的是事實，不是實績。 */}
      <p className="text-xs text-gray-400 mt-3 leading-relaxed">
        以<strong>當時可得的資料</strong>重算：時點的估值帶只用該時點之前的樣本，
        財報一律以申報期限為可用日（不是季末日）。這與河流圖不同——河流圖的便宜線
        是用今天算出的倍數回頭套，看起來像「當時很便宜」的位置未必是當時的判斷。
        <br />
        報酬為含息（以除權息還原價計算）。
        {settled.length > 0 && `已滿期的只有 ${settled.length} 段——`}
        段數這麼少算不出有意義的中位數或勝率，
        <strong>這是這支股票的歷史紀錄，不是對未來的預測</strong>。
        另外此處採月採樣，估值卡的「目前狀態」採週採樣，最近一段可能略有出入。
      </p>
    </div>
  )
}
