import Link from 'next/link'
import { OVERALL, BY_INDUSTRY, BACKTEST_PERIOD, INDUSTRY_HORIZON } from '@/lib/backtestStats'
import { CAVEATS } from '@/lib/backtest'

export const metadata = {
  title: '模型體檢報告 — 台股估值查詢',
  description: '用十年資料回測「便宜」訊號到底準不準',
}

const MODELS = [
  { key: 'P/E', group: 'P/E 便宜', desc: '獲利估值' },
  { key: 'P/B', group: 'P/B 便宜', desc: '資產估值' },
  { key: 'P/S', group: 'P/S 便宜', desc: '營收估值' },
  { key: 'P/FCF', group: 'P/FCF 便宜', desc: '現金流估值' },
]

function pct(v: number) {
  return `${v > 0 ? '+' : ''}${v.toFixed(1)}%`
}

export default function BacktestPage() {
  const universe12 = OVERALL.find(r => r.group.startsWith('全市場') && r.horizon === 12)!

  return (
    <main className="max-w-4xl mx-auto px-4 py-8 md:py-12">
      <Link href="/" className="text-sm text-blue-600 hover:underline">← 回首頁</Link>

      <header className="mt-4 mb-8">
        <h1 className="text-2xl md:text-3xl font-bold text-gray-900 mb-2">模型體檢報告</h1>
        <p className="text-gray-500">
          這個網站告訴你「這支便宜」，但便宜之後發生了什麼？
          用 {BACKTEST_PERIOD.from} ～ {BACKTEST_PERIOD.to}（共 {BACKTEST_PERIOD.months} 個月）
          的資料回測，答案在下面。
        </p>
      </header>

      {/* 三個結論 */}
      <section className="grid gap-3 md:grid-cols-3 mb-10">
        <Finding
          tone="good"
          title="訊號贏「隨便挑股」"
          body={`持有 12 個月，P/E 便宜股報酬中位數 ${pct(OVERALL.find(r => r.group === 'P/E 便宜' && r.horizon === 12)!.median)}、`
            + `P/B ${pct(OVERALL.find(r => r.group === 'P/B 便宜' && r.horizon === 12)!.median)}，`
            + `全市場等權只有 ${pct(universe12.median)}。`}
        />
        <Finding
          tone="bad"
          title="但輸給無腦買 0050"
          body={`同期 0050 含息中位數 ${pct(OVERALL.find(r => r.group === 'P/E 便宜' && r.horizon === 12)!.bench)}，`
            + `訊號股勝過它的比率僅 ${OVERALL.find(r => r.group === 'P/E 便宜' && r.horizon === 12)!.winRate}%。`
            + '持有越久差距越大——過去十年是權值股行情。'}
        />
        <Finding
          tone="neutral"
          title="產業差異很大，但不會延續"
          body={'各產業的訊號表現差距可達 20 個百分點以上。但把資料切成前後兩半、'
            + '用前半期（2016–2021）的排名去看後半期（2022 起）：前期落後的產業有 '
            + '56% 反轉為領先，前後期相關性僅 −0.06。'
            + '這些產業差異描述的是過去，不能拿來挑未來的股票。'}
        />
      </section>

      {/* 整體結果 */}
      <section className="mb-10">
        <h2 className="text-lg font-semibold text-gray-800 mb-1">整體結果</h2>
        <p className="text-sm text-gray-500 mb-4">
          報酬為含息總報酬中位數。「勝過 0050」＝該筆訊號的報酬高於同期 0050 的比率。
        </p>
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-4 md:p-6 overflow-x-auto">
          <table className="w-full text-sm min-w-[36rem]">
            <thead>
              <tr className="border-b border-gray-200 text-gray-500 text-left">
                <th className="pb-3 pr-4 font-medium">組別</th>
                <th className="pb-3 pr-4 font-medium text-right">持有</th>
                <th className="pb-3 pr-4 font-medium text-right">樣本數</th>
                <th className="pb-3 pr-4 font-medium text-right">報酬中位數</th>
                <th className="pb-3 pr-4 font-medium text-right">0050 同期</th>
                <th className="pb-3 pr-4 font-medium text-right">勝過 0050</th>
                <th className="pb-3 font-medium text-right">正報酬率</th>
              </tr>
            </thead>
            <tbody>
              {OVERALL.map(r => {
                const isSignal = !r.group.startsWith('全市場')
                return (
                  <tr key={`${r.group}-${r.horizon}`} className="border-b border-gray-50">
                    <td className={`py-3 pr-4 ${isSignal ? 'font-medium text-gray-800' : 'text-gray-400'}`}>
                      {r.group}
                    </td>
                    <td className="py-3 pr-4 text-right text-gray-500">{r.horizon} 個月</td>
                    <td className="py-3 pr-4 text-right text-gray-400">{r.n.toLocaleString()}</td>
                    <td className="py-3 pr-4 text-right font-medium text-gray-800">{pct(r.median)}</td>
                    <td className="py-3 pr-4 text-right text-gray-500">{pct(r.bench)}</td>
                    <td className={`py-3 pr-4 text-right font-medium ${r.winRate >= 50 ? 'text-green-600' : 'text-red-500'}`}>
                      {r.winRate}%
                    </td>
                    <td className="py-3 text-right text-gray-500">{r.positiveRate}%</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </section>

      {/* 分產業 */}
      <section className="mb-10">
        <h2 className="text-lg font-semibold text-gray-800 mb-1">哪些產業的訊號可信？</h2>
        <p className="text-sm text-gray-500 mb-4">
          持有 {INDUSTRY_HORIZON} 個月、至少 30 筆才列入。「超額」＝便宜股的報酬 −{' '}
          <strong className="text-gray-700">同產業全體股票</strong>的報酬（皆取中位數）。
          跟同業比而非跟大盤比，才能區分「選股有效」與「整個產業在漲」。
        </p>
        <div className="grid gap-4 md:grid-cols-2">
          {MODELS.map(m => (
            <div key={m.key} className="bg-white rounded-2xl shadow-sm border border-gray-100 p-4 md:p-6">
              <h3 className="font-semibold text-gray-800 mb-3">
                {m.key} <span className="text-xs font-normal text-gray-400 ml-1">{m.desc}</span>
              </h3>
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-200 text-gray-500 text-left">
                    <th className="pb-2 pr-2 font-medium">產業</th>
                    <th className="pb-2 pr-2 font-medium text-right">樣本</th>
                    <th className="pb-2 font-medium text-right">超額</th>
                  </tr>
                </thead>
                <tbody>
                  {BY_INDUSTRY.filter(r => r.model === m.key).map(r => (
                    <tr key={r.industry} className="border-b border-gray-50">
                      <td className="py-2 pr-2 text-gray-700">{r.industry}</td>
                      <td className="py-2 pr-2 text-right text-gray-400">{r.n.toLocaleString()}</td>
                      <td className={`py-2 text-right font-medium ${
                        r.excess >= 3 ? 'text-green-600' : r.excess <= -3 ? 'text-red-500' : 'text-gray-400'
                      }`}>
                        {r.excess > 0 ? '+' : ''}{r.excess.toFixed(1)}pp
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
        </div>
      </section>

      {/* 偏誤揭露 */}
      <section className="mb-10">
        <h2 className="text-lg font-semibold text-gray-800 mb-3">這份報告的限制</h2>
        <div className="bg-amber-50 border border-amber-200 rounded-2xl p-5">
          <ul className="space-y-2 text-sm text-amber-900">
            {CAVEATS.map(c => (
              <li key={c} className="flex gap-2">
                <span className="shrink-0">•</span><span>{c}</span>
              </li>
            ))}
          </ul>
        </div>
      </section>

      {/* 方法 */}
      <section className="text-sm text-gray-500 space-y-2 border-t border-gray-200 pt-6">
        <h2 className="font-semibold text-gray-700">怎麼算的</h2>
        <p>
          每個月最後一個交易日，用<strong className="text-gray-700">當時可得的資料</strong>重算估值帶，
          挑出當時被判定便宜的股票，再看它們往後 6／12／24 個月的含息報酬。
        </p>
        <p>
          為了不讓結果偷看未來，做了三件事：財報要等到<strong className="text-gray-700">公司實際公布之後</strong>
          才採用，不是財報季一結束就當作已知；每個時間點只用當時之前的股價算估值帶；
          報酬把配息也算進去，所以是含息總報酬。
        </p>
      </section>
    </main>
  )
}

function Finding({ tone, title, body }: { tone: 'good' | 'bad' | 'neutral'; title: string; body: string }) {
  const style = {
    good:    'bg-green-50 border-green-200 text-green-900',
    bad:     'bg-red-50 border-red-200 text-red-900',
    neutral: 'bg-blue-50 border-blue-200 text-blue-900',
  }[tone]
  return (
    <div className={`rounded-2xl border p-4 ${style}`}>
      <h3 className="font-semibold mb-1 text-sm">{title}</h3>
      <p className="text-xs leading-relaxed opacity-90">{body}</p>
    </div>
  )
}
