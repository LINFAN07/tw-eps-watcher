import Link from 'next/link'
import { getSupabase } from '@/lib/supabase'
import { isPeUnreliable } from '@/lib/peReliability'
import { fetchUnadjusted } from '@/components/CheapLeaderboard'
import ScreenerClient, { type ScreenerRow } from '@/components/ScreenerClient'

export const metadata = { title: '條件篩選 | 台股估值' }

// 不加這行會在建置時就靜態產生，價格與估值狀態從此凍結在部署那一刻。
// 與首頁排行榜同步（每小時），股價本來就只在收盤後更新一次。
export const revalidate = 3600

const PAGE = 1000

/**
 * 條件篩選器。
 *
 * 排行榜回答「哪些最便宜」，這一頁回答「符合我這組條件的有哪些」——
 * 先前這些條件散在排行榜的幾個 checkbox 裡，而且只能在「已經是便宜」的
 * 子集上篩。
 *
 * ## 為什麼一次把全市場送到瀏覽器
 *
 * 篩選要在整個母體上做，不能只送前 N 名。約 2,400 列 × 十來個數值欄位，
 * 換來的是改條件不必來回請求。每一列都在伺服器端先算好衍生值（ROE、殖利率、
 * 市值、可靠性旗標），瀏覽器只做比大小——判讀規則因此仍只有一份，
 * 不會在前端長出第二套 `isPeUnreliable`。
 *
 * ## 這一頁沿用排行榜的三道排除，不重新發明
 *
 * 已下市（價格凍結、折價越算越誇張）、未還原資本事件（估值帶跨兩套股數基準）、
 * 估值失真（`pe_reliable` / `pe_deep_discount` / `pb_reliable`）。
 * 前兩者直接不進母體；第三者做成可關的開關並預設開啟——
 * 使用者要看全部是他的自由，但預設不該把已知失真的目標價端上桌。
 */
async function fetchAll(): Promise<ScreenerRow[]> {
  const db = getSupabase()
  const excluded = await fetchUnadjusted(db)

  const raw: Record<string, unknown>[] = []
  for (let offset = 0; ; offset += PAGE) {
    const { data, error } = await db.from('valuations')
      .select(
        'stock_id,current_price,status,pb_status,ps_status,pfcf_status,yield_status,'
        + 'ttm_eps,pb_book_value,operating_margin,debt_ratio,yield_ttm_div,'
        + 'pe_reliable,pe_deep_discount,pb_reliable,warning,nonop_warning,'
        + 'stocks!inner(name,industry,listed_shares)')
      .gt('current_price', 0)
      .is('stocks.delisted_at', null)
      .order('stock_id')
      .range(offset, offset + PAGE - 1)
    // 故障要拋出，不可吞成空清單——那會讓整頁看起來像「沒有符合條件的股票」
    if (error) throw new Error(`篩選器查詢失敗：${error.message}`)
    if (!data) break
    raw.push(...(data as unknown as Record<string, unknown>[]))
    if (data.length < PAGE) break
  }

  const num = (v: unknown) => (v == null ? null : Number(v))

  return raw
    .filter(r => !excluded.has(r.stock_id as string))
    .map(r => {
      const stock = r.stocks as { name: string; industry: string | null; listed_shares: number | null }
      const price = Number(r.current_price)
      const eps = num(r.ttm_eps)
      const bvps = num(r.pb_book_value)
      const div = num(r.yield_ttm_div)
      const shares = num(stock?.listed_shares)
      return {
        code:     r.stock_id as string,
        name:     stock?.name ?? '',
        industry: stock?.industry ?? null,
        price,
        // ROE 由 TTM EPS ÷ 每股淨值推得（同 ValuationCard）；淨值 ≤ 0 時無意義
        roe:      eps != null && bvps != null && bvps > 0 ? +(eps / bvps * 100).toFixed(1) : null,
        margin:   num(r.operating_margin),
        debt:     num(r.debt_ratio),
        // 殖利率用【原始價】而非還原價：它本質是「實際買價換到多少股利」
        yieldPct: div != null && div > 0 ? +(div / price * 100).toFixed(2) : null,
        // 市值（億元）。listed_shares 單位是千股
        capYi:    shares != null && shares > 0 ? +(shares * 1000 * price / 1e8).toFixed(1) : null,
        pe:       (r.status as string | null) ?? null,
        pb:       (r.pb_status as string | null) ?? null,
        ps:       (r.ps_status as string | null) ?? null,
        pfcf:     (r.pfcf_status as string | null) ?? null,
        div_:     (r.yield_status as string | null) ?? null,
        // 判讀規則留在伺服器端，前端只拿布林值——否則遲早會長出第二套 isPeUnreliable
        peBad:    isPeUnreliable({
          pe_reliable:      r.pe_reliable as boolean | null,
          pe_deep_discount: r.pe_deep_discount as boolean | null,
          warning:          r.warning as string | null,
          nonop_warning:    r.nonop_warning as string | null,
        }),
        pbBad:    r.pb_reliable === false,
      }
    })
}

export default async function ScreenerPage() {
  const rows = await fetchAll()
  const industries = [...new Set(rows.map(r => r.industry).filter(Boolean))].sort() as string[]

  return (
    <main className="max-w-6xl mx-auto px-4 py-10">
      <Link href="/" className="text-sm text-gray-400 hover:text-gray-700 mb-6 inline-block">
        ← 返回搜尋
      </Link>
      <h1 className="text-2xl font-bold mb-1">條件篩選</h1>
      <p className="text-sm text-gray-500 mb-6">
        全市場 {rows.length} 支（已排除下市與資本事件未還原者）。
        這是查詢工具，符合條件不代表值得買——各模型的歷史實績請看
        <Link href="/backtest" className="text-blue-600 hover:underline mx-1">模型體檢報告</Link>。
      </p>
      <ScreenerClient rows={rows} industries={industries} />
    </main>
  )
}
