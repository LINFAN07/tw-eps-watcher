import { notFound } from 'next/navigation'
import Link from 'next/link'
import { getSupabase } from '@/lib/supabase'
import ValuationCard from '@/components/ValuationCard'
import PERiverChart from '@/components/PERiverChart'
import WatchlistButton from '@/components/WatchlistButton'
import YieldRiverChart from '@/components/YieldRiverChart'
import AltRiverChart from '@/components/AltRiverChart'

interface Props { params: Promise<{ code: string }> }

export async function generateMetadata({ params }: Props) {
  const { code } = await params
  return { title: `${code} 估值查詢 | 台股估值` }
}

// 取某張表某支股票的「最新一筆日期」，用來標示各項資料的實際基準日。
// 單股 + order + limit(1) 走主鍵前綴，很快。
async function latestDate(
  db: ReturnType<typeof getSupabase>, table: string, dateCol: string, code: string,
): Promise<string | null> {
  const { data } = await db.from(table).select(dateCol)
    .eq('stock_id', code).order(dateCol, { ascending: false }).limit(1).single()
  return (data as Record<string, string> | null)?.[dateCol] ?? null
}

async function fetchStock(code: string) {
  const db = getSupabase()
  const [stockRes, valRes, epsRes, priceDate, pbDate, psDate, pfcfDate, yieldDate] = await Promise.all([
    db.from('stocks').select('stock_id,name,market,industry,listed_shares').eq('stock_id', code).single(),
    db.from('valuations').select('*').eq('stock_id', code).single(),
    // 取最近 8 季：前 4 季組成 TTM，後 4 季用來比較去年同期趨勢
    db.from('eps_quarterly').select('quarter_end_date,eps')
      .eq('stock_id', code).order('quarter_end_date', { ascending: false }).limit(8),
    // 各項資料的實際基準日期（顯示在網站上，避免用寫入時間誤導使用者）
    latestDate(db, 'daily_prices', 'date', code),
    latestDate(db, 'balance_sheet_quarterly', 'quarter_end_date', code),
    latestDate(db, 'monthly_revenue', 'year_month', code),
    latestDate(db, 'cash_flows_quarterly', 'quarter_end_date', code),
    latestDate(db, 'dividends', 'ex_date', code),
  ])
  const eps8 = epsRes.data ?? []
  return {
    stock: stockRes.data,
    valuation: valRes.data,
    ttmQuarters: eps8.slice(0, 4),
    prevYearQuarters: eps8.slice(4, 8),
    asOf: {
      price: priceDate,
      pe:    eps8[0]?.quarter_end_date ?? null,
      pb:    pbDate,
      ps:    psDate,
      pfcf:  pfcfDate,
      yield: yieldDate,
    },
  }
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
  const { stock, valuation, ttmQuarters, prevYearQuarters, asOf } = await fetchStock(code)

  if (!stock) notFound()

  return (
    <main className="max-w-4xl mx-auto px-4 py-10">
      {/* 返回首頁 */}
      <Link href="/" className="text-sm text-gray-400 hover:text-gray-700 mb-6 inline-block">
        ← 返回搜尋
      </Link>

      {/* 股票標頭 */}
      <div className="mb-6">
        <div className="flex items-start justify-between gap-4 flex-wrap">
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
          <WatchlistButton code={code} />
        </div>
      </div>

      {/* 估值卡片 */}
      {valuation ? (
        <div className="mb-8">
          <ValuationCard v={valuation} ttmQuarters={ttmQuarters} prevYearQuarters={prevYearQuarters} industry={stock.industry} asOf={asOf} />
        </div>
      ) : (
        <div className="mb-8 p-6 bg-gray-50 rounded-2xl border text-gray-400 text-center">
          此股票尚無估值資料（EPS 資料不足 4 季）
        </div>
      )}

      {/* P/E 河流圖 */}
      <section className="mb-8">
        <h2 className="text-base font-semibold text-gray-700 mb-3">本益比河流圖（10 年）</h2>
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-4">
          <PERiverChart code={code} />
        </div>
        <p className="text-xs text-gray-400 mt-2 px-1">
          綠線：便宜價｜藍線：合理價｜紅線：昂貴價｜黑線：實際收盤價。P/E 帶依每季 TTM EPS 動態調整。
        </p>
      </section>

      {/* 殖利率河流圖 */}
      <section className="mb-8">
        <h2 className="text-base font-semibold text-gray-700 mb-3">殖利率河流圖（10 年）</h2>
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-4">
          <YieldRiverChart code={code} />
        </div>
        <p className="text-xs text-gray-400 mt-2 px-1">
          綠線：高殖利率（便宜）｜藍線：中殖利率（合理）｜紅線：低殖利率（昂貴）｜黑線：實際收盤價。殖利率愈高代表股價相對便宜。
        </p>
      </section>

      {/* P/B 河流圖（有資料時才顯示） */}
      {valuation?.pb_cheap_pb && (
        <section className="mb-8">
          <h2 className="text-base font-semibold text-gray-700 mb-3">
            股價淨值比河流圖（P/B，10 年）
          </h2>
          <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-4">
            <AltRiverChart code={code} model="pb" />
          </div>
          <p className="text-xs text-gray-400 mt-2 px-1">
            以歷史 P/B 20/50/80 百分位為估值帶，適合資產型公司（銀行、地產、傳產）。
            每股淨值 {valuation.pb_book_value} 元。
          </p>
        </section>
      )}

      {/* P/S 河流圖（有資料時才顯示） */}
      {valuation?.ps_cheap_ps && (
        <section className="mb-8">
          <h2 className="text-base font-semibold text-gray-700 mb-3">
            股價營收比河流圖（P/S，10 年）
          </h2>
          <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-4">
            <AltRiverChart code={code} model="ps" />
          </div>
          <p className="text-xs text-gray-400 mt-2 px-1">
            以歷史 P/S 20/50/80 百分位為估值帶，適合有營收但 EPS 偏低的成長型公司。
            TTM 每股營收 {valuation.ps_revenue_per_share} 元。
          </p>
        </section>
      )}

      {/* P/FCF 河流圖（有資料時才顯示） */}
      {valuation?.pfcf_cheap_pfcf && (
        <section>
          <h2 className="text-base font-semibold text-gray-700 mb-3">
            股價自由現金流比河流圖（P/FCF，10 年）
          </h2>
          <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-4">
            <AltRiverChart code={code} model="pfcf" />
          </div>
          <p className="text-xs text-gray-400 mt-2 px-1">
            以歷史 P/FCF 20/50/80 百分位為估值帶，適合帳面獲利被折舊壓低但現金流充沛的公司（電信、基建）。
            TTM 每股 FCF {valuation.pfcf_per_share?.toFixed(1)} 元。
          </p>
        </section>
      )}
    </main>
  )
}
