import Link from 'next/link'
import { getSupabase } from '@/lib/supabase'

export const revalidate = 3600

export const metadata = {
  title: '資料健康狀態 — 台股估值查詢',
  description: '各資料表的新鮮度、模型覆蓋率與資料庫容量',
}

/** Supabase 免費層上限；超過會被鎖為唯讀，屆時全站無法更新 */
const DB_LIMIT_MB = 500
/** 每交易日新增約 2,400 列、一年 245 個交易日、每列含索引約 90 bytes */
const GROWTH_MB_PER_YEAR = 50

const REFERENCE_STOCK = '2330'

/** 各資料表的「最新資料日期」。用參考股查詢以吃到 (stock_id, …) 主鍵索引——
 *  直接對整表 order by 日期會因缺少該欄索引而逾時。 */
const FRESHNESS = [
  { table: 'daily_prices',            col: 'date',             label: '日收盤價', unit: 'day' },
  { table: 'eps_quarterly',           col: 'quarter_end_date', label: '季度 EPS', unit: 'quarter' },
  { table: 'balance_sheet_quarterly', col: 'quarter_end_date', label: '每股淨值', unit: 'quarter' },
  { table: 'monthly_revenue',         col: 'year_month',       label: '月營收',   unit: 'month' },
  { table: 'cash_flows_quarterly',    col: 'quarter_end_date', label: '現金流',   unit: 'quarter' },
  { table: 'dividends',               col: 'ex_date',          label: '現金股利', unit: 'day' },
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

async function fetchDbSize(): Promise<number | null> {
  const { data, error } = await getSupabase().rpc('db_size_mb')
  return error ? null : Number(data)
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
  const limit = { day: 5, month: 70, quarter: 200 }[unit] ?? 30
  return days <= limit ? 'ok' : days <= limit * 1.5 ? 'warn' : 'bad'
}

export default async function HealthPage() {
  const [freshness, coverage, dbSize] = await Promise.all([
    fetchFreshness(), fetchCoverage(), fetchDbSize(),
  ])

  const usedPct = dbSize != null ? (dbSize / DB_LIMIT_MB) * 100 : null
  const monthsLeft = dbSize != null
    ? Math.max(0, (DB_LIMIT_MB - dbSize) / GROWTH_MB_PER_YEAR * 12) : null

  return (
    <main className="max-w-4xl mx-auto px-4 py-8 md:py-12">
      <Link href="/" className="text-sm text-blue-600 hover:underline">← 回首頁</Link>
      <header className="mt-4 mb-8">
        <h1 className="text-2xl md:text-3xl font-bold text-gray-900 mb-2">資料健康狀態</h1>
        <p className="text-gray-500">
          不必登入 GitHub 就能知道排程有沒有跑、資料是不是還在往前推。
          顯示的是各來源自己回報的資料日期，不是系統時間。
        </p>
      </header>

      {/* 容量 */}
      <section className="mb-10">
        <h2 className="text-lg font-semibold text-gray-800 mb-4">資料庫容量</h2>
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
          {dbSize == null ? (
            <p className="text-gray-400 text-sm">
              無法取得容量（需在資料庫建立 <code>db_size_mb()</code> 函式）
            </p>
          ) : (
            <>
              <div className="flex items-baseline justify-between mb-2">
                <span className="text-2xl font-bold text-gray-900">
                  {dbSize.toFixed(1)} <span className="text-base font-normal text-gray-400">/ {DB_LIMIT_MB} MB</span>
                </span>
                <span className={`text-sm font-semibold ${
                  usedPct! >= 90 ? 'text-red-600' : usedPct! >= 80 ? 'text-amber-500' : 'text-green-600'
                }`}>
                  {usedPct!.toFixed(1)}%
                </span>
              </div>
              <div className="h-2 rounded-full bg-gray-100 overflow-hidden">
                <div className={`h-full rounded-full ${
                  usedPct! >= 90 ? 'bg-red-500' : usedPct! >= 80 ? 'bg-amber-400' : 'bg-green-500'
                }`} style={{ width: `${Math.min(100, usedPct!)}%` }} />
              </div>
              <p className="text-xs text-gray-500 mt-3">
                以每年約 {GROWTH_MB_PER_YEAR}MB 的增長推估，剩餘空間可再撐
                <strong className="text-gray-800 mx-1">
                  {monthsLeft! >= 12 ? `${(monthsLeft! / 12).toFixed(1)} 年` : `${monthsLeft!.toFixed(0)} 個月`}
                </strong>
                。超過上限會被鎖為唯讀，屆時全站無法更新。
              </p>
              {usedPct! >= 90 && (
                <p className="text-xs text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2 mt-3">
                  已超過 90%：執行週採樣瘦身（<code>scripts/thin_daily_prices.py</code>）可換到 5 年以上緩衝。
                  注意瘦身後此數字不會下降——Postgres 的 DELETE 不歸還磁碟，
                  但釋出的空間會被後續寫入重用，實際上已停止增長。
                </p>
              )}
            </>
          )}
        </div>
      </section>

      {/* 資料新鮮度 */}
      <section className="mb-10">
        <h2 className="text-lg font-semibold text-gray-800 mb-1">資料新鮮度</h2>
        <p className="text-sm text-gray-500 mb-4">
          以參考股 {REFERENCE_STOCK} 查詢各表的最新資料日期。
        </p>
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 divide-y divide-gray-50">
          {freshness.map(f => {
            const state = f.failed ? 'bad' : staleness(f.value, f.unit)
            return (
              <div key={f.table} className="flex items-center justify-between px-6 py-3">
                <div>
                  <span className="text-gray-800">{f.label}</span>
                  <code className="text-xs text-gray-400 ml-2">{f.table}</code>
                </div>
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
          共 {coverage.total.toLocaleString()} 支股票。未涵蓋多為資料本身不存在
          （新掛牌、興櫃半年報季數不足、FinMind 無該公司財報），非計算失敗。
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
