import { Suspense } from 'react'
import Link from 'next/link'
import SearchBox from '@/components/SearchBox'
import CheapLeaderboard from '@/components/CheapLeaderboard'
import WatchlistPanel from '@/components/WatchlistPanel'
import MarketThermometer from '@/components/MarketThermometer'

export const revalidate = 3600 // 每小時重新抓一次排行榜

export default function Home() {
  return (
    <main className="max-w-4xl mx-auto px-4 py-8 md:py-12">
      {/* 標題 */}
      <div className="text-center mb-8 md:mb-10">
        <h1 className="text-2xl md:text-3xl font-bold text-gray-900 mb-2">台股估值查詢</h1>
        <p className="text-gray-500"><span className="font-medium text-gray-700">「多模型估值」</span>找出台股的真實價值</p>
      </div>

      {/* 搜尋框 */}
      <div className="mb-10 md:mb-14">
        <SearchBox />
      </div>

      {/* 市場溫度計 */}
      <section className="mb-10 md:mb-14">
        <h2 className="text-lg font-semibold text-gray-800 mb-4 flex items-center gap-2">
          <span className="w-2 h-5 bg-blue-400 rounded-full inline-block" />
          市場溫度計
        </h2>
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
          <MarketThermometer />
        </div>
      </section>

      {/* 自選股清單 */}
      <section className="mb-10 md:mb-14">
        <h2 className="text-lg font-semibold text-gray-800 mb-4 flex items-center gap-2">
          <span className="w-2 h-5 bg-yellow-400 rounded-full inline-block" />
          我的自選股
        </h2>
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
          <WatchlistPanel />
        </div>
      </section>

      {/* 便宜股排行榜 */}
      <section>
        <div className="flex items-baseline justify-between mb-4 gap-2 flex-wrap">
          <h2 className="text-lg font-semibold text-gray-800 flex items-center gap-2">
            <span className="w-2 h-5 bg-green-500 rounded-full inline-block" />
            目前被低估的股票
          </h2>
          <Link href="/backtest" className="text-xs text-blue-600 hover:underline">
            這些訊號準不準？看模型體檢報告 →
          </Link>
        </div>
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
          <Suspense fallback={<p className="text-gray-400 text-sm">載入中...</p>}>
            <CheapLeaderboard />
          </Suspense>
        </div>
      </section>

      <footer className="mt-12 pt-6 border-t border-gray-100 flex gap-4 justify-center text-xs text-gray-400">
        <Link href="/screener" className="hover:text-gray-600">條件篩選</Link>
        <span>·</span>
        <Link href="/report" className="hover:text-gray-600">每日市場快報</Link>
        <span>·</span>
        <Link href="/backtest" className="hover:text-gray-600">模型體檢報告</Link>
        <span>·</span>
        <Link href="/health" className="hover:text-gray-600">資料健康狀態</Link>
      </footer>
    </main>
  )
}
