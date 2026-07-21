import Link from 'next/link'
import { getSupabase } from '@/lib/supabase'

export const revalidate = 3600

export const metadata = {
  title: '每日市場快報 — 台股估值查詢',
  description: '今天有哪些股票剛跌進便宜區、哪些剛離開',
}

const MODEL_LABEL: Record<string, string> = {
  pe: 'P/E', pb: 'P/B', ps: 'P/S', pfcf: 'P/FCF', yield: '殖利率',
}

interface Change {
  stock_id: string
  date: string
  model: string
  from_status: string
  to_status: string
  stocks: { name: string; industry: string | null } | null
}

/**
 * 取最新一個「有變動記錄」的交易日。
 * 不用系統日期回推：休市、排程延遲都會讓兩者脫節，
 * 硬指定今天會在休市日顯示成一片空白。
 */
async function fetchLatestChanges(): Promise<{ date: string | null; changes: Change[] }> {
  const sb = getSupabase()
  const latest = await sb.from('status_changes')
    .select('date').order('date', { ascending: false }).limit(1)

  // 表尚未建立（schema.sql 未執行）與「確實沒有變動」是兩件事，要分開處理。
  // PGRST205 = PostgREST 在 schema cache 找不到該表，代表尚未部署，非查詢故障。
  if (latest.error) {
    if (latest.error.code === 'PGRST205') return { date: null, changes: [] }
    throw new Error(`讀取狀態變動失敗：${latest.error.message}`)
  }
  const date = latest.data?.[0]?.date ?? null
  if (!date) return { date: null, changes: [] }

  const { data, error } = await sb.from('status_changes')
    .select('stock_id,date,model,from_status,to_status,stocks(name,industry)')
    .eq('date', date)
  if (error) throw new Error(`讀取狀態變動失敗：${error.message}`)
  return { date, changes: (data ?? []) as unknown as Change[] }
}

function Group({ title, hint, tone, items }: {
  title: string; hint: string; tone: 'good' | 'bad' | 'plain'; items: Change[]
}) {
  if (!items.length) return null
  const style = {
    good: 'border-green-200 bg-green-50',
    bad: 'border-red-200 bg-red-50',
    plain: 'border-gray-200 bg-gray-50',
  }[tone]
  return (
    <section className="mb-6">
      <h2 className="text-base font-semibold text-gray-800 mb-1">
        {title} <span className="text-sm font-normal text-gray-400">{items.length} 筆</span>
      </h2>
      <p className="text-xs text-gray-500 mb-3">{hint}</p>
      <div className={`rounded-2xl border p-4 ${style}`}>
        <div className="flex flex-wrap gap-2">
          {items.map(c => (
            <Link
              key={`${c.stock_id}-${c.model}`}
              href={`/stock/${c.stock_id}`}
              className="inline-flex items-baseline gap-1.5 bg-white/80 hover:bg-white rounded-lg px-2.5 py-1.5 text-sm transition-colors"
            >
              <span className="font-mono text-blue-600">{c.stock_id}</span>
              <span className="text-gray-700">{c.stocks?.name ?? ''}</span>
              <span className="text-[10px] px-1 py-0.5 rounded bg-gray-100 text-gray-500">
                {MODEL_LABEL[c.model] ?? c.model}
              </span>
            </Link>
          ))}
        </div>
      </div>
    </section>
  )
}

export default async function ReportPage() {
  const { date, changes } = await fetchLatestChanges()

  const enteredCheap = changes.filter(c => c.to_status === '便宜')
  const leftCheap = changes.filter(c => c.from_status === '便宜')
  const others = changes.filter(c => c.to_status !== '便宜' && c.from_status !== '便宜')

  return (
    <main className="max-w-4xl mx-auto px-4 py-8 md:py-12">
      <Link href="/" className="text-sm text-blue-600 hover:underline">← 回首頁</Link>
      <header className="mt-4 mb-8">
        <h1 className="text-2xl md:text-3xl font-bold text-gray-900 mb-2">每日市場快報</h1>
        <p className="text-gray-500">
          {date
            ? <>資料日期 <strong className="text-gray-700">{date.replace(/-/g, '/')}</strong>——
              股價變動使估值狀態改變的股票。日期取自交易所回報，不是系統日期。</>
            : '哪些股票剛跌進便宜區、哪些剛離開。'}
        </p>
      </header>

      {!date ? (
        <div className="bg-gray-50 border border-gray-200 rounded-2xl p-6 text-sm text-gray-500">
          尚無變動記錄，第一批資料會在下一個交易日收盤後產生。
        </div>
      ) : changes.length === 0 ? (
        <p className="text-gray-400 text-sm">這個交易日沒有任何股票的估值狀態改變。</p>
      ) : (
        <>
          <Group
            title="🟢 跌進便宜區"
            hint="股價下跌使其低於便宜價。便宜不等於會漲——先看該產業的歷史實績再決定。"
            tone="good"
            items={enteredCheap}
          />
          <Group
            title="🔴 離開便宜區"
            hint="股價上漲使其高於便宜價，原本的折價已經消失。"
            tone="bad"
            items={leftCheap}
          />
          <Group
            title="其他狀態變動"
            hint="合理與昂貴之間的移動。"
            tone="plain"
            items={others}
          />
        </>
      )}

      <p className="text-xs text-gray-400 mt-8 pt-4 border-t border-gray-100">
        只記錄「便宜／合理／昂貴」之間的實際移動；與「無法計算」的互轉屬於資料狀態改變
        （財報更新、模型失效），不是市場價格造成的變化，不列入。
        記錄保留 90 天。
        想知道這些訊號準不準，見 <Link href="/backtest" className="text-blue-600 hover:underline">模型體檢報告</Link>。
      </p>
    </main>
  )
}
