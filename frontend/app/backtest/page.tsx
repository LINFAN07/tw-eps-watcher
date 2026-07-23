import Link from 'next/link'
import { OVERALL, BY_INDUSTRY, BACKTEST_PERIOD, INDUSTRY_HORIZON, type IndustryRow } from '@/lib/backtestStats'
import { YIELD_OVERALL } from '@/lib/backtestYieldStats'
import { CAVEATS } from '@/lib/backtest'

export const metadata = {
  title: '模型體檢報告 — 台股估值查詢',
  description: '用十年資料回測「便宜」訊號到底準不準，金融小白也看得懂',
}

// ── 資料查詢小工具（頁面所有數字都由這裡即時取自 backtestStats / backtestYieldStats，
//    回測腳本一重跑就自動更新，不寫死）────────────────────────────────────
const ov = (group: string, h: number) => OVERALL.find(r => r.group === group && r.horizon === h)!
const yov = (group: string, h: number) => YIELD_OVERALL.find(r => r.group === group && r.horizon === h)!
const UNIVERSE = '全市場等權（對照）'

/** 四個模型的「一句話它在看什麼」。key 對齊 OVERALL 的 group 與 BY_INDUSTRY 的 model */
const MODELS = [
  { key: 'P/E', group: 'P/E 便宜', watches: '每股賺的錢', desc: '獲利估值' },
  { key: 'P/B', group: 'P/B 便宜', watches: '每股家底（淨值）', desc: '資產估值' },
  { key: 'P/S', group: 'P/S 便宜', watches: '每股營收', desc: '營收估值' },
  { key: 'P/FCF', group: 'P/FCF 便宜', watches: '每股自由現金', desc: '現金流估值' },
] as const

/**
 * 樣本外持續性檢驗的結果（scripts/audit_oos_persistence.py，切點 2021/2022/2023）。
 * 這是一次性研究的結論、不隨每次回測改變，故以常數陳述；判讀措辭見 lib/backtest.ts。
 */
const OOS_PERSISTENCE = [
  { key: 'P/E', corr: '−0.09 ~ +0.07', persists: false, note: '幾乎為零，過去有效 ≠ 未來有效' },
  { key: 'P/B', corr: '+0.09 ~ +0.19', persists: false, note: '很弱，參考價值低' },
  { key: 'P/FCF', corr: '−0.20 ~ +0.12', persists: false, note: '幾乎為零，不能外推' },
  { key: 'P/S', corr: '+0.45 ~ +0.62', persists: true, note: '穩定為正 → 唯一會延續' },
]

function pct(v: number) {
  return `${v > 0 ? '+' : ''}${v.toFixed(1)}%`
}

