import { NextRequest, NextResponse } from 'next/server'
import { SupabaseClient } from '@supabase/supabase-js'
import { getSupabase } from '@/lib/supabase'

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

  // P/FCF 百分位數
  const { data: val } = await db.from('valuations')
    .select('pfcf_per_share,pfcf_cheap_pfcf,pfcf_fair_pfcf,pfcf_expensive_pfcf,pfcf_status,current_price')
    .eq('stock_id', code)
    .single()

  if (!val?.pfcf_cheap_pfcf)
    return NextResponse.json({ error: 'P/FCF 資料尚未計算，請先執行 calculate_alt_valuations.py' }, { status: 404 })

  // 流通股數（千股）
  const { data: stockInfo } = await db.from('stocks')
    .select('listed_shares')
    .eq('stock_id', code)
    .single()

  const listedShares = Number(stockInfo?.listed_shares)
  if (!listedShares || listedShares <= 0)
    return NextResponse.json({ error: '流通股數資料不足' }, { status: 404 })

  // 季度現金流序列（operating_cf + capex，單位千元）
  const { data: cfRaw } = await db.from('cash_flows_quarterly')
    .select('quarter_end_date,operating_cf,capex')
    .eq('stock_id', code)
    .order('quarter_end_date')

  if (!cfRaw || cfRaw.length < 4)
    return NextResponse.json({ error: '現金流資料不足（需至少 4 季）' }, { status: 404 })

  // 每季計算 TTM FCF per share（滾動 4 季合計）
  // FCF = operating_cf + capex（capex 通常為負），單位千元
  // FCF per share = 千元 ÷ (千股 × 1000) = 元/股
  const ttmFcf: { date: string; fcfPerShare: number }[] = []
  for (let i = 3; i < cfRaw.length; i++) {
    const window = cfRaw.slice(i - 3, i + 1)
    const fcf = window.reduce(
      (s, q) => s + Number(q.operating_cf ?? 0) + Number(q.capex ?? 0), 0
    )
    const fcfPs = fcf / (listedShares * 1000)
    if (fcfPs > 0) ttmFcf.push({ date: cfRaw[i].quarter_end_date, fcfPerShare: fcfPs })
  }

  if (ttmFcf.length === 0)
    return NextResponse.json({ error: '無正值 FCF 期間，無法繪製河流圖' }, { status: 404 })

  // 月採樣股價
  let prices: Awaited<ReturnType<typeof fetchAllPrices>>
  try {
    prices = await fetchAllPrices(db, code)
  } catch {
    return NextResponse.json({ error: '股價資料載入失敗' }, { status: 500 })
  }

  const byMonth: Record<string, { date: string; close_price: number }> = {}
  for (const p of prices) byMonth[p.date.slice(0, 7)] = p
  const sampled = Object.values(byMonth).sort((a, b) => a.date.localeCompare(b.date))

  // merge_asof：每月找最近一期 TTM FCF per share
  let fi = 0
  const chartData = sampled.map(p => {
    while (fi + 1 < ttmFcf.length && ttmFcf[fi + 1].date <= p.date) fi++
    const fcfPs = ttmFcf[fi]?.date <= p.date ? ttmFcf[fi].fcfPerShare : null
    if (!fcfPs) return null
    return {
      date:      p.date,
      price:     Number(p.close_price),
      cheap:     +(fcfPs * Number(val.pfcf_cheap_pfcf)).toFixed(2),
      fair:      +(fcfPs * Number(val.pfcf_fair_pfcf)).toFixed(2),
      expensive: +(fcfPs * Number(val.pfcf_expensive_pfcf)).toFixed(2),
    }
  }).filter((d): d is NonNullable<typeof d> => d !== null)

  if (chartData.length === 0)
    return NextResponse.json({ error: '圖表資料不足' }, { status: 404 })

  return NextResponse.json({ chartData, valuation: val })
}
