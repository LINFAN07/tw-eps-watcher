import { NextRequest, NextResponse } from 'next/server'
import { SupabaseClient } from '@supabase/supabase-js'
import { getSupabase } from '@/lib/supabase'
import { adjustedMap, type ExEvent } from '@/lib/priceAdjust'

async function fetchAllPrices(db: SupabaseClient, stockId: string) {
  const all: { date: string; close_price: number }[] = []
  let offset = 0
  while (true) {
    const { data, error } = await db.from('daily_prices')
      .select('date,close_price')
      .eq('stock_id', stockId)
      .order('date')
      .range(offset, offset + 999)
    if (error || !data) throw new Error(`股價查詢失敗: ${error?.message}`)
    all.push(...data)
    if (data.length < 1000) break
    offset += 1000
  }
  return all
}

export async function GET(_req: NextRequest, { params }: { params: Promise<{ code: string }> }) {
  const { code } = await params
  const db = getSupabase()

  // P/B 百分位數（由 calculate_alt_valuations.py 預算，直接讀取）
  const { data: val } = await db.from('valuations')
    .select('pb_book_value,pb_cheap_pb,pb_fair_pb,pb_expensive_pb,pb_status,current_price')
    .eq('stock_id', code)
    .single()

  if (!val?.pb_cheap_pb)
    return NextResponse.json({ error: 'P/B 資料尚未計算，請先執行 calculate_alt_valuations.py' }, { status: 404 })

  // 歷史每股淨值序列（季度）
  const { data: bvpsRaw } = await db.from('balance_sheet_quarterly')
    .select('quarter_end_date,book_value_per_share')
    .eq('stock_id', code)
    .order('quarter_end_date')

  if (!bvpsRaw || bvpsRaw.length < 4)
    return NextResponse.json({ error: '每股淨值資料不足' }, { status: 404 })

  // 月採樣股價
  let prices: Awaited<ReturnType<typeof fetchAllPrices>>
  try {
    prices = await fetchAllPrices(db, code)
  } catch {
    return NextResponse.json({ error: '股價資料載入失敗' }, { status: 500 })
  }

  // 取每月最後一筆收盤價（月採樣，約 120 個資料點）
  // 除權息即時還原：用全日序列 + 股利算「日期→還原價」
  const { data: divRows } = await db.from('dividends')
    .select('ex_date,cash_dividend,stock_dividend').eq('stock_id', code)
  // 配股必須一起帶：只還原現金股利會在配股日留下數十個百分點的假跌幅
  const exList: ExEvent[] = (divRows ?? []).map(d =>
    [d.ex_date, Number(d.cash_dividend ?? 0), Number(d.stock_dividend ?? 0)])
  const adjMap = adjustedMap(prices, exList)

  const byMonth: Record<string, typeof prices[0]> = {}
  for (const p of prices) byMonth[p.date.slice(0, 7)] = p
  const sampled = Object.values(byMonth).sort((a, b) => a.date.localeCompare(b.date))

  // merge_asof：每月找最近一期每股淨值（與 P/E 圖表邏輯相同）
  let bi = 0
  const chartData = sampled.map(p => {
    while (bi + 1 < bvpsRaw.length && bvpsRaw[bi + 1].quarter_end_date <= p.date) bi++
    const bvps = bvpsRaw[bi]?.quarter_end_date <= p.date
      ? Number(bvpsRaw[bi].book_value_per_share) : null
    if (!bvps || bvps <= 0) return null
    return {
      date:      p.date,
      price:     adjMap[p.date] ?? Number(p.close_price),   // 河流圖用還原價（回退原始）
      cheap:     +(bvps * Number(val.pb_cheap_pb)).toFixed(2),
      fair:      +(bvps * Number(val.pb_fair_pb)).toFixed(2),
      expensive: +(bvps * Number(val.pb_expensive_pb)).toFixed(2),
    }
  }).filter((d): d is NonNullable<typeof d> => d !== null)

  if (chartData.length === 0)
    return NextResponse.json({ error: '圖表資料不足' }, { status: 404 })

  return NextResponse.json({ chartData, valuation: val })
}
