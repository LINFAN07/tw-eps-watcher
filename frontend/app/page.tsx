import { Suspense } from 'react'
import SearchBox from '@/components/SearchBox'
import CheapLeaderboard from '@/components/CheapLeaderboard'

export const revalidate = 3600 // 每小時重新抓一次排行榜

export default function Home() {
  return (
    <main className="max-w-4xl mx-auto px-4 py-12">
      {/* 標題 */}
      <div className="text-center mb-10">
        <h1 className="text-3xl font-bold text-gray-900 mb-2">台股估值查詢</h1>
        <p className="text-gray-500">以本益比河流圖判斷股價是否被低估或高估</p>
      </div>

      {/* 搜尋框 */}
      <div className="mb-14">
        <SearchBox />
      </div>

      {/* 便宜股排行榜 */}
      <section>
        <h2 className="text-lg font-semibold text-gray-800 mb-4 flex items-center gap-2">
          <span className="w-2 h-5 bg-green-500 rounded-full inline-block" />
          目前被低估的股票
        </h2>
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
          <Suspense fallback={<p className="text-gray-400 text-sm">載入中...</p>}>
            <CheapLeaderboard />
          </Suspense>
        </div>
      </section>
    </main>
  )
}
