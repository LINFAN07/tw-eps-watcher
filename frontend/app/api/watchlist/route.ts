import { NextRequest, NextResponse } from 'next/server'
import { getSupabase } from '@/lib/supabase'

export async function GET(req: NextRequest) {
  const codes = req.nextUrl.searchParams.get('codes')
    ?.split(',').map(s => s.trim()).filter(Boolean) ?? []

  if (codes.length === 0) return NextResponse.json([])

  const db = getSupabase()
  const { data } = await db
    .from('valuations')
    .select('stock_id,current_price,status,cheap_price,warning,stocks(name)')
    .in('stock_id', codes)

  return NextResponse.json(data ?? [])
}
