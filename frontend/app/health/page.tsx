import Link from 'next/link'
import { getSupabase } from '@/lib/supabase'

// 這一頁的用途就是回答「資料有多新」，本身不能被快取——
// ISR 快取 1 小時會讓它報告過期的新鮮度（實測曾在股價已更新後仍顯示前一交易日），
// 也可能在問題已修復後繼續顯示異常。流量低，每次查詢的成本可以接受。
export const dynamic = 'force-dynamic'

export const metadata = {
  title: '資料健康狀態 — 台股估值查詢',
  description: '各資料表的新鮮度與估值模型覆蓋率',
}

// 資料庫容量刻意不顯示：那是維運資訊，看股票的人不需要知道，
// 顯示高水位只會造成無謂擔心。監控仍由 check_data_freshness.py 每日檢查並寄信。

const REFERENCE_STOCK = '2330'

/** 各資料表的「最新資料日期」。用參考股查詢以吃到 (stock_id, …) 主鍵索引——
 *  直接對整表 order by 日期會因缺少該欄索引而逾時。 */
const FRESHNESS = [
  { table: 'daily_prices',            col: 'date',             label: '日收盤價', unit: 'day' },
  { table: 'eps_quarterly',           col: 'quarter_end_date', label: '季度 EPS', unit: 'quarter' },
  { table: 'balance_sheet_quarterly', col: 'quarter_end_date', label: '每股淨值', unit: 'quarter' },
  { table: 'monthly_revenue',         col: 'year_month',       label: '月營收',   unit: 'month' },
  { table: 'cash_flows_quarterly',    col: 'quarter_end_date', label: '現金流',   unit: 'quarter' },
  // 股利是事件型資料（多數公司年配、台積電季配），不是每日更新——
  // 用日曆頻率的門檻會在兩次除息之間長期誤亮紅燈。以 event 單位放寬到約一年。
  { table: 'dividends',               col: 'ex_date',          label: '現金股利', unit: 'event' },
] as const

async function fetchFreshness() {
  const sb = getSupabase()
  return Promise.all(FRESHNESS.map(async f => {
    const { data, error } = await sb.from(f.table).select(f.col)
      .eq('stock_id', REFERENCE_STOCK).order(f.col, { ascending: false }).limit(1)
    // 查詢失敗與「確實沒有資料」是兩件事，不可混為一談
    if (error) return { ...f, value: null, failed: true }
    return { ...f, value: (data?.[0] as Record<string, string>)?.[f.col] ?? null, failed: false }
  }))
}

async function fetchCoverage() {
  const sb = getSupabase()
  const cols = 'stock_id,status,pb_status,ps_status,pfcf_status,yield_status,operating_margin,debt_ratio'
  const rows: Record<string, unknown>[] = []
  for (let offset = 0; ; offset += 1000) {
    const { data, error } = await sb.from('valuations').select(cols)
      .order('stock_id').range(offset, offset + 999)
    if (error) throw new Error(`讀取 valuations 失敗：${error.message}`)
    rows.push(...(data ?? []))
    if (!data || data.length < 1000) break
  }
  const usable = (v: unknown) => v != null && v !== '無法計算'
  return {
    total: rows.length,
    models: [
      { label: 'P/E',   n: rows.filter(r => usable(r.status)).length },
      { label: 'P/B',   n: rows.filter(r => usable(r.pb_status)).length },
      { label: 'P/S',   n: rows.filter(r => usable(r.ps_status)).length },
      { label: 'P/FCF', n: rows.filter(r => usable(r.pfcf_status)).length },
      { label: '殖利率', n: rows.filter(r => usable(r.yield_status)).length },
      { label: '營業利益率', n: rows.filter(r => r.operating_margin != null).length },
      { label: '負債比', n: rows.filter(r => r.debt_ratio != null).length },
    ],
  }
}

