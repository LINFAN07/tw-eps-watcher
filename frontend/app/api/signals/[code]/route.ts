import { NextRequest, NextResponse } from 'next/server'
import { SupabaseClient } from '@supabase/supabase-js'
import { getSupabase } from '@/lib/supabase'
import { adjustedMap } from '@/lib/priceAdjust'
import { fetchExAdjustment } from '@/lib/exRights'
import { availableDate, ttmWindows } from '@/lib/periodicity'

/**
 * 個股的 P/E「便宜」訊號回放 —— 過去十年，這支股票在哪幾段時間被判為便宜，
 * 以及每一段之後一年發生了什麼。
 *
 * ## 為什麼不能直接讀河流圖
 *
 * 河流圖的便宜線 = 各月 TTM × `valuations.cheap_pe`，而 `cheap_pe` 是**今天**用
 * 全期歷史算出來的一個常數。拿它回頭套 2019 年，得到的是「以今天的眼光看，
 * 當時算便宜」——那是事後諸葛，不是「當時模型會說便宜」。
 *
 * 本路由改用**當時可得的資料**重算：時點 T 的百分位只看 ≤T 的倍數樣本
 * （expanding），且財報一律以申報期限（`availableDate`）為可用日
 * ——2026-04-30 不可能知道 2026Q1 的 EPS。這與 `backtest_valuation.py` 的
 * 防 look-ahead 作法相同，常數也取自同一份定義。
 *
 * ## 為什麼逐段列出而不給彙總報酬
 *
 * 一支股票十年內大概只有 2~4 段獨立的便宜期。把它們平均成「中位報酬 +4.2%」
 * 是假精確：本專案的回測已知「每月選股＋長持有期使樣本高度重疊，勝率的統計
 * 顯著性被高估」，而單股層級更嚴重——三段行情算不出中位數。
 * 逐段列出是事實陳述，讀者自己看得出樣本只有幾段。
 *
 * ## 與卡片上的「目前狀態」可能略有出入
 *
 * 這裡用月採樣，`calculate_valuation.py` 用週採樣（`to_weekly()`），
 * 百分位會有小差異。最新一點兩者的樣本集合最接近（expanding 到最後即全期），
 * 但仍不保證完全一致。呈現時要說明，不可讓使用者以為是網站算錯。
 */

// 與 backtest_valuation.py 同一組定義，改動時兩邊要一起改
const PCT_CHEAP  = 0.20   // 便宜 = 歷史 P/E 第 20 百分位
const MIN_SAMPLE = 24     // 建立百分位帶所需的最少月樣本（2 年）
const PE_MIN     = 3      // 與 calculate_valuation.py 一致的倍數合理範圍
const PE_MAX     = 200
const HORIZON    = 12     // 事後觀察的月數

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

/** 線性內插的百分位，與 pandas `.quantile()`／numpy 預設一致 */
function quantile(sorted: number[], q: number): number {
  const pos = (sorted.length - 1) * q
  const lo = Math.floor(pos)
  const hi = Math.ceil(pos)
  return lo === hi ? sorted[lo] : sorted[lo] + (sorted[hi] - sorted[lo]) * (pos - lo)
}

/** 保持陣列有序地插入（樣本數約 120，不需要更聰明的結構） */
function insertSorted(sorted: number[], value: number): void {
  let lo = 0, hi = sorted.length
  while (lo < hi) {
    const mid = (lo + hi) >> 1
    if (sorted[mid] < value) lo = mid + 1
    else hi = mid
  }
  sorted.splice(lo, 0, value)
}

interface Episode {
  startMonth: string
  endMonth: string
  months: number
  priceAtStart: number        // 當時實際收盤價（未還原，供辨識）
  cheapAtStart: number        // 當時以當時資料算出的便宜價
  forwardMonth: string | null
  forwardReturn: number | null  // 一年後含息報酬（%）；尚未滿一年為 null
}

