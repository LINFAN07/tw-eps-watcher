import { NextRequest, NextResponse } from 'next/server'
import { SupabaseClient } from '@supabase/supabase-js'
import { getSupabase } from '@/lib/supabase'
import { adjustedMap } from '@/lib/priceAdjust'
import { fetchExAdjustment } from '@/lib/exRights'
import { ttmWindows } from '@/lib/periodicity'

// 取得一支股票的所有日收盤價（自動分頁，繞過 Supabase 1000 筆上限）
// 中途任一頁失敗即拋出錯誤，避免靜默回傳截斷的不完整資料
async function fetchAllPrices(db: SupabaseClient, stockId: string) {
  const all: { date: string; close_price: number }[] = []
  let offset = 0
  while (true) {
    const { data, error } = await db.from('daily_prices')
      .select('date,close_price')
      .eq('stock_id', stockId)
      .order('date')
      .range(offset, offset + 999)
    if (error || !data) throw new Error(`價格分頁查詢失敗（offset=${offset}）：${error?.message}`)
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
    .select('cheap_pe,fair_pe,expensive_pe,ttm_eps,current_price,status,warning')
    .eq('stock_id', code)
    .single()
  if (!val) return NextResponse.json({ error: 'Not found' }, { status: 404 })

  // 季度 EPS
  const { data: epsRaw } = await db.from('eps_quarterly')
    .select('quarter_end_date,eps')
    .eq('stock_id', code)
    .order('quarter_end_date')
  // 2 是【資料量下限】，不是 TTM 期數：視窗由下方的 ttmWindows() 依實際期別決定
  // （季報 4 期、半年報 2 期）。這裡只擋「連兩期都沒有」。
  if (!epsRaw || epsRaw.length < 2) return NextResponse.json({ error: 'Insufficient EPS' }, { status: 404 })

  // 計算 TTM EPS 序列。問的是「哪幾期加起來剛好 12 個月」，不是「最近 N 列」——
  // 期數標籤答不了公司中途改變揭露頻率的情形：半年報轉季報時，最近 4 列會是
  // Q1+H2+H1+H2＝21 個月。2026-08-09 修正前這裡用的是後者，43 支在市股票的
  // 估值帶因此偏高（7843 用 3.16，正確 -0.14），且與同一頁的估值卡矛盾。
  // 與後端共用同一套規則（lib/periodicity.ts，兩端由 tests/test_shared.* 綁在一起）。
  const epsByDate = new Map(epsRaw.map(e => [e.quarter_end_date, Number(e.eps)]))
  const ttmSeries = [...ttmWindows(epsRaw.map(e => e.quarter_end_date))]
    .flatMap(([date, window]) => window
      // 湊不出 12 個月的期別直接不給點，不用近似值頂替（資料誠信原則第 3 條）
      ? [{ date, ttm: window.reduce((sum, d) => sum + (epsByDate.get(d) ?? 0), 0) }]
      : [])
  // ⚠️ 這裡刻意【不】過濾 ttm > 0。過濾掉虧損期會讓下面的 merge_asof 一路沿用
  // 最後一個為正的 TTM，於是卡片寫「虧損 −0.10」、圖上卻還有一條用 0.18 畫的帶
  // （4573 實例）。虧損期要讓帶斷掉，不是拿舊獲利撐著。

  // 日收盤價，取每月最後一筆（約 120 點）；失敗則回 500
  let prices: Awaited<ReturnType<typeof fetchAllPrices>>
  try {
    prices = await fetchAllPrices(db, code)
  } catch (e) {
    return NextResponse.json({ error: '價格資料載入失敗' }, { status: 500 })
  }
  // 除權息即時還原：用全日序列（升冪）+ 股利算「日期→還原價」，再月採樣
  const { exList, official } = await fetchExAdjustment(db, code)
  const adjMap = adjustedMap(prices, exList, official)

  const byMonth: Record<string, typeof prices[0]> = {}
  for (const p of prices) byMonth[p.date.slice(0, 7)] = p
  const sampled = Object.values(byMonth).sort((a, b) => a.date.localeCompare(b.date))

  // 對每個月收盤價，找最近一期 TTM EPS（merge_asof 邏輯）
  let ei = 0
  const chartData = sampled.map(p => {
    while (ei + 1 < ttmSeries.length && ttmSeries[ei + 1].date <= p.date) ei++
    const ttm = ttmSeries[ei]?.date <= p.date ? ttmSeries[ei].ttm : null
    if (ttm === null) return null            // 首份財報之前，連價格都不畫
    // TTM ≤ 0：股價線照畫，三條帶給 null 讓它斷在最後一個有效點。
    // 虧損期本來就沒有「合理本益比」可言，硬畫一條是在假裝模型還適用。
    const band = ttm > 0
      ? {
          cheap:     +(ttm * Number(val.cheap_pe)).toFixed(2),
          fair:      +(ttm * Number(val.fair_pe)).toFixed(2),
          expensive: +(ttm * Number(val.expensive_pe)).toFixed(2),
        }
      : { cheap: null, fair: null, expensive: null }
    return {
      date: p.date,
      // 河流圖價格線用還原價（與還原後的估值帶一致）。最新一日還原價==原始價，
      // 故現價顯示不受影響；查無還原值時回退原始價。
      price: adjMap[p.date] ?? Number(p.close_price),
      ...band,
    }
  }).filter(Boolean) as { date: string; price: number
                          cheap: number | null; fair: number | null; expensive: number | null }[]

  // 一條帶都畫不出來（TTM 全為負）才算沒有圖——只有部分期間為負時仍要回傳，
  // 那正是「帶斷掉、股價線續畫」想呈現的東西
  if (!chartData.some(d => d.cheap !== null))
    return NextResponse.json({ error: 'Insufficient chart data' }, { status: 404 })

  return NextResponse.json({ chartData, valuation: val })
}