function fmt(value: string | null, unit: string) {
  if (!value) return '—'
  if (unit === 'quarter') return `${value.slice(0, 4)} Q${Math.ceil(+value.slice(5, 7) / 3)}`
  if (unit === 'month') return value.length === 6
    ? `${value.slice(0, 4)}/${value.slice(4)}` : value.slice(0, 7).replace('-', '/')
  return value.slice(0, 10).replace(/-/g, '/')
}

/** 資料落後多久才算異常，依該資料表的更新頻率而定 */
function staleness(value: string | null, unit: string): 'ok' | 'warn' | 'bad' {
  if (!value) return 'bad'
  const iso = unit === 'month' && value.length === 6
    ? `${value.slice(0, 4)}-${value.slice(4)}-01` : value
  const days = (Date.now() - new Date(iso).getTime()) / 86_400_000
  // event：一年最多發生幾次的事件型資料（股利），放寬到約一年才算落後
  const limit = { day: 5, month: 70, quarter: 200, event: 400 }[unit] ?? 30
  return days <= limit ? 'ok' : days <= limit * 1.5 ? 'warn' : 'bad'
}

export default async function HealthPage() {
  const [freshness, coverage] = await Promise.all([fetchFreshness(), fetchCoverage()])

  return (
    <main className="max-w-4xl mx-auto px-4 py-8 md:py-12">
      <Link href="/" className="text-sm text-blue-600 hover:underline">← 回首頁</Link>
      <header className="mt-4 mb-8">
        <h1 className="text-2xl md:text-3xl font-bold text-gray-900 mb-2">資料健康狀態</h1>
        <p className="text-gray-500">
          網站上的資料更新到什麼時候，以及每種估值涵蓋了多少股票。
        </p>
      </header>

      {/* 資料新鮮度 */}
      <section className="mb-10">
        <h2 className="text-lg font-semibold text-gray-800 mb-1">資料新鮮度</h2>
        <p className="text-sm text-gray-500 mb-4">
          各項資料的最新日期。綠燈代表如期更新，紅燈代表已經落後。
        </p>
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 divide-y divide-gray-50">
          {freshness.map(f => {
            const state = f.failed ? 'bad' : staleness(f.value, f.unit)
            return (
              <div key={f.table} className="flex items-center justify-between px-6 py-3">
                {/* 只顯示中文名稱；資料表英文名是內部實作，使用者不需要知道 */}
                <span className="text-gray-800">{f.label}</span>
                <div className="flex items-center gap-3">
                  <span className="text-sm text-gray-600">
                    {f.failed ? '查詢失敗' : fmt(f.value, f.unit)}
                  </span>
                  <span className={`w-2 h-2 rounded-full ${
                    state === 'ok' ? 'bg-green-500' : state === 'warn' ? 'bg-amber-400' : 'bg-red-500'
                  }`} />
                </div>
              </div>
            )
          })}
        </div>
      </section>

      {/* 模型覆蓋率 */}
      <section>
        <h2 className="text-lg font-semibold text-gray-800 mb-1">模型覆蓋率</h2>
        <p className="text-sm text-gray-500 mb-4">
          共 {coverage.total.toLocaleString()} 支股票。未涵蓋的多是新掛牌、
          財報年份還不夠長，或公司本身沒有公布該項資料。
        </p>
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6 space-y-3">
          {coverage.models.map(m => {
            const pct = (m.n / coverage.total) * 100
            return (
              <div key={m.label}>
                <div className="flex justify-between text-sm mb-1">
                  <span className="text-gray-700">{m.label}</span>
                  <span className="text-gray-500">
                    {m.n.toLocaleString()} 支
                    <span className="text-gray-400 ml-1.5">{pct.toFixed(0)}%</span>
                  </span>
                </div>
                <div className="h-1.5 rounded-full bg-gray-100 overflow-hidden">
                  <div className="h-full rounded-full bg-blue-400" style={{ width: `${pct}%` }} />
                </div>
              </div>
            )
          })}
        </div>
      </section>
    </main>
  )
}
