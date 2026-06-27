import { NextResponse } from 'next/server'
import { getSupabase } from '@/lib/supabase'

export const revalidate = 3600 // 每小時重算一次

export async function GET() {
  const db = getSupabase()

  // 計算各估值狀態的股票數（排除無法計算與零股價）
  const { data: rows } = await db.from('valuations')
    .select('status,current_price,ttm_eps')
    .neq('status', '無法計算')
    .gt('current_price', 0)

  if (!rows) return NextResponse.json({ error: 'No data' }, { status: 500 })

  let cheap = 0, fair = 0, expensive = 0
  const pes: number[] = []

  for (const r of rows) {
    if (r.status === '便宜') cheap++
    else if (r.status === '合理') fair++
    else if (r.status === '昂貴') expensive++

    if (r.ttm_eps > 0) pes.push(r.current_price / r.ttm_eps)
  }

  pes.sort((a, b) => a - b)
  const medianPE = pes.length > 0 ? +pes[Math.floor(pes.length / 2)].toFixed(1) : null

  return NextResponse.json({ cheap, fair, expensive, total: cheap + fair + expensive, medianPE })
}
