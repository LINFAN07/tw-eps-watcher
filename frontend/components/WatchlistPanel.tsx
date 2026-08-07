'use client'
import { useEffect, useState } from 'react'
import Link from 'next/link'
import { useWatchlist } from '@/hooks/useWatchlist'
import { expensiveCaveat } from '@/lib/expensiveBacktest'
import { isPeUnreliable } from '@/lib/peReliability'

interface WatchItem {
  stock_id: string
  current_price: number
  status: string
  cheap_price: number
  fair_price: number | null
  expensive_price: number | null
  warning?: string | null
  nonop_warning?: string | null
  pe_reliable?: boolean | null
  pe_deep_discount?: boolean | null
  stocks: { name: string } | null
}

const statusStyle: Record<string, string> = {
  '便宜': 'text-green-700 bg-green-100',
  '合理': 'text-blue-700 bg-blue-100',
  '昂貴': 'text-red-700 bg-red-100',
}

/**
 * 便宜／合理／昂貴三個錨點在位置條上的固定位置（%）。
 *
 * 這是**畫面座標**（CSS left），與後端估值帶的第 20/50/80 統計百分位無關——
 * 中間值同為 50 是巧合。bandPosition() 是分段線性映射，跟那三個分位數沒有算術關係。
 */
const ANCHORS = [10, 50, 90] as const

/**
 * 把現價映射到位置條上的百分比位置。
 *
 * 用分段線性而非單一線性：便宜→合理與合理→昂貴這兩段在價格上的跨度
 * 往往差好幾倍，單一線性會把大多數股票的點擠在同一小段，看不出差別。
 *
 * 超出兩端者夾在 2%~98%，避免點跑出條外。夾住的只是**顯示位置**，
 * 實際離便宜價多遠另外用數字表示，不會因此看不出「遠超昂貴價」。
 *
 * 三條帶不成立時回傳 null（不畫），不用推估值頂替——缺的就是缺的。
 */
function bandPosition(price: number, cheap: number, fair: number, expensive: number): number | null {
  if (!(cheap > 0 && fair > cheap && expensive > fair)) return null
  const [lo, mid, hi] = ANCHORS
  if (price <= cheap)     return Math.max(2, lo * (price / cheap))
  if (price <= fair)      return lo + (mid - lo) * (price - cheap) / (fair - cheap)
  if (price <= expensive) return mid + (hi - mid) * (price - fair) / (expensive - fair)
  return Math.min(98, hi + 8 * (price - expensive) / expensive)
}

/** 現價離便宜價還有多遠（%）。負值代表已低於便宜價。 */
function gapToCheap(price: number, cheap: number): number {
  return ((price - cheap) / cheap) * 100
}

