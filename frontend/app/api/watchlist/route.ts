import { NextRequest, NextResponse } from 'next/server'
import { getSupabase } from '@/lib/supabase'

export async function GET(req: NextRequest) {
  const codes = req.nextUrl.searchParams.get('codes')
    ?.split(',').map(s => s.trim()).filter(Boolean) ?? []

  if (codes.length === 0) return NextResponse.json([])

  const db = getSupabase()
  const { data } = await db
    .from('valuations')
    // fair_price／expensive_price 供面板畫「現價在估值帶哪個位置」的位置條；
    // pe_reliable／pe_deep_discount／nonop_warning 供 isPeUnreliable() 判讀——
    // 帶本身失真時位置條要標示出來，否則等於把「不知道」畫成精確的一點。
    .select('stock_id,current_price,status,cheap_price,fair_price,expensive_price,' +
            'warning,nonop_warning,pe_reliable,pe_deep_discount,stocks(name)')
    .in('stock_id', codes)

  return NextResponse.json(data ?? [])
}
