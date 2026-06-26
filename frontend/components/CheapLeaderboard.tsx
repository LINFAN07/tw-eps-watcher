import Link from 'next/link'
import { getSupabase } from '@/lib/supabase'

interface Row {
  stock_id: string
  ttm_eps: number
  cheap_pe: number
  cheap_price: number
  current_price: number
  status: string
  stocks: { name: string; industry: string; market: string } | null
}

async function fetchCheapStocks(): Promise<Row[]> {
  const db = getSupabase()
  const { data } = await db.from('valuations')
    .select('stock_id,ttm_eps,cheap_pe,cheap_price,current_price,status,stocks(name,industry,market)')
    .eq('status', '便宜')
    .gt('current_price', 0)
    .order('current_price', { ascending: true })
    .limit(50)
      if (!data) return []
  // 排序：現價與便宜價的比值（越低 = 越便宜）
  return (data as unknown as Row[]).sort(
    (a, b) => (a.current_price / a.cheap_price) - (b.current_price / b.cheap_price)
  ).slice(0, 30)
}

const statusColor: Record<string, string> = {
  '便宜': 'bg-green-100 text-green-700',
  '合理': 'bg-blue-100 text-blue-700',
  '昂貴': 'bg-red-100 text-red-700',
}

export default async function CheapLeaderboard() {
  const rows = await fetchCheapStocks()

  if (rows.length === 0) {
    return <p className="text-gray-400 text-center py-8">目前沒有被低估的股票</p>
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-200 text-gray-500 text-left">
            <th className="pb-3 pr-4 font-medium">#</th>
            <th className="pb-3 pr-4 font-medium">代碼</th>
            <th className="pb-3 pr-4 font-medium">公司</th>
            <th className="pb-3 pr-4 font-medium hidden md:table-cell">產業</th>
            <th className="pb-3 pr-4 font-medium text-right">現價</th>
            <th className="pb-3 pr-4 font-medium text-right">便宜價</th>
            <th className="pb-3 font-medium text-right">折價</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => {
            const discount = (((r.cheap_price - r.current_price) / r.cheap_price) * 100).toFixed(1)
            const name = r.stocks?.name ?? '—'
            const industry = r.stocks?.industry ?? r.stocks?.market ?? '—'
            return (
              <tr key={r.stock_id} className="border-b border-gray-50 hover:bg-gray-50 transition-colors">
                <td className="py-3 pr-4 text-gray-400">{i + 1}</td>
                <td className="py-3 pr-4">
                  <Link href={`/stock/${r.stock_id}`} className="font-mono font-bold text-blue-600 hover:underline">
                    {r.stock_id}
                  </Link>
                </td>
                <td className="py-3 pr-4">
                  <Link href={`/stock/${r.stock_id}`} className="text-gray-800 hover:text-blue-600">
                    {name}
                  </Link>
                </td>
                <td className="py-3 pr-4 text-gray-400 hidden md:table-cell">{industry}</td>
                <td className="py-3 pr-4 text-right font-medium">{r.current_price}</td>
                <td className="py-3 pr-4 text-right text-green-600">{r.cheap_price}</td>
                <td className="py-3 text-right">
                  <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${statusColor[r.status] ?? ''}`}>
                    -{discount}%
                  </span>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
