import { NextResponse } from 'next/server'
import { getSupabase } from '@/lib/supabase'

export const revalidate = 3600 // 每小時重算一次

// 取得全部符合條件的估值（自動分頁）。
// Supabase 單次查詢上限 1000 筆，全市場約 1700 支，
// 未分頁會靜默只統計前 1000 支，使市場分布系統性偏向低股票代碼。
async function fetchAllValuations(db: ReturnType<typeof getSupabase>) {
  const all: { status: string; current_price: number; ttm_eps: number }[] = []
  let offset = 0
  while (true) {
    const { data, error } = await db.from('valuations')
      .select('status,current_price,ttm_eps')
      .neq('status', '無法計算')
      .gt('current_price', 0)
      .order('stock_id')
      .range(offset, offset + 999)
    if (error || !data) throw new Error(`估值分頁查詢失敗（offset=${offset}）：${error?.message}`)
    all.push(...data)
    if (data.length < 1000) break
    offset += 1000
  }
  return all
}

export async function GET() {
  const db = getSupabase()

  let rows: Awaited<ReturnType<typeof fetchAllValuations>>
  try {
    rows = await fetchAllValuations(db)
  } catch {
    return NextResponse.json({ error: 'No data' }, { status: 500 })
  }

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
