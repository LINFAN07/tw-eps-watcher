import { notFound } from 'next/navigation'
import Link from 'next/link'
import { getSupabase } from '@/lib/supabase'
import ValuationCard from '@/components/ValuationCard'
import PERiverChart from '@/components/PERiverChart'
import WatchlistButton from '@/components/WatchlistButton'
import YieldRiverChart from '@/components/YieldRiverChart'
import AltRiverChart from '@/components/AltRiverChart'
import RevenueChart from '@/components/RevenueChart'
import PeerComparison, { type PeerRow } from '@/components/PeerComparison'

interface Props {
  params: Promise<{ code: string }>
  // Next.js 15：searchParams 與 params 同為 Promise，必須 await
  searchParams: Promise<{ model?: string }>
}

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

/**
 * 同產業所有股票的估值基準，供 PeerComparison 計算排名。
 * 最大產業 262 支（電子工業），不會踩到 Supabase 單次 1000 筆上限，故不需分頁。
 */
async function fetchPeers(industry: string | null): Promise<PeerRow[]> {
  if (!industry) return []
  const { data, error } = await getSupabase()
    .from('valuations')
    .select('stock_id,current_price,ttm_eps,pb_book_value,stocks!inner(industry)')
    .eq('stocks.industry', industry)
  // 查詢失敗不可偽裝成「沒有同業」——那會讓整個區塊靜默消失
  if (error) throw new Error(`讀取同業估值失敗：${error.message}`)
  return (data ?? []) as unknown as PeerRow[]
}

async function fetchStock(code: string) {
  const db = getSupabase()
  const [stockRes, valRes, epsRes, pbDate, psDate, pfcfDate, yieldDate,
         capitalRes] = await Promise.all([
    db.from('stocks').select('stock_id,name,market,industry,listed_shares').eq('stock_id', code).single(),
    db.from('valuations').select('*').eq('stock_id', code).single(),
    // 取最近 8 季：前 4 季組成 TTM，後 4 季用來比較去年同期趨勢
    db.from('eps_quarterly').select('quarter_end_date,eps')
      .eq('stock_id', code).order('quarter_end_date', { ascending: false }).limit(8),
    // 各項資料的實際基準日期（顯示在網站上，避免用寫入時間誤導使用者）
    // 股價日期不在此查：現價的來源日直接存在 valuations.price_date
    latestDate(db, 'balance_sheet_quarterly', 'quarter_end_date', code),
    latestDate(db, 'monthly_revenue', 'year_month', code),
    latestDate(db, 'cash_flows_quarterly', 'quarter_end_date', code),
    latestDate(db, 'dividends', 'ex_date', code),
    // 未還原的資本事件（減資／分割／換發）：估值帶在事件那一點跨了兩套股數基準。
    // 個股頁照常顯示該股與數字——那是查詢不是推薦（同 pe_reliable 的處理），
    // 但要讓使用者知道這條帶斷在哪一天。
    db.from('unadjusted_capital_events')
      .select('event_date,share_ratio,adjustable').eq('stock_id', code).order('event_date'),
  ])
  const eps8 = epsRes.data ?? []
  // 同業資料要等 stock 查完才知道產業，故獨立於上面的 Promise.all
  const peers = await fetchPeers(stockRes.data?.industry ?? null)
  return {
    stock: stockRes.data,
    valuation: valRes.data,
    capitalEvents: capitalRes.data ?? [],
    peers,
    ttmQuarters: eps8.slice(0, 4),
    prevYearQuarters: eps8.slice(4, 8),
    asOf: {
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

export default async function StockPage({ params, searchParams }: Props) {
  const { code } = await params
  // ?model=pb：使用者從 P/B 排行榜點進來，估值卡預設顯示該模型
  const { model: fromModel } = await searchParams
  const { stock, valuation, ttmQuarters, prevYearQuarters, asOf, peers, capitalEvents } = await fetchStock(code)

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
          <ValuationCard v={valuation} ttmQuarters={ttmQuarters} prevYearQuarters={prevYearQuarters} industry={stock.industry} asOf={asOf} fromModel={fromModel} capitalEvents={capitalEvents} />
        </div>
      ) : (
        <div className="mb-8 p-6 bg-gray-50 rounded-2xl border text-gray-400 text-center">
          此股票尚無估值資料（EPS 資料不足 4 季）
        </div>
      )}

      {/* 同業相對估值：河流圖只比「這支 vs 它自己的歷史」，這裡補上「vs 同業」 */}
      {stock.industry && peers.length > 0 && (
        <PeerComparison
          peers={peers}
          code={code}
          industry={stock.industry}
          ownFairPe={valuation?.fair_pe ?? null}
          ownFairPb={valuation?.pb_fair_pb ?? null}
        />
      )}

      {/* P/E 河流圖 */}
      <section className="mb-8">
        <h2 className="text-base font-semibold text-gray-700 mb-3">本益比河流圖（10 年）</h2>
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-4">
          <PERiverChart code={code} />
        </div>
        <p className="text-xs text-gray-400 mt-2 px-1">
          綠線：便宜價｜藍線：合理價｜紅線：昂貴價｜黑線：實際收盤價。估值帶會隨每季財報更新而調整。
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
            用過去十年的股價淨值比分布，劃出便宜／合理／昂貴三條線。適合資產型公司（銀行、地產、傳產）。
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
            用過去十年的股價營收比分布，劃出便宜／合理／昂貴三條線。適合有營收但獲利偏低的成長型公司。
            近四季每股營收 {valuation.ps_revenue_per_share} 元。
          </p>
        </section>
      )}

      {/* P/FCF 河流圖（有資料時才顯示） */}
      {valuation?.pfcf_cheap_pfcf && (
        <section className="mb-8">
          <h2 className="text-base font-semibold text-gray-700 mb-3">
            股價自由現金流比河流圖（P/FCF，10 年）
          </h2>
          <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-4">
            <AltRiverChart code={code} model="pfcf" />
          </div>
          <p className="text-xs text-gray-400 mt-2 px-1">
            用過去十年的股價自由現金流比分布，劃出便宜／合理／昂貴三條線。適合帳面獲利被折舊壓低、但現金流充沛的公司（電信、基建）。
            近四季每股自由現金流 {valuation.pfcf_per_share?.toFixed(1)} 元。
          </p>
        </section>
      )}

      {/* 月營收與年增率。
          放在所有估值帶之後：上面五段回答「現在貴不貴」，這一段回答「生意在成長嗎」，
          是不同的問題。它也是全頁唯一每月更新的資料，其餘都要等財報。 */}
      <section>
        <h2 className="text-base font-semibold text-gray-700 mb-3">月營收與年增率（近 3 年）</h2>
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-4">
          <RevenueChart code={code} />
        </div>
        <p className="text-xs text-gray-400 mt-2 px-1">
          藍柱：當月營收｜橘線：與去年同月相比的年增率。營收領先財報約一個半月，是最快看到經營變化的數字，
          但單月易受出貨節奏影響，累計年增率較能看出趨勢。
          證券、保險、建設等業別的單月營收可能為負（含評價損益、退屋沖銷），
          去年同期為零或負數時年增率不適用，圖上會斷開而不是畫成 0。
        </p>
      </section>
    </main>
  )
}
