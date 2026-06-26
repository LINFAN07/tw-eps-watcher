import { NextRequest, NextResponse } from 'next/server'
import { getSupabase } from '@/lib/supabase'

// 取得一支股票的所有日收盤價（自動分頁，繞過 Supabase 1000 筆上限）
async function fetchAllPrices(db: ReturnType<typeof import('@/lib/supabase').getSupabase>, stockId: string) {
  const all: { date: string; close_price: number }[] = []
  let offset = 0
  while (true) {
    const { data } = await db.from('daily_prices')
      .select('date,close_price')
      .eq('stock_id', stockId)
      .order('date')
      .range(offset, offset + 999)
    if (!data) break
    all.push(...data)
    if (data.length < 1000) break
    offset += 1000
  }
  return all
}

export async function GET(_req: NextRequest, { params }: { params: Promise<{ code: string }> }) {
  const { code } = await params
  const db = getSupabase()

  // P/E 百分位區間
  const { data: val } = await db.from('valuations')
    .select('cheap_pe,fair_pe,expensive_pe,ttm_eps,current_price,status')
    .eq('stock_id', code)
    .single()
  if (!val) return NextResponse.json({ error: 'Not found' }, { status: 404 })

  // 季度 EPS
  const { data: epsRaw } = await db.from('eps_quarterly')
    .select('quarter_end_date,eps')
    .eq('stock_id', code)
    .order('quarter_end_date')
  if (!epsRaw || epsRaw.length < 4) return NextResponse.json({ error: 'Insufficient EPS' }, { status: 404 })

  // 計算 TTM EPS 序列（每季往回加 4 季）
  const ttmSeries = epsRaw.slice(3).map((_, i) => {
    const base = i + 3
    const ttm = [0, 1, 2, 3].reduce((s, j) => s + Number(epsRaw[base - j].eps), 0)
    return { date: epsRaw[base].quarter_end_date, ttm }
  }).filter(e => e.ttm > 0)

  // 日收盤價，取每月最後一筆（約 120 點）
  const prices = await fetchAllPrices(db, code)
  const byMonth: Record<string, typeof prices[0]> = {}
  for (const p of prices) byMonth[p.date.slice(0, 7)] = p
  const sampled = Object.values(byMonth).sort((a, b) => a.date.localeCompare(b.date))

  // 對每個月收盤價，找最近一期 TTM EPS（merge_asof 邏輯）
  let ei = 0
  const chartData = sampled.map(p => {
    while (ei + 1 < ttmSeries.length && ttmSeries[ei + 1].date <= p.date) ei++
    const ttm = ttmSeries[ei]?.date <= p.date ? ttmSeries[ei].ttm : null
    if (!ttm) return null
    return {
      date: p.date,
      price: Number(p.close_price),
      cheap: +(ttm * Number(val.cheap_pe)).toFixed(2),
      fair: +(ttm * Number(val.fair_pe)).toFixed(2),
      expensive: +(ttm * Number(val.expensive_pe)).toFixed(2),
    }
  }).filter(Boolean)

  return NextResponse.json({ chartData, valuation: val })
}
