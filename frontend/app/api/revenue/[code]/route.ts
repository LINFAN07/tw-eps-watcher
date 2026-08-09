import { NextRequest, NextResponse } from 'next/server'
import { getSupabase } from '@/lib/supabase'

/**
 * 月營收與年增率（YoY）。
 *
 * 不新增資料表也不掛排程——由 monthly_revenue 即時計算。
 * （同 lib/bandStability.ts 的取捨：推導得出來的東西不另存一份，
 * 免得多一個會過期的欄位。）
 *
 * ## 單位
 *
 * `monthly_revenue.revenue` 的單位是**元**，不是 schema.sql 註解曾寫的「千元」。
 * 實測台積電 2026-06 為 442,679,969,000 → 4,427 億元（當千元會變成 442 兆）。
 * 本路由一律在此處換算成**億元**並以 `revenueYi` 命名，讓單位寫在欄位名裡，
 * 下游不必再判斷一次——這個專案為單位錯誤付過代價。
 *
 * ## 基期為零或負數時不給數字
 *
 * 券商的營業收入含金融資產評價損益、保險業含投資與避險損益、建設業有退屋沖銷，
 * **單月為負是真實申報值**（全市場 44 支曾出現）。基期 ≤ 0 時年增率算得出來
 * 卻沒有意義，一律回 null 並附原因，不可印成一個看起來正常的百分比。
 * 這是資料誠信原則第 3 條的同型問題：不把「這題無解」變成一個數字。
 *
 * 實測（以 2026-06 為最新月，在市 2,420 支）：可算 2,151 支、缺去年同期 133 支、
 * 基期為 0 者 27 支、基期為負者 6 支。
 */

// 圖表顯示的月數。月營收是柱狀圖，10 年 120 根在手機上擠成一團，
// 3 年剛好看得到兩個完整的年度循環。YoY 需要的前 12 個月另外取，不受此限。
const DISPLAY_MONTHS = 36

interface Point {
  month: string          // YYYY-MM
  revenueYi: number      // 億元
  yoy: number | null     // 單月年增率（%）；基期 ≤ 0 或缺值時為 null
}

/** 'YYYY-MM' 往前推一年 */
function lastYear(month: string): string {
  return `${Number(month.slice(0, 4)) - 1}${month.slice(4)}`
}

/** 年增率（%）。基期缺值或 ≤ 0 時回 null——比率在那種情況下沒有意義 */
function yoyPct(current: number, base: number | undefined): number | null {
  if (base === undefined || base <= 0) return null
  return (current / base - 1) * 100
}

export async function GET(_req: NextRequest, { params }: { params: Promise<{ code: string }> }) {
  const { code } = await params

  // 單支股票最多約 130 列（10 年月營收），不會踩到 Supabase 單次 1000 筆上限，
  // 故不需分頁。查詢失敗與「確實沒資料」必須分開回報，不可都回空陣列。
  const { data, error } = await getSupabase()
    .from('monthly_revenue')
    .select('year_month,revenue')
    .eq('stock_id', code)
    .order('year_month')

  if (error)
    return NextResponse.json({ error: `月營收查詢失敗：${error.message}` }, { status: 500 })
  if (!data?.length)
    return NextResponse.json({ error: 'NO_REVENUE' }, { status: 404 })

  // year_month 是 DATE（該月第一天），取到月份即可
  const byMonth = new Map<string, number>(
    data.map(r => [String(r.year_month).slice(0, 7), Number(r.revenue)]),
  )
  const months = [...byMonth.keys()].sort()
  const latest = months[months.length - 1]

  const points: Point[] = months.slice(-DISPLAY_MONTHS).map(m => ({
    month: m,
    revenueYi: byMonth.get(m)! / 1e8,
    yoy: yoyPct(byMonth.get(m)!, byMonth.get(lastYear(m))),
  }))

  // 累計年增率（年初至今 vs 去年同期）。台股慣例，且比單月穩定。
  // 兩邊必須是**相同的月份集合**——今年有 6 個月、去年同期只抓到 5 個月時，
  // 相除得到的是「少一個月」而不是成長率。缺任一個月就不給數字。
  const [year, month] = [Number(latest.slice(0, 4)), Number(latest.slice(5, 7))]
  const ytdKeys = Array.from({ length: month },
    (_, i) => `${year}-${String(i + 1).padStart(2, '0')}`)
  const complete = ytdKeys.every(k => byMonth.has(k) && byMonth.has(lastYear(k)))
  const sum = (keys: string[]) => keys.reduce((t, k) => t + (byMonth.get(k) ?? 0), 0)

  const ytdYoy = complete
    ? yoyPct(sum(ytdKeys), sum(ytdKeys.map(lastYear)))
    : null

  const latestBase = byMonth.get(lastYear(latest))
  const yoy = yoyPct(byMonth.get(latest)!, latestBase)

  return NextResponse.json({
    points,
    summary: {
      latestMonth:   latest,
      latestRevenueYi: byMonth.get(latest)! / 1e8,
      yoy,
      // 沒有數字時說清楚為什麼，不要讓畫面只留一個「—」——
      // 「沒有資料」與「這題無解」是兩件事，混在一起使用者會以為是網站壞了
      yoyNote: yoy !== null ? null
        : latestBase === undefined ? '去年同期無資料'
        : '去年同期營收為零或負數，年增率不適用',
      ytdYoy,
      ytdMonths: complete ? month : null,
      ytdNote: ytdYoy !== null ? null
        : !complete ? '今年或去年同期有月份缺漏，累計無法比較'
        : '去年同期累計為零或負數，年增率不適用',
    },
  })
}
