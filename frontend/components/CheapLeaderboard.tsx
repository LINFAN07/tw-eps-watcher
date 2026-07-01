import { getSupabase } from '@/lib/supabase'
import CheapLeaderboardClient, { type LeaderboardRow, type LeaderboardData } from './CheapLeaderboardClient'

// P/E 特有：這兩種警告代表估值模型失真，不應出現在 P/E 排行榜
const UNRELIABLE_WARNINGS = ['EPS 長期偏低', '顯著高於長期均值']

async function fetchModel(
  db: ReturnType<typeof getSupabase>,
  model: 'pe' | 'pb' | 'ps' | 'pfcf'
): Promise<LeaderboardRow[]> {
  const statusCol = model === 'pe' ? 'status' : `${model}_status`
  const priceCol  = model === 'pe' ? 'cheap_price' : `${model}_cheap_price`
  const selectFields = `stock_id,current_price,${priceCol}${model === 'pe' ? ',warning' : ''},stocks(name,industry,market)`

  const { data } = await db.from('valuations')
    .select(selectFields)
    .eq(statusCol, '便宜')
    .gt('current_price', 0)
    .not(priceCol, 'is', null)
    .limit(200)

  if (!data) return []

  let rows: LeaderboardRow[] = (data as unknown as Record<string, unknown>[]).map(r => ({
    stock_id:      r.stock_id as string,
    current_price: Number(r.current_price),
    cheap_price:   Number(r[priceCol]),
    warning:       (r.warning as string | null) ?? null,
    stocks:        r.stocks as { name: string; industry: string; market: string } | null,
  }))

  if (model === 'pe') {
    rows = rows.filter(r => !r.warning || !UNRELIABLE_WARNINGS.some(kw => r.warning!.includes(kw)))
  }

  return rows
    .sort((a, b) => (a.current_price / a.cheap_price) - (b.current_price / b.cheap_price))
    .slice(0, 50)
}

export default async function CheapLeaderboard() {
  const db = getSupabase()
  const [pe, pb, ps, pfcf] = await Promise.all([
    fetchModel(db, 'pe'),
    fetchModel(db, 'pb'),
    fetchModel(db, 'ps'),
    fetchModel(db, 'pfcf'),
  ])

  if (pe.length + pb.length + ps.length + pfcf.length === 0) {
    return <p className="text-gray-400 text-center py-8">目前沒有被低估的股票</p>
  }

  return <CheapLeaderboardClient data={{ pe, pb, ps, pfcf }} />
}