function BandBar({ item, unreliable }: { item: WatchItem; unreliable: boolean }) {
  const { current_price: price, cheap_price: cheap, fair_price: fair, expensive_price: expensive } = item
  if (fair == null || expensive == null) return null
  const pos = bandPosition(price, cheap, fair, expensive)
  if (pos == null) return null

  // 帶本身失真時一律灰階：綠→紅的漸層是在說「左邊便宜、右邊貴」，
  // 而這正是該股不成立的部分。照畫顏色等於用視覺蓋掉資料的不確定性。
  const track = unreliable ? 'bg-gray-100' : 'bg-gradient-to-r from-green-100 via-gray-100 to-red-100'
  const dotColor = unreliable ? 'bg-gray-400'
    : price <= cheap ? 'bg-green-500' : price >= expensive ? 'bg-red-500' : 'bg-blue-500'
  // 標籤與價格同一筆資料，不靠兩個陣列的順序默契配對
  const anchors = [
    { label: '便宜', at: ANCHORS[0], value: cheap },
    { label: '合理', at: ANCHORS[1], value: fair },
    { label: '昂貴', at: ANCHORS[2], value: expensive },
  ]

  return (
    <div className="mt-2 pl-14 pr-7">
      <div className={`h-1.5 rounded-full relative ${track}`}>
        {/* 三個錨點的刻度 */}
        {anchors.map(({ at }) => (
          <span key={at} className="absolute top-0 h-full w-px bg-gray-300" style={{ left: `${at}%` }} />
        ))}
        <span
          className={`absolute top-1/2 -translate-y-1/2 -translate-x-1/2 w-2.5 h-2.5 rounded-full border-2 border-white shadow ${dotColor}`}
          style={{ left: `${pos}%` }}
        />
      </div>
      <div className={`relative h-4 mt-1 text-[10px] ${unreliable ? 'text-gray-300' : 'text-gray-400'}`}>
        {anchors.map(({ at, label, value }) => (
          <span key={at} className="absolute -translate-x-1/2 whitespace-nowrap" style={{ left: `${at}%` }}>
            {label} {value}
          </span>
        ))}
      </div>
    </div>
  )
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

  // 依 codes 的順序取出有資料的項目（保留使用者加入自選的順序）
  const byId = new Map(items.map(i => [i.stock_id, i]))
  const shown = codes.map(c => byId.get(c)).filter(i => i != null)
  const hasExpensive  = shown.some(i => i.status === '昂貴')
  const hasUnreliable = shown.some(isPeUnreliable)

  return (
    <div className="space-y-2">
      {shown.map(item => {
        const code = item.stock_id
        const gap = item.cheap_price > 0 ? gapToCheap(item.current_price, item.cheap_price) : null
        const unreliable = isPeUnreliable(item)

        return (
          <div key={code} className="p-3 rounded-xl bg-gray-50 hover:bg-gray-100 transition-colors">
            <div className="flex items-center gap-3">
              <Link href={`/stock/${code}`} className="flex-1 flex items-center gap-3 min-w-0">
                <span className="font-mono font-bold text-blue-600 w-14 shrink-0">{code}</span>
                <span className="text-gray-700 truncate">{item.stocks?.name ?? '—'}</span>
                <span className="ml-auto shrink-0 text-gray-600 font-medium">{item.current_price}</span>
                {gap != null && (
                  <span
                    className={`shrink-0 text-xs font-semibold ${gap <= 0 ? 'text-green-600' : 'text-gray-500'}`}
                    title="現價離這支股票自己歷史便宜價的距離"
                  >
                    {gap <= 0 ? '↓' : '+'}{Math.abs(gap).toFixed(0)}%
                  </span>
                )}
                {unreliable && (
                  <span
                    className="shrink-0 text-xs text-amber-500"
                    title={item.warning ?? item.nonop_warning ?? '這支股票的歷史估值帶已不適用，位置僅供參考'}
                  >
                    ⚠
                  </span>
                )}
                {/*
                  失真股的徽章維持原色，只加 ⚠——與 ValuationCard 和個股頁一致
                  （兩處都是「照常上色 + 另掛警示」，榜單則是整列排除）。
                  就地改成灰色會讓同一支股票在個股頁是紅色「昂貴」、在這裡是灰色，
                  且警示已經講過一次，用顏色再講一次是雙重懲罰。
                */}
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
            <BandBar item={item} unreliable={unreliable} />
          </div>
        )
      })}

      {/*
        說明文字整個面板只出現一次：持股裡昂貴與失真的比例本來就高，
        逐列掛同一句話是雜訊（同 2026-08-05 從排行榜移除還原標籤的理由）
      */}
      <p className="text-[11px] text-gray-400 leading-relaxed pt-1">
        位置條顯示現價落在這支股票自己歷史估值帶的哪個位置，百分比為離便宜價的距離。
        {hasUnreliable && <><br />⚠ 者的歷史估值帶已不適用（獲利太小、劇烈波動或有一次性收益），位置條轉為灰階、僅供查詢，滑過看原因。</>}
        {hasExpensive && <><br />{expensiveCaveat()}</>}
      </p>
    </div>
  )
}
