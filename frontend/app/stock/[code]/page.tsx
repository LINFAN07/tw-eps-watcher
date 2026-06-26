import { notFound } from 'next/navigation'
import Link from 'next/link'
import { getSupabase } from '@/lib/supabase'
import ValuationCard from '@/components/ValuationCard'
import PERiverChart from '@/components/PERiverChart'

interface Props { params: Promise<{ code: string }> }

export async function generateMetadata({ params }: Props) {
  const { code } = await params
  return { title: `${code} 估值查詢 | 台股估值` }
}

async function fetchStock(code: string) {
  const db = getSupabase()
  const [stockRes, valRes] = await Promise.all([
    db.from('stocks').select('stock_id,name,market,industry').eq('stock_id', code).single(),
    db.from('valuations').select('*').eq('stock_id', code).single(),
  ])
  return { stock: stockRes.data, valuation: valRes.data }
}

const marketLabel: Record<string, string> = {
  TWSE: '上市', TPEx: '上櫃', tse: '上市', otc: '上櫃',
  '上市': '上市', '上櫃': '上櫃',
}
const statusStyle: Record<string, string> = {
  '便宜': 'text-green-600', '合理': 'text-blue-600', '昂貴': 'text-red-600',
}

export default async function StockPage({ params }: Props) {
  const { code } = await params
  const { stock, valuation } = await fetchStock(code)

  if (!stock) notFound()

  return (
    <main className="max-w-4xl mx-auto px-4 py-10">
      {/* 返回首頁 */}
      <Link href="/" className="text-sm text-gray-400 hover:text-gray-700 mb-6 inline-block">
        ← 返回搜尋
      </Link>

      {/* 股票標頭 */}
      <div className="mb-6">
        <div className="flex items-baseline gap-3 flex-wrap">
          <h1 className="text-2xl font-bold">{stock.name}</h1>
          <span className="font-mono text-lg text-gray-500">{stock.stock_id}</span>
          {(marketLabel[stock.market]) && (
            <span className="text-sm px-2 py-0.5 bg-gray-100 text-gray-600 rounded-full">
              {marketLabel[stock.market]}
            </span>
          )}
          {stock.industry && (
            <span className="text-sm px-2 py-0.5 bg-blue-50 text-blue-600 rounded-full">
              {stock.industry}
            </span>
          )}
          {valuation?.status && (
            <span className={`text-sm font-semibold ${statusStyle[valuation.status] ?? 'text-gray-500'}`}>
              {valuation.status}
            </span>
          )}
        </div>
      </div>

      {/* 估值卡片 */}
      {valuation ? (
        <div className="mb-8">
          <ValuationCard v={valuation} />
        </div>
      ) : (
        <div className="mb-8 p-6 bg-gray-50 rounded-2xl border text-gray-400 text-center">
          此股票尚無估值資料（EPS 資料不足 4 季）
        </div>
      )}

      {/* P/E 河流圖 */}
      <section>
        <h2 className="text-base font-semibold text-gray-700 mb-3">本益比河流圖（10 年）</h2>
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-4">
          <PERiverChart code={code} />
        </div>
        <p className="text-xs text-gray-400 mt-2 px-1">
          綠線：便宜價｜藍線：合理價｜紅線：昂貴價｜黑線：實際收盤價。P/E 帶依每季 TTM EPS 動態調整。
        </p>
      </section>
    </main>
  )
}
