import { getSupabase } from '@/lib/supabase'
import CheapLeaderboardClient, { type LeaderboardRow } from './CheapLeaderboardClient'

// 這兩種警告代表估值模型失真，不應出現在排行榜
const UNRELIABLE_WARNINGS = ['EPS 長期偏低', '顯著高於長期均值']

async function fetchCheapStocks(): Promise<LeaderboardRow[]> {
  const db = getSupabase()
  const { data } = await db.from('valuations')
    .select('stock_id,ttm_eps,cheap_pe,cheap_price,current_price,status,warning,stocks(name,industry,market)')
    .eq('status', '便宜')
    .gt('current_price', 0)
    .order('current_price', { ascending: true })
    .limit(100)
  if (!data) return []
  // 排序：現價與便宜價的比值（越低 = 越便宜），並排除失真警告
  return (data as unknown as LeaderboardRow[])
    .filter(r => !r.warning || !UNRELIABLE_WARNINGS.some(kw => r.warning!.includes(kw)))
    .sort((a, b) => (a.current_price / a.cheap_price) - (b.current_price / b.cheap_price))
    .slice(0, 50)
}

export default async function CheapLeaderboard() {
  const rows = await fetchCheapStocks()

  if (rows.length === 0) {
    return <p className="text-gray-400 text-center py-8">目前沒有被低估的股票</p>
  }

  return <CheapLeaderboardClient rows={rows} />
}
