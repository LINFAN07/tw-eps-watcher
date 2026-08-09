import { NextRequest, NextResponse } from 'next/server'
import { SupabaseClient } from '@supabase/supabase-js'
import { getSupabase } from '@/lib/supabase'
import { adjustedMap } from '@/lib/priceAdjust'
import { fetchExAdjustment } from '@/lib/exRights'
import { ttmWindows } from '@/lib/periodicity'

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

const QUARTER_INDEX: Record<string, number> = { '03': 1, '06': 2, '09': 3, '12': 4 }

type CashFlowRow = { quarter_end_date: string; operating_cf: number | null; capex: number | null }

// 還原「年初至今累計」為單季 FCF。
// 台灣現金流量表以年度累計揭露（Q1 重置、逐季累加），
// 例如台積電 2025 年營業現金流為 0.63→1.12→1.55→2.27 兆，
// 直接四季相加會得到 5.57 兆，實際 TTM 僅約 2.3 兆。
// 規則：該年度第一季直接採用，其餘減去同年度前一季；前一季缺漏則剔除該筆。
function decumulate(rows: CashFlowRow[]): { date: string; fcf: number }[] {
  const cumulative = new Map<string, { op: number; cx: number }>()
  for (const r of rows) {
    const qi = QUARTER_INDEX[r.quarter_end_date.slice(5, 7)]
    if (!qi) continue
    cumulative.set(`${r.quarter_end_date.slice(0, 4)}-${qi}`, {
      op: Number(r.operating_cf ?? 0),
      cx: Number(r.capex ?? 0),
    })
  }

  const out: { date: string; fcf: number }[] = []
  for (const r of rows) {
    const year = r.quarter_end_date.slice(0, 4)
    const qi = QUARTER_INDEX[r.quarter_end_date.slice(5, 7)]
    if (!qi) continue
    const cur = cumulative.get(`${year}-${qi}`)!
    if (qi === 1) {
      out.push({ date: r.quarter_end_date, fcf: cur.op + cur.cx })
      continue
    }
    const prev = cumulative.get(`${year}-${qi - 1}`)
    if (!prev) continue   // 同年度前一季缺漏，無法還原
    out.push({ date: r.quarter_end_date, fcf: (cur.op - prev.op) + (cur.cx - prev.cx) })
  }
  return out
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

  // 季度現金流序列（operating_cf + capex，單位：元）
  const { data: cfRaw } = await db.from('cash_flows_quarterly')
    .select('quarter_end_date,operating_cf,capex')
    .eq('stock_id', code)
    .order('quarter_end_date')

  if (!cfRaw || cfRaw.length < 4)
    return NextResponse.json({ error: '現金流資料不足（需至少 4 季）' }, { status: 404 })

  const quarterly = decumulate(cfRaw)
  if (quarterly.length < 4)
    return NextResponse.json({ error: '現金流資料不足（需至少 4 季）' }, { status: 404 })

  // 每季計算 TTM FCF per share。取「哪幾期剛好 12 個月」而非「最近 N 列」——
  // 公司中途改變揭露頻率時，最近 4 列可能橫跨 21 個月（見 lib/periodicity.ts）。
  // FCF = operating_cf + capex（capex 通常為負），單位：元
  // FCF per share = 元 ÷ (千股 × 1000) = 元/股
  const fcfByDate = new Map(quarterly.map(q => [q.date, q.fcf]))
  const ttmFcf: { date: string; fcfPerShare: number }[] = []
  for (const [date, window] of ttmWindows(quarterly.map(q => q.date))) {
    if (!window) continue        // 湊不出 12 個月就不給這一點，不用近似值頂替
    const fcf = window.reduce((sum, d) => sum + (fcfByDate.get(d) ?? 0), 0)
    const fcfPs = fcf / (listedShares * 1000)
    if (fcfPs > 0) ttmFcf.push({ date, fcfPerShare: fcfPs })
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

  // 除權息即時還原：用全日序列 + 股利算「日期→還原價」
  const { exList, official } = await fetchExAdjustment(db, code)
  const adjMap = adjustedMap(prices, exList, official)

  const byMonth: Record<string, typeof prices[0]> = {}
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
      price:     adjMap[p.date] ?? Number(p.close_price),   // 河流圖用還原價（回退原始）
      cheap:     +(fcfPs * Number(val.pfcf_cheap_pfcf)).toFixed(2),
      fair:      +(fcfPs * Number(val.pfcf_fair_pfcf)).toFixed(2),
      expensive: +(fcfPs * Number(val.pfcf_expensive_pfcf)).toFixed(2),
    }
  }).filter((d): d is NonNullable<typeof d> => d !== null)

  if (chartData.length === 0)
    return NextResponse.json({ error: '圖表資料不足' }, { status: 404 })

  return NextResponse.json({ chartData, valuation: val })
}
