import { NextRequest, NextResponse } from 'next/server'
import { SupabaseClient } from '@supabase/supabase-js'
import { getSupabase } from '@/lib/supabase'

async function fetchAllPrices(db: SupabaseClient, stockId: string) {
  const all: { date: string; close_price: number; adjusted_close: number | null }[] = []
  let offset = 0
  while (true) {
    const { data, error } = await db.from('daily_prices')
      .select('date,close_price,adjusted_close')
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

  // P/S 百分位數
  const { data: val } = await db.from('valuations')
    .select('ps_revenue_per_share,ps_cheap_ps,ps_fair_ps,ps_expensive_ps,ps_status,current_price')
    .eq('stock_id', code)
    .single()

  if (!val?.ps_cheap_ps)
    return NextResponse.json({ error: 'P/S 資料尚未計算，請先執行 calculate_alt_valuations.py' }, { status: 404 })

  // 流通股數（千股）
  const { data: stockInfo } = await db.from('stocks')
    .select('listed_shares')
    .eq('stock_id', code)
    .single()

  const listedShares = Number(stockInfo?.listed_shares)
  if (!listedShares || listedShares <= 0)
    return NextResponse.json({ error: '流通股數資料不足' }, { status: 404 })

  // 月營收序列（千元）
  const { data: revenueRaw } = await db.from('monthly_revenue')
    .select('year_month,revenue')
    .eq('stock_id', code)
    .order('year_month')

  if (!revenueRaw || revenueRaw.length < 12)
    return NextResponse.json({ error: '月營收資料不足（需至少 12 個月）' }, { status: 404 })

  // 月採樣股價
  let prices: Awaited<ReturnType<typeof fetchAllPrices>>
  try {
    prices = await fetchAllPrices(db, code)
  } catch {
    return NextResponse.json({ error: '股價資料載入失敗' }, { status: 500 })
  }

  const byMonth: Record<string, typeof prices[0]> = {}
  for (const p of prices) byMonth[p.date.slice(0, 7)] = p

  // 從第 12 筆起，每月計算 TTM 營收（前 12 個月合計）→ 計算帶狀價格
  // revenue 元 ÷ (listed_shares 千股 × 1000) = 元/股
  const chartData = revenueRaw.slice(11).map((_, i) => {
    const idx    = i + 11
    const window = revenueRaw.slice(idx - 11, idx + 1)
    const ttmRev = window.reduce((s, r) => s + Number(r.revenue), 0)
    const rps    = ttmRev / (listedShares * 1000)  // 元/股
    if (rps <= 0) return null

    const monthStr   = revenueRaw[idx].year_month.slice(0, 7)
    const pricePoint = byMonth[monthStr]
    if (!pricePoint) return null

    return {
      date:      pricePoint.date,
      price:     Number(pricePoint.adjusted_close ?? pricePoint.close_price),   // 河流圖用還原價（回退原始）
      cheap:     +(rps * Number(val.ps_cheap_ps)).toFixed(2),
      fair:      +(rps * Number(val.ps_fair_ps)).toFixed(2),
      expensive: +(rps * Number(val.ps_expensive_ps)).toFixed(2),
    }
  }).filter((d): d is NonNullable<typeof d> => d !== null)

  if (chartData.length === 0)
    return NextResponse.json({ error: '圖表資料不足' }, { status: 404 })

  return NextResponse.json({ chartData, valuation: val })
}
