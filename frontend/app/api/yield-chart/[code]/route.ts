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
    if (error || !data) throw new Error(`價格查詢失敗：${error?.message}`)
    all.push(...data)
    if (data.length < 1000) break
    offset += 1000
  }
  return all
}

const YIELD_CHEAP    = 80 // 殖利率第 80 百分位 = 歷史便宜水準（殖利率高 = 股價低）
const YIELD_FAIR     = 50
const YIELD_EXPENSIVE = 20

export async function GET(_req: NextRequest, { params }: { params: Promise<{ code: string }> }) {
  const { code } = await params
  const db = getSupabase()

  // 取該股票的現金股利紀錄（依除息日升序）
  const { data: divs } = await db.from('dividends')
    .select('ex_date,cash_dividend')
    .eq('stock_id', code)
    .order('ex_date')

  if (!divs || divs.length === 0) {
    return NextResponse.json({ error: 'NO_DIVIDEND' }, { status: 404 })
  }

  // 取歷史收盤價
  let prices: Awaited<ReturnType<typeof fetchAllPrices>>
  try {
    prices = await fetchAllPrices(db, code)
  } catch {
    return NextResponse.json({ error: '價格資料載入失敗' }, { status: 500 })
  }
  if (prices.length < 30) return NextResponse.json({ error: 'Insufficient price data' }, { status: 404 })

  // 每月最後一筆（降低資料量）
  const byMonth: Record<string, typeof prices[0]> = {}
  for (const p of prices) byMonth[p.date.slice(0, 7)] = p
  const sampled = Object.values(byMonth).sort((a, b) => a.date.localeCompare(b.date))

  // 計算每個月的 TTM 股利（過去 365 天現金股利加總）
  // 殖利率 = TTM 股利 / 收盤價
  const yieldSeries: number[] = []
  const chartData: { date: string; price: number; cheap: number; fair: number; expensive: number }[] = []

  for (const p of sampled) {
    const dayMs = new Date(p.date).getTime()
    const ttmDiv = divs
      .filter(d => {
        const ms = new Date(d.ex_date).getTime()
        return ms <= dayMs && ms > dayMs - 365 * 86400 * 1000
      })
      .reduce((s, d) => s + Number(d.cash_dividend), 0)

    if (ttmDiv > 0 && p.close_price > 0) {
      yieldSeries.push(ttmDiv / p.close_price)
    }
  }

  if (yieldSeries.length < 10) {
    return NextResponse.json({ error: 'Insufficient yield data' }, { status: 404 })
  }

  // 計算殖利率百分位數（排序後取位置）
  const sorted = [...yieldSeries].sort((a, b) => a - b)
  const pct = (p: number) => sorted[Math.floor((sorted.length - 1) * p / 100)]
  const yieldCheap     = pct(YIELD_CHEAP)      // 高殖利率 = 歷史便宜
  const yieldFair      = pct(YIELD_FAIR)
  const yieldExpensive = pct(YIELD_EXPENSIVE)  // 低殖利率 = 歷史昂貴

  // 產生圖表資料：對每個月計算三條價格帶
  for (const p of sampled) {
    const dayMs = new Date(p.date).getTime()
    const ttmDiv = divs
      .filter(d => {
        const ms = new Date(d.ex_date).getTime()
        return ms <= dayMs && ms > dayMs - 365 * 86400 * 1000
      })
      .reduce((s, d) => s + Number(d.cash_dividend), 0)

    if (ttmDiv <= 0) continue

    chartData.push({
      date:      p.date,
      price:     +Number(p.close_price).toFixed(2),
      cheap:     +(ttmDiv / yieldCheap).toFixed(2),
      fair:      +(ttmDiv / yieldFair).toFixed(2),
      expensive: +(ttmDiv / yieldExpensive).toFixed(2),
    })
  }

  if (chartData.length === 0) return NextResponse.json({ error: 'Insufficient chart data' }, { status: 404 })

  // 最新 TTM 股利與殖利率帶摘要
  const latestPrice  = prices[prices.length - 1].close_price
  const recentDivMs  = new Date(prices[prices.length - 1].date).getTime()
  const latestTTMDiv = divs
    .filter(d => {
      const ms = new Date(d.ex_date).getTime()
      return ms <= recentDivMs && ms > recentDivMs - 365 * 86400 * 1000
    })
    .reduce((s, d) => s + Number(d.cash_dividend), 0)

  const currentYield = latestTTMDiv > 0 ? +(latestTTMDiv / latestPrice * 100).toFixed(2) : null

  return NextResponse.json({
    chartData,
    summary: {
      ttmDiv:          +latestTTMDiv.toFixed(2),
      currentYield,
      cheapYield:      +(yieldCheap * 100).toFixed(2),
      fairYield:       +(yieldFair  * 100).toFixed(2),
      expensiveYield:  +(yieldExpensive * 100).toFixed(2),
      cheapPrice:      +(latestTTMDiv / yieldCheap).toFixed(2),
      fairPrice:       +(latestTTMDiv / yieldFair).toFixed(2),
      expensivePrice:  +(latestTTMDiv / yieldExpensive).toFixed(2),
    },
  })
}
