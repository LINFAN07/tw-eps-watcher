import { getSupabase } from '@/lib/supabase'
import CheapLeaderboardClient, { type LeaderboardRow, type LeaderboardData } from './CheapLeaderboardClient'

// P/E 特有：這兩種警告代表估值模型失真，不應出現在 P/E 排行榜
const UNRELIABLE_WARNINGS = ['EPS 長期偏低', '顯著高於長期均值']

const PAGE = 1000

async function fetchModel(
  db: ReturnType<typeof getSupabase>,
  model: 'pe' | 'pb' | 'ps' | 'pfcf'
): Promise<LeaderboardRow[]> {
  const statusCol = model === 'pe' ? 'status' : `${model}_status`
  const priceCol  = model === 'pe' ? 'cheap_price' : `${model}_cheap_price`
  const peExtra   = model === 'pe' ? ',warning,nonop_warning' : ''
  const selectFields = `stock_id,current_price,${priceCol},ttm_eps,pb_book_value,operating_margin${peExtra},stocks(name,industry,market)`

  // 排序鍵（現價 ÷ 便宜價）是計算值，資料庫無法排序，必須取回完整候選再排。
  // 原本只取前 200 筆，但「便宜」股最多達 525 支（P/B），
  // 導致排行榜是從任意子集挑出的前 50 名，而非真正的前 50。
  const data: Record<string, unknown>[] = []
  for (let offset = 0; ; offset += PAGE) {
    const { data: page, error } = await db.from('valuations')
      .select(selectFields)
      .eq(statusCol, '便宜')
      .gt('current_price', 0)
      .not(priceCol, 'is', null)
      .order('stock_id')   // 固定排序，確保跨頁不重複、不遺漏
      .range(offset, offset + PAGE - 1)
    if (error || !page) return []
    data.push(...(page as unknown as Record<string, unknown>[]))
    if (page.length < PAGE) break
  }

  let rows: LeaderboardRow[] = data.map(r => ({
    stock_id:         r.stock_id as string,
    current_price:    Number(r.current_price),
    cheap_price:      Number(r[priceCol]),
    warning:          (r.warning as string | null) ?? null,
    ttm_eps:          r.ttm_eps != null ? Number(r.ttm_eps) : null,
    pb_book_value:    r.pb_book_value != null ? Number(r.pb_book_value) : null,
    operating_margin: r.operating_margin != null ? Number(r.operating_margin) : null,
    stocks:           r.stocks as { name: string; industry: string; market: string } | null,
  }))

  if (model === 'pe') {
    rows = rows
      .filter(r => !r.warning || !UNRELIABLE_WARNINGS.some(kw => r.warning!.includes(kw)))
      .filter(r => !r.nonop_warning)
  }

  return rows
    .sort((a, b) => (a.current_price / a.cheap_price) - (b.current_price / b.cheap_price))
    .slice(0, 50)
}

async function fetchConsensus(db: ReturnType<typeof getSupabase>): Promise<LeaderboardRow[]> {
  const fields = [
    'stock_id', 'current_price',
    'status', 'cheap_price', 'warning', 'nonop_warning',
    'pb_status', 'pb_cheap_price',
    'ps_status', 'ps_cheap_price',
    'pfcf_status', 'pfcf_cheap_price',
    'ttm_eps', 'pb_book_value', 'operating_margin',
    'stocks(name,industry,market)',
  ].join(',')

  // 逐頁取到底，不寫死批次數（全市場已達 2238 支，原本寫死兩批會漏掉尾端）。
  // 兩次獨立查詢若未指定 order，Postgres 不保證跨查詢順序一致，可能重複或遺漏。
  const all: Record<string, unknown>[] = []
  for (let offset = 0; ; offset += PAGE) {
    const { data: page, error } = await db.from('valuations')
      .select(fields)
      .gt('current_price', 0)
      .order('stock_id')
      .range(offset, offset + PAGE - 1)
    if (error || !page) break
    all.push(...(page as unknown as Record<string, unknown>[]))
    if (page.length < PAGE) break
  }

  const rows: LeaderboardRow[] = []

  for (const r of all) {
    const warning = (r.warning as string | null) ?? null

    // P/E 需額外排除不可靠警告
    const peValid = r.status === '便宜'
      && r.cheap_price != null
      && !r.nonop_warning
      && (!warning || !UNRELIABLE_WARNINGS.some(kw => warning.includes(kw)))

    const models: string[] = []
    if (peValid)                                                    models.push('P/E')
    if (r.pb_status   === '便宜' && r.pb_cheap_price   != null)    models.push('P/B')
    if (r.ps_status   === '便宜' && r.ps_cheap_price   != null)    models.push('P/S')
    if (r.pfcf_status === '便宜' && r.pfcf_cheap_price != null)    models.push('P/FCF')

    if (models.length < 2) continue

    // 以 P/E 便宜價為參考，依序 fallback
    const cheapPrice = peValid                   ? Number(r.cheap_price)
      : r.pb_cheap_price   != null               ? Number(r.pb_cheap_price)
      : r.ps_cheap_price   != null               ? Number(r.ps_cheap_price)
      : Number(r.pfcf_cheap_price)

    rows.push({
      stock_id:         r.stock_id as string,
      current_price:    Number(r.current_price),
      cheap_price:      cheapPrice,
      warning,
      ttm_eps:          r.ttm_eps != null ? Number(r.ttm_eps) : null,
      pb_book_value:    r.pb_book_value != null ? Number(r.pb_book_value) : null,
      operating_margin: r.operating_margin != null ? Number(r.operating_margin) : null,
      stocks:           r.stocks as { name: string; industry: string; market: string } | null,
      models,
    })
  }

  // 先按共識模型數量降序，同數再按折價幅度降序
  return rows
    .sort((a, b) => {
      const countDiff = (b.models?.length ?? 0) - (a.models?.length ?? 0)
      if (countDiff !== 0) return countDiff
      return (a.current_price / a.cheap_price) - (b.current_price / b.cheap_price)
    })
    .slice(0, 50)
}

export default async function CheapLeaderboard() {
  const db = getSupabase()
  const [pe, pb, ps, pfcf, consensus] = await Promise.all([
    fetchModel(db, 'pe'),
    fetchModel(db, 'pb'),
    fetchModel(db, 'ps'),
    fetchModel(db, 'pfcf'),
    fetchConsensus(db),
  ])

  if (pe.length + pb.length + ps.length + pfcf.length === 0) {
    return <p className="text-gray-400 text-center py-8">目前沒有被低估的股票</p>
  }

  return <CheapLeaderboardClient data={{ pe, pb, ps, pfcf, consensus }} />
}