export async function GET(_req: NextRequest, { params }: { params: Promise<{ code: string }> }) {
  const { code } = await params
  const db = getSupabase()

  const { data: epsRaw, error: epsErr } = await db.from('eps_quarterly')
    .select('quarter_end_date,eps')
    .eq('stock_id', code)
    .order('quarter_end_date')
  if (epsErr) return NextResponse.json({ error: `EPS 查詢失敗：${epsErr.message}` }, { status: 500 })
  if (!epsRaw?.length) return NextResponse.json({ error: 'NO_EPS' }, { status: 404 })

  let prices: Awaited<ReturnType<typeof fetchAllPrices>>
  try {
    prices = await fetchAllPrices(db, code)
  } catch {
    return NextResponse.json({ error: '價格資料載入失敗' }, { status: 500 })
  }
  if (!prices.length) return NextResponse.json({ error: 'NO_PRICE' }, { status: 404 })

  // 各季股數，用來把歷史 EPS 換算到最新股數基準。
  // EPS 是各季用【當時股數】申報的，配股後股數變多、數值變小，財報不追溯調整；
  // 而股價已除權還原到最新股數基準，分母不換算就會系統性壓低歷史倍數
  // → 便宜門檻偏低 → 訊號比實際少。與 calculate_valuation.share_factors 及
  // backtest_valuation.share_factor_table 同一套邏輯（實測見下方註記）。
  const { data: sharesRaw } = await db.from('balance_sheet_quarterly')
    .select('quarter_end_date,shares_thousand')
    .eq('stock_id', code)
    .order('quarter_end_date')
  const shareRows = (sharesRaw ?? [])
    .map(r => ({ date: String(r.quarter_end_date), shares: Number(r.shares_thousand) }))
    .filter(r => r.shares > 0)
  const latestShares = shareRows.length ? shareRows[shareRows.length - 1].shares : 0

  /** 該期的股數因子（向前對應最後一筆 ≤ 期末日）。對應不到就是 1，不猜、不外插 */
  const shareFactor = (quarterEnd: string): number => {
    if (!latestShares) return 1
    let factor = 1
    for (const row of shareRows) {
      if (row.date > quarterEnd) break
      factor = row.shares / latestShares
    }
    return factor
  }

  // 除權息還原：還原價相除即為含息總報酬（同 backtest_valuation.py 的作法）
  const { exList, official } = await fetchExAdjustment(db, code)
  const adjMap = adjustedMap(prices, exList, official)

  // 月採樣：每月最後一個交易日
  const byMonth = new Map<string, { date: string; close: number; adj: number }>()
  for (const p of prices) {
    byMonth.set(p.date.slice(0, 7), {
      date: p.date,
      close: Number(p.close_price),
      adj: adjMap[p.date] ?? Number(p.close_price),
    })
  }
  const months = [...byMonth.keys()].sort()

  // TTM EPS 序列，以【申報期限】為可用日。用期末日當可用日等於偷看未來。
  // 先把每季 EPS 換算到最新股數基準，再加總——順序不可顛倒，
  // 每季 EPS 要對應自己那一季的股數
  const epsByDate = new Map(epsRaw.map(
    e => [e.quarter_end_date, Number(e.eps) * shareFactor(e.quarter_end_date)]))
  const ttmByAvail: { avail: string; ttm: number }[] = []
  for (const [end, window] of ttmWindows(epsRaw.map(e => e.quarter_end_date))) {
    if (!window) continue
    ttmByAvail.push({
      avail: availableDate(end),
      ttm: window.reduce((sum, d) => sum + (epsByDate.get(d) ?? 0), 0),
    })
  }
  ttmByAvail.sort((a, b) => a.avail.localeCompare(b.avail))

  // 逐月往前走：只用 ≤ 當月的樣本算百分位（expanding），這是不作弊的關鍵
  const multiples: number[] = []
  const cheapMonths: { month: string; close: number; adj: number; cheapPrice: number }[] = []
  let ti = -1

  for (const month of months) {
    const point = byMonth.get(month)!
    while (ti + 1 < ttmByAvail.length && ttmByAvail[ti + 1].avail <= point.date) ti++
    const ttm = ti >= 0 ? ttmByAvail[ti].ttm : null
    if (ttm === null || ttm <= 0) continue

    const multiple = point.adj / ttm
    // 樣本累積在門檻判斷【之前】，與 pandas expanding 的語意相同（含當期）
    if (multiple >= PE_MIN && multiple <= PE_MAX) insertSorted(multiples, multiple)
    if (multiples.length < MIN_SAMPLE) continue
    if (multiple < PE_MIN || multiple > PE_MAX) continue

    const target = ttm * quantile(multiples, PCT_CHEAP)
    if (point.adj <= target) {
      cheapMonths.push({
        month, close: point.close, adj: point.adj,
        // 門檻換回「當時的錢」再顯示。判斷在還原基準上進行，但畫面若一邊印原始
        // 收盤價、一邊印還原基準的門檻，就會出現「股價 42.25 高於便宜價 29.74
        // 卻判便宜」這種自相矛盾。同乘 close/adj 不影響比較結果，只換單位。
        cheapPrice: target * (point.close / point.adj),
      })
    }
  }

  // 連續的月份合併成一段
  const episodes: Episode[] = []
  for (const m of cheapMonths) {
    const last = episodes[episodes.length - 1]
    const isNext = last && monthDiff(last.endMonth, m.month) === 1
    if (isNext) {
      last.endMonth = m.month
      last.months += 1
      continue
    }
    const forwardMonth = addMonths(m.month, HORIZON)
    const future = byMonth.get(forwardMonth)
    episodes.push({
      startMonth: m.month,
      endMonth: m.month,
      months: 1,
      priceAtStart: +m.close.toFixed(2),
      cheapAtStart: +m.cheapPrice.toFixed(2),
      // 還原價相除＝含息總報酬。取不到未來那個月就是「還沒滿一年」，
      // 不可用最近一筆頂替——那會把不同長度的持有期混為一談
      forwardMonth: future ? forwardMonth : null,
      forwardReturn: future ? +((future.adj / m.adj - 1) * 100).toFixed(1) : null,
    })
  }

  const lastMonth = months[months.length - 1]
  return NextResponse.json({
    episodes,
    summary: {
      firstMonth: months[0],
      lastMonth,
      // 樣本數不足 24 個月時整段沒有訊號，要與「有算但從未便宜」分開講
      evaluated: multiples.length >= MIN_SAMPLE,
      // 最後一段延續到最新月份 → 目前仍在便宜區間
      ongoing: episodes.length > 0 && episodes[episodes.length - 1].endMonth === lastMonth,
      horizonMonths: HORIZON,
    },
  })
}

function monthNumber(month: string): number {
  return Number(month.slice(0, 4)) * 12 + Number(month.slice(5, 7)) - 1
}

function monthDiff(from: string, to: string): number {
  return monthNumber(to) - monthNumber(from)
}

function addMonths(month: string, delta: number): string {
  const n = monthNumber(month) + delta
  return `${String(Math.floor(n / 12)).padStart(4, '0')}-${String((n % 12) + 1).padStart(2, '0')}`
}
