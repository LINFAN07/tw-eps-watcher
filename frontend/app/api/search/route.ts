import { NextRequest, NextResponse } from 'next/server'
import { getSupabase } from '@/lib/supabase'

export async function GET(req: NextRequest) {
  const q = req.nextUrl.searchParams.get('q')?.trim() ?? ''
  if (q.length < 1) return NextResponse.json([])

  const db = getSupabase()
  const [byCode, byName] = await Promise.all([
    db.from('stocks').select('stock_id,name,market,industry').ilike('stock_id', `${q}%`).limit(5),
    db.from('stocks').select('stock_id,name,market,industry').ilike('name', `%${q}%`).limit(5),
  ])

  const seen = new Set<string>()
  const results = [...(byCode.data ?? []), ...(byName.data ?? [])].filter(r => {
    if (seen.has(r.stock_id)) return false
    seen.add(r.stock_id)
    return true
  })

  return NextResponse.json(results.slice(0, 8))
}