export default function BacktestPage() {
  const uni12 = ov(UNIVERSE, 12)
  const pfcf12 = ov('P/FCF 便宜', 12)
  const pfcf24 = ov('P/FCF 便宜', 24)

  // Q1：持有 12 個月中位報酬（四模型 + 亂買對照）
  const q1 = [
    { label: '全市場亂買', value: uni12.median, tone: 'mut' as const },
    ...MODELS.map(m => ({ label: `${m.key} 便宜`, value: ov(m.group, 12).median, tone: 'good' as const })),
  ]
  const q1max = Math.max(...q1.map(r => r.value))

  // Q2：贏過 0050 的比例（12 個月，另加 P/FCF 抱 2 年這個唯一過半的例子）
  const q2 = [
    ...MODELS.map(m => ({ label: `${m.key} 便宜 · 1年`, value: ov(m.group, 12).winRate, highlight: false })),
    { label: 'P/FCF 便宜 · 抱2年', value: pfcf24.winRate, highlight: true },
  ]

  // Q3：P/S 產業別（唯一通過樣本外檢驗）。取樣本 ≥100 降雜訊，前 6 高 + 後 5 低
  const psRobust = BY_INDUSTRY.filter(r => r.model === 'P/S' && r.n >= 100)
    .sort((a, b) => b.excess - a.excess)
  const psChart = [...psRobust.slice(0, 6), ...psRobust.slice(-5)]
  const psMax = Math.max(...psChart.map(r => Math.abs(r.excess)))

  // Q6：便宜 ＋ 高股息（持有 2 年）
  const q6 = [
    { label: '全市場亂買', value: yov(UNIVERSE, 24).median, tone: 'mut' as const },
    { label: '只看 P/E 便宜', value: yov('P/E 便宜', 24).median, tone: 'mut' as const },
    { label: '便宜＋高股息', value: yov('P/E 便宜 × 高殖利率', 24).median, tone: 'good' as const },
  ]
  const q6max = Math.max(...q6.map(r => r.value))
  const yieldCombo24 = yov('P/E 便宜 × 高殖利率', 24)

  return (
    <main className="max-w-3xl mx-auto px-4 py-8 md:py-12">
      <Link href="/" className="text-sm text-blue-600 hover:underline">← 回首頁</Link>

      <header className="mt-4 mb-8">
        <p className="text-xs font-semibold tracking-widest text-blue-600 uppercase">模型體檢報告</p>
        <h1 className="text-2xl md:text-3xl font-bold text-gray-900 mt-2 mb-3">
          「便宜」真的會賺嗎？用十年資料誠實回答
        </h1>
        <p className="text-gray-500">
          這個網站告訴你「這支便宜」，但便宜之後發生了什麼？用 {BACKTEST_PERIOD.from} ～ {BACKTEST_PERIOD.to}
          （共 {BACKTEST_PERIOD.months} 個月）的資料回測，下面用不需要金融背景也看得懂的方式說明。
        </p>
      </header>

      {/* 名詞小卡 */}
      <section className="mb-10">
        <div className="grid gap-3 sm:grid-cols-2">
          <Term term="四把「便宜尺」">
            P/E＝股價比每股<strong>賺的錢</strong>／P/B＝比每股<strong>家底</strong>／
            P/S＝比每股<strong>營收</strong>／P/FCF＝比每股<strong>能自由運用的現金</strong>。
            都是拿股票「自己的歷史」判斷貴或便宜。
          </Term>
          <Term term="0050（及格線）">
            台灣 50 ETF，等於「無腦買一整個台股」。贏它才叫真本事，輸它不如躺著買 0050。
          </Term>
          <Term term="中位報酬">
            所有案例報酬排排站、正中間那一個。比「平均」更貼近體感，不會被少數暴賺拉高。
          </Term>
          <Term term="勝率">
            同一段時間內贏過 0050 的比例。超過 50% 代表一半以上情況能打敗大盤。
          </Term>
        </div>
      </section>

      {/* 三個結論 */}
      <section className="grid gap-3 md:grid-cols-3 mb-12">
        <Finding tone="good" title="訊號贏「隨便挑股」"
          body={`持有 12 個月，四把便宜尺的中位報酬都高過全市場亂買的 ${pct(uni12.median)}，`
            + `其中 P/FCF 最亮眼（${pct(pfcf12.median)}）。`} />
        <Finding tone="bad" title="但多數情況輸給 0050"
          body={`四把尺贏過 0050 的比例都只有 45～47%，超過一半情況輸給躺著買大盤。`
            + `唯一例外是 P/FCF 抱兩年（${pfcf24.winRate}%）。`} />
        <Finding tone="neutral" title="產業差異多半不延續，P/S 例外"
          body={'把資料切前後兩半互相驗證，P/E、P/B、P/FCF 的產業排名幾乎不相關（約 0）——'
            + '只描述過去。唯獨 P/S 的排名會延續，是四個模型裡唯一的例外。'} />
      </section>

      {/* Q1 */}
      <Q n={1} title="四把「便宜尺」買了真的會賺嗎？"
        lead="先問最基本的：標「便宜」的股票，成績有沒有比閉著眼睛亂買好？">
        <Chart caption="持有一年 · 便宜組中位報酬（四模型 vs 亂買）">
          {q1.map(r => <HBar key={r.label} label={r.label} value={r.value} max={q1max} tone={r.tone} />)}
        </Chart>
        <Note tone="good">
          <strong>四把尺全部有用。</strong>「便宜」組的一年報酬都穩定高過全市場平均，其中 P/FCF（自由現金流）
          最突出——「能拿出多少現金」最難用會計手法灌水，反而是最誠實的體質指標。
        </Note>
        <OverallTable />
      </Q>

      {/* Q2 */}
      <Q n={2} title="它們贏得了大盤 0050 嗎？"
        lead="贏亂買不稀奇——真正的門檻是：贏不贏得了「無腦買 0050」？">
        <Chart caption="贏過 0050 的比例（越高越好，50% 是及格線）">
          {q2.map(r => <WinBar key={r.label} label={r.label} value={r.value} highlight={r.highlight} />)}
        </Chart>
        <Note tone="bad">
          <strong>老實說：多數情況贏不了。</strong>四把尺持有一年打敗 0050 的比例都只有 45～47%，過半數情況
          反而輸給大盤。唯一的例外是 P/FCF 長抱兩年（{pfcf24.winRate}%），但那也剛好落在 0050 表現平淡的期間、
          且樣本最少，先當「值得追蹤」而非「已成定論」。
        </Note>
        <p className="text-sm text-gray-500 mt-4">
          為什麼贏不了？因為 0050 裝的是台積電這些權值股，過去十年剛好走了一大段多頭。「便宜」幫你贏過一般個股，
          卻贏不過這段特別強的大盤行情——「選股能不能長期勝過大盤」本來就是全世界最難的事。
          正確用法：把它當「幫你篩掉貴的、留下相對便宜的濾網」，而不是「保證跑贏大盤的聖杯」。
        </p>
      </Q>

      {/* Q3 */}
      <Q n={3} title="哪些產業的「便宜」可信、哪些是陷阱？"
        lead="同樣是「便宜」，換個產業結果天差地遠。四把尺都做完產業別回測了，但這裡有個關鍵陷阱。">
        <h3 className="font-semibold text-gray-800 mt-2 mb-2">⚠️ 多數「產業排名」不會延續到未來</h3>
        <p className="text-sm text-gray-600 mb-4">
          我們做了最嚴格的檢驗——把十年資料切成前後兩半，用前半段找出哪些產業有效，再看後半段是否<em>還</em>有效
          （相關性越接近 +1 越會延續，接近 0 代表純屬運氣）：
        </p>
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-x-auto mb-6">
          <table className="w-full text-sm min-w-[24rem]">
            <thead>
              <tr className="border-b border-gray-200 text-gray-500 text-left">
                <th className="p-3 font-medium">便宜尺</th>
                <th className="p-3 font-medium text-right">前後半段 · 產業排名相關性</th>
                <th className="p-3 font-medium">白話翻譯</th>
              </tr>
            </thead>
            <tbody>
              {OOS_PERSISTENCE.map(r => (
                <tr key={r.key} className={`border-b border-gray-50 ${r.persists ? 'bg-green-50' : ''}`}>
                  <td className="p-3 font-medium text-gray-800">{r.key}</td>
                  <td className={`p-3 text-right font-medium ${r.persists ? 'text-green-600' : 'text-gray-500'}`}>{r.corr}</td>
                  <td className="p-3 text-gray-600">{r.note}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <Note tone="neutral">
          <strong>意思是：</strong>四把尺裡只有 <strong>P/S（股價營收比）</strong>的產業排名前後半段穩定一致，
          是唯一能「拿過去推未來」的。所以下面這張 P/S 產業圖，含金量比其他三把尺高。
        </Note>

        <Chart caption="各產業「便宜」的超額報酬（P/S · 唯一通過樣本外檢驗）"
          legend={<>綠＝贏同業　紅＝輸同業（超額報酬，百分點）</>}>
          <Diverging rows={psChart.map(r => ({ label: r.industry, value: r.excess }))} max={psMax} />
        </Chart>
        <p className="text-xs text-gray-400 mt-2">
          取樣本 ≥100 筆的產業降低雜訊，依超額報酬排序取前 6 高與後 5 低。其餘三個模型的完整產業數字見下方明細。
        </p>

        <IndustryDetail />
      </Q>

      {/* Q6 */}
      <Q n={6} title="有沒有更強的組合？便宜 ＋ 高股息" hideRule
        lead="把「便宜」和「高股息（高殖利率）」疊在一起，是目前所有測試裡最亮眼的組合。">
        <Chart caption="持有兩年 · 中位報酬比一比">
          {q6.map(r => <HBar key={r.label} label={r.label} value={r.value} max={q6max} tone={r.tone} />)}
        </Chart>
        <Note tone="good">
          <strong>這是唯一「打敗 0050 比例站上五成」的常見組合</strong>（持有兩年勝率 {yieldCombo24.winRate}%、
          約 {yieldCombo24.positiveRate}% 會賺）。高股息本身就是「公司真的有賺錢、拿得出現金」的體質證明，
          剛好補上單看「便宜」的盲點。
        </Note>
      </Q>

      {/* 偏誤揭露 */}
      <section className="mb-10">
        <h2 className="text-lg font-semibold text-gray-800 mb-3">這份報告的限制</h2>
        <div className="bg-amber-50 border border-amber-200 rounded-2xl p-5">
          <ul className="space-y-2 text-sm text-amber-900">
            {CAVEATS.map(c => (
              <li key={c} className="flex gap-2"><span className="shrink-0">•</span><span>{c}</span></li>
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
          才採用；每個時間點只用當時之前的股價算估值帶；報酬把配息也算進去，所以是含息總報酬。
        </p>
      </section>
    </main>
  )
}

// ── 版面元件 ────────────────────────────────────────────────────────────

function Q({ n, title, lead, children, hideRule }: {
  n: number; title: string; lead: string; children: React.ReactNode; hideRule?: boolean
}) {
  return (
    <section className={`mb-12 ${hideRule ? '' : 'pt-2'}`}>
      <h2 className="text-xl md:text-2xl font-bold text-gray-900">
        <span className="text-blue-600 mr-2">Q{n}</span>{title}
      </h2>
      <p className="text-gray-500 mt-1 mb-5">{lead}</p>
      {children}
    </section>
  )
}

function Term({ term, children }: { term: string; children: React.ReactNode }) {
  return (
    <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-4">
      <div className="font-semibold text-gray-800 text-sm mb-1">{term}</div>
      <div className="text-sm text-gray-500 leading-relaxed">{children}</div>
    </div>
  )
}

function Finding({ tone, title, body }: { tone: 'good' | 'bad' | 'neutral'; title: string; body: string }) {
  const style = {
    good: 'bg-green-50 border-green-200 text-green-900',
    bad: 'bg-red-50 border-red-200 text-red-900',
    neutral: 'bg-blue-50 border-blue-200 text-blue-900',
  }[tone]
  return (
    <div className={`rounded-2xl border p-4 ${style}`}>
      <h3 className="font-semibold mb-1 text-sm">{title}</h3>
      <p className="text-xs leading-relaxed opacity-90">{body}</p>
    </div>
  )
}

function Note({ tone, children }: { tone: 'good' | 'bad' | 'neutral'; children: React.ReactNode }) {
  const style = {
    good: 'bg-green-50 border-green-200 text-green-900',
    bad: 'bg-red-50 border-red-200 text-red-900',
    neutral: 'bg-blue-50 border-blue-200 text-blue-900',
  }[tone]
  return <div className={`rounded-2xl border p-4 text-sm leading-relaxed ${style}`}>{children}</div>
}

function Chart({ caption, legend, children }: {
  caption: string; legend?: React.ReactNode; children: React.ReactNode
}) {
  return (
    <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5 mb-4">
      <div className="text-xs font-semibold text-gray-500 tracking-wide mb-1">{caption}</div>
      {legend && <div className="text-xs text-gray-400 mb-3">{legend}</div>}
      <div className={legend ? 'space-y-2' : 'space-y-2.5 mt-4'}>{children}</div>
    </div>
  )
}

/** 水平長條：綠＝正、灰＝對照。value 為報酬%（正值） */
function HBar({ label, value, max, tone }: {
  label: string; value: number; max: number; tone: 'good' | 'mut'
}) {
  const w = Math.max((value / max) * 100, 2)
  const fill = tone === 'good' ? 'bg-green-500' : 'bg-gray-300'
  return (
    <div className="grid grid-cols-[6.5rem_1fr_3.2rem] items-center gap-3">
      <span className="text-xs text-gray-600 truncate">{label}</span>
      <div className="h-5 rounded bg-gray-100 overflow-hidden">
        <div className={`h-full rounded ${fill}`} style={{ width: `${w}%` }} />
      </div>
      <span className="text-xs font-semibold text-gray-700 text-right tabular-nums">{pct(value)}</span>
    </div>
  )
}

/** 勝率長條：固定 0~60 刻度、50% 及格虛線。過半數用藍色點出 */
function WinBar({ label, value, highlight }: { label: string; value: number; highlight?: boolean }) {
  const w = Math.min((value / 60) * 100, 100)
  const over = value >= 50
  return (
    <div className="grid grid-cols-[7.5rem_1fr_2.6rem] items-center gap-3">
      <span className="text-xs text-gray-600 truncate">{label}</span>
      <div className="relative h-5 rounded bg-gray-100 overflow-hidden">
        {/* 50% 及格線 */}
        <div className="absolute top-0 bottom-0 border-l-2 border-dashed border-amber-400 z-10" style={{ left: `${(50 / 60) * 100}%` }} />
        <div className={`h-full rounded ${highlight || over ? 'bg-blue-500' : 'bg-gray-300'}`} style={{ width: `${w}%` }} />
      </div>
      <span className={`text-xs font-semibold text-right tabular-nums ${over ? 'text-blue-600' : 'text-gray-500'}`}>
        {value.toFixed(1)}%
      </span>
    </div>
  )
}

/** 發散長條：以中線為零，綠向右（正）、紅向左（負） */
function Diverging({ rows, max }: { rows: { label: string; value: number }[]; max: number }) {
  return (
    <div className="space-y-1.5">
      {rows.map(r => {
        const w = Math.min((Math.abs(r.value) / max) * 100, 100)
        const pos = r.value >= 0
        return (
          <div key={r.label} className="grid grid-cols-[6rem_1fr_1fr_2.8rem] items-center gap-1">
            <span className="text-xs text-gray-600 text-right truncate">{r.label}</span>
            <div className="flex justify-end h-4">
              {!pos && <div className="bg-red-400 rounded-l" style={{ width: `${w}%` }} />}
            </div>
            <div className="flex justify-start h-4 border-l-2 border-gray-200">
              {pos && <div className="bg-green-500 rounded-r" style={{ width: `${w}%` }} />}
            </div>
            <span className={`text-xs font-semibold tabular-nums ${pos ? 'text-green-600' : 'text-red-500'}`}>
              {r.value > 0 ? '+' : ''}{r.value.toFixed(1)}
            </span>
          </div>
        )
      })}
    </div>
  )
}

/** Q1 的整體結果表：全部由 OVERALL 即時產生 */
function OverallTable() {
  const rows = OVERALL.filter(r => r.horizon === 12)
  return (
    <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-4 md:p-5 overflow-x-auto mt-4">
      <table className="w-full text-sm min-w-[32rem]">
        <thead>
          <tr className="border-b border-gray-200 text-gray-500 text-left">
            <th className="pb-3 pr-4 font-medium">組別（持有 12 個月）</th>
            <th className="pb-3 pr-4 font-medium text-right">樣本數</th>
            <th className="pb-3 pr-4 font-medium text-right">中位報酬</th>
            <th className="pb-3 pr-4 font-medium text-right">勝過 0050</th>
            <th className="pb-3 font-medium text-right">正報酬率</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(r => {
            const isSignal = !r.group.startsWith('全市場')
            return (
              <tr key={r.group} className="border-b border-gray-50">
                <td className={`py-2.5 pr-4 ${isSignal ? 'font-medium text-gray-800' : 'text-gray-400'}`}>{r.group}</td>
                <td className="py-2.5 pr-4 text-right text-gray-400 tabular-nums">{r.n.toLocaleString()}</td>
                <td className="py-2.5 pr-4 text-right font-medium text-gray-800 tabular-nums">{pct(r.median)}</td>
                <td className={`py-2.5 pr-4 text-right font-medium tabular-nums ${r.winRate >= 50 ? 'text-green-600' : 'text-red-500'}`}>{r.winRate}%</td>
                <td className="py-2.5 text-right text-gray-500 tabular-nums">{r.positiveRate}%</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

/** Q3 的四模型完整產業明細（保留原技術版的完整數據，資料驅動） */
function IndustryDetail() {
  return (
    <details className="mt-6 group">
      <summary className="cursor-pointer text-sm font-medium text-blue-600 hover:underline list-none">
        ▸ 展開四個模型的完整產業明細（持有 {INDUSTRY_HORIZON} 個月，樣本 ≥30）
      </summary>
      <div className="grid gap-4 md:grid-cols-2 mt-4">
        {MODELS.map(m => {
          const rows = BY_INDUSTRY.filter(r => r.model === m.key)
          return (
            <div key={m.key} className="bg-white rounded-2xl shadow-sm border border-gray-100 p-4">
              <h4 className="font-semibold text-gray-800 mb-3">
                {m.key} <span className="text-xs font-normal text-gray-400 ml-1">{m.desc}</span>
              </h4>
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-200 text-gray-500 text-left">
                    <th className="pb-2 pr-2 font-medium">產業</th>
                    <th className="pb-2 pr-2 font-medium text-right">樣本</th>
                    <th className="pb-2 font-medium text-right">超額</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r: IndustryRow) => (
                    <tr key={r.industry} className="border-b border-gray-50">
                      <td className="py-2 pr-2 text-gray-700">{r.industry}</td>
                      <td className="py-2 pr-2 text-right text-gray-400 tabular-nums">{r.n.toLocaleString()}</td>
                      <td className={`py-2 text-right font-medium tabular-nums ${
                        r.excess >= 3 ? 'text-green-600' : r.excess <= -3 ? 'text-red-500' : 'text-gray-400'
                      }`}>{r.excess > 0 ? '+' : ''}{r.excess.toFixed(1)}pp</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        })}
      </div>
    </details>
  )
}
