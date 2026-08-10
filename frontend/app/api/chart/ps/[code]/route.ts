import { NextRequest, NextResponse } from 'next/server'
import { SupabaseClient } from '@supabase/supabase-js'
import { getSupabase } from '@/lib/supabase'
import { adjustedMap } from '@/lib/priceAdjust'
import { fetchExAdjustment } from '@/lib/exRights'
import { ttmMonthWindow } from '@/lib/periodicity'

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

  // 月營收序列（元；與下方第 72 行的換算一致。註解原寫「千元」為誤，2026-08-09 更正）
  const { data: revenueRaw } = await db.from('monthly_revenue')
    .select('year_month,revenue')
    .eq('stock_id', code)
    .order('year_month')

  // 12 是【資料量下限】，不是 TTM 視窗：視窗由下方的 ttmMonthWindow() 決定，
  // 它會檢查那 12 個月是否連續（缺月即回 null）。這裡只擋「連 12 筆都沒有」。
  if (!revenueRaw || revenueRaw.length < 12)
    return NextResponse.json({ error: '月營收資料不足（需至少 12 個月）' }, { status: 404 })

  // 月採樣股價
  let prices: Awaited<ReturnType<typeof fetchAllPrices>>
  try {
    prices = await fetchAllPrices(db, code)
  } catch {
    return NextResponse.json({ error: '股價資料載入失敗' }, { status: 500 })
  }

  // 除權息即時還原：用全日序列 + 股利算「日期→還原價」
  const { exList, official } = await fetchExAdjustment(db, code)
  const adjMap = adjustedMap(prices, exList, official)

  const byMonth: Record<string, typeof prices[0]> = {}
  for (const p of prices) byMonth[p.date.slice(0, 7)] = p

  // 每月計算 TTM 營收 → 帶狀價格。取「連續 12 個月」而非「最近 12 列」——
  // 全市場 42 支有缺月（共 388 個月），取 12 列會橫跨 13 個月以上、營收灌水。
  // revenue 元 ÷ (listed_shares 千股 × 1000) = 元/股
  const revByMonth = new Map(
    revenueRaw.map(r => [String(r.year_month).slice(0, 7), Number(r.revenue)]))
  const availableMonths = [...revByMonth.keys()]

  const chartData = availableMonths.map(monthStr => {
    const window = ttmMonthWindow(availableMonths, monthStr)
    if (!window) return null      // 缺月就不給這一點，不用 11 個月頂替 12 個月
    const ttmRev = window.reduce((s, m) => s + (revByMonth.get(m) ?? 0), 0)
    const rps    = ttmRev / (listedShares * 1000)  // 元/股
    if (rps <= 0) return null

    const pricePoint = byMonth[monthStr]
    if (!pricePoint) return null

    return {
      date:      pricePoint.date,
      price:     adjMap[pricePoint.date] ?? Number(pricePoint.close_price),   // 河流圖用還原價（回退原始）
      cheap:     +(rps * Number(val.ps_cheap_ps)).toFixed(2),
      fair:      +(rps * Number(val.ps_fair_ps)).toFixed(2),
      expensive: +(rps * Number(val.ps_expensive_ps)).toFixed(2),
    }
  }).filter((d): d is NonNullable<typeof d> => d !== null)

  if (chartData.length === 0)
    return NextResponse.json({ error: '圖表資料不足' }, { status: 404 })

  return NextResponse.json({ chartData, valuation: val })
}
