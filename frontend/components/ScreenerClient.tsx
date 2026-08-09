'use client'

import { useMemo, useState } from 'react'
import Link from 'next/link'

export interface ScreenerRow {
  code: string
  name: string
  industry: string | null
  price: number
  roe: number | null
  margin: number | null
  debt: number | null
  yieldPct: number | null
  capYi: number | null
  pe: string | null
  pb: string | null
  ps: string | null
  pfcf: string | null
  div_: string | null
  peBad: boolean
  pbBad: boolean
}

type Model = 'pe' | 'pb' | 'ps' | 'pfcf' | 'div_'
type SortKey = 'capYi' | 'roe' | 'margin' | 'debt' | 'yieldPct' | 'price'

const MODEL_LABEL: Record<Model, string> = {
  pe: 'P/E 本益比', pb: 'P/B 股價淨值比', ps: 'P/S 股價營收比',
  pfcf: 'P/FCF 自由現金流比', div_: '殖利率',
}

const STATUS_STYLE: Record<string, string> = {
  便宜: 'text-green-600', 合理: 'text-blue-600', 昂貴: 'text-red-600',
}

/** 空字串代表「不限」——與 0 是兩件事，不可用 Number('') 的 0 當預設 */
const numOr = (s: string, fallback: number) => (s.trim() === '' ? fallback : Number(s))

interface Filters {
  industry: string
  model: Model | ''
  status: string
  roeMin: string
  marginMin: string
  debtMax: string
  yieldMin: string
  capMin: string
  capMax: string
  hideUnreliable: boolean
}

const EMPTY: Filters = {
  industry: '', model: '', status: '', roeMin: '', marginMin: '',
  debtMax: '', yieldMin: '', capMin: '', capMax: '', hideUnreliable: true,
}

export default function ScreenerClient(
  { rows, industries }: { rows: ScreenerRow[]; industries: string[] },
) {
  const [f, setF] = useState<Filters>(EMPTY)
  const [sort, setSort] = useState<{ key: SortKey; desc: boolean }>({ key: 'capYi', desc: true })

  const set = <K extends keyof Filters>(key: K, value: Filters[K]) =>
    setF(prev => ({ ...prev, [key]: value }))

  const result = useMemo(() => {
    const roeMin    = numOr(f.roeMin, -Infinity)
    const marginMin = numOr(f.marginMin, -Infinity)
    const debtMax   = numOr(f.debtMax, Infinity)
    const yieldMin  = numOr(f.yieldMin, -Infinity)
    const capMin    = numOr(f.capMin, -Infinity)
    const capMax    = numOr(f.capMax, Infinity)

    const out = rows.filter(r => {
      if (f.industry && r.industry !== f.industry) return false
      if (f.model && f.status && r[f.model] !== f.status) return false
      // 缺值一律不通過有下限／上限的條件——「沒有這個數字」不等於「達標」。
      // 用 0 或無限大頂替會讓金融股（無利益率）默默混進「利益率 ≥ 10%」的結果。
      if (f.roeMin    && (r.roe      == null || r.roe      < roeMin))    return false
      if (f.marginMin && (r.margin   == null || r.margin   < marginMin)) return false
      if (f.debtMax   && (r.debt     == null || r.debt     > debtMax))   return false
      if (f.yieldMin  && (r.yieldPct == null || r.yieldPct < yieldMin))  return false
      if (f.capMin    && (r.capYi    == null || r.capYi    < capMin))    return false
      if (f.capMax    && (r.capYi    == null || r.capYi    > capMax))    return false
      // 只擋掉「所選模型」的失真：拿 P/E 的失真去擋 P/B 查詢是張冠李戴
      if (f.hideUnreliable) {
        if ((f.model === 'pe' || !f.model) && r.peBad) return false
        if (f.model === 'pb' && r.pbBad) return false
      }
      return true
    })

    return out.sort((a, b) => {
      const x = a[sort.key], y = b[sort.key]
      // 缺值一律沉底，不論升冪降冪——否則排序會被一堆 null 佔據前排
      if (x == null) return 1
      if (y == null) return -1
      return sort.desc ? y - x : x - y
    })
  }, [rows, f, sort])

  const toggleSort = (key: SortKey) =>
    setSort(s => (s.key === key ? { key, desc: !s.desc } : { key, desc: true }))

  const Th = ({ label, k, cls = '' }: { label: string; k: SortKey; cls?: string }) => (
    <th className={`pb-2 pr-4 font-medium text-right cursor-pointer hover:text-gray-700 ${cls}`}
        onClick={() => toggleSort(k)}>
      {label}{sort.key === k && (sort.desc ? ' ↓' : ' ↑')}
    </th>
  )

  return (
    <div>
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-4 mb-5">
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3 text-sm">
          <label className="flex flex-col gap-1">
            <span className="text-gray-500 text-xs">產業</span>
            <select className="border rounded-lg px-2 py-1.5" value={f.industry}
                    onChange={e => set('industry', e.target.value)}>
              <option value="">全部</option>
              {industries.map(i => <option key={i} value={i}>{i}</option>)}
            </select>
          </label>

          <label className="flex flex-col gap-1">
            <span className="text-gray-500 text-xs">估值模型</span>
            <select className="border rounded-lg px-2 py-1.5" value={f.model}
                    onChange={e => set('model', e.target.value as Model | '')}>
              <option value="">不限</option>
              {Object.entries(MODEL_LABEL).map(([k, v]) =>
                <option key={k} value={k}>{v}</option>)}
            </select>
          </label>

          <label className="flex flex-col gap-1">
            <span className="text-gray-500 text-xs">估值狀態</span>
            <select className="border rounded-lg px-2 py-1.5 disabled:bg-gray-50"
                    value={f.status} disabled={!f.model}
                    onChange={e => set('status', e.target.value)}>
              <option value="">不限</option>
              <option value="便宜">便宜</option>
              <option value="合理">合理</option>
              <option value="昂貴">昂貴</option>
            </select>
          </label>

          {([
            ['roeMin',    'ROE ≥ (%)'],
            ['marginMin', '營業利益率 ≥ (%)'],
            ['debtMax',   '負債比 ≤ (%)'],
            ['yieldMin',  '現金殖利率 ≥ (%)'],
            ['capMin',    '市值 ≥ (億)'],
            ['capMax',    '市值 ≤ (億)'],
          ] as [keyof Filters, string][]).map(([key, label]) => (
            <label key={key} className="flex flex-col gap-1">
              <span className="text-gray-500 text-xs">{label}</span>
              <input type="number" inputMode="decimal" placeholder="不限"
                     className="border rounded-lg px-2 py-1.5"
                     value={f[key] as string}
                     onChange={e => set(key, e.target.value as Filters[typeof key])} />
            </label>
          ))}
        </div>

        <div className="flex items-center justify-between gap-4 flex-wrap mt-4 pt-3 border-t">
          <label className="flex items-center gap-2 text-sm text-gray-600">
            <input type="checkbox" checked={f.hideUnreliable}
                   onChange={e => set('hideUnreliable', e.target.checked)} />
            排除估值可能失真的股票
            <span className="text-xs text-gray-400">
              （獲利高峰／EPS 長期偏低／業外虛胖／折價過深，依所選模型判定）
            </span>
          </label>
          <button className="text-sm text-gray-500 hover:text-gray-800 underline"
                  onClick={() => setF(EMPTY)}>
            清除條件
          </button>
        </div>
      </div>

      <p className="text-sm text-gray-500 mb-2">符合條件 <strong>{result.length}</strong> 支</p>

      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-4 overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-gray-400 border-b">
              <th className="pb-2 pr-4 font-medium">代碼</th>
              <th className="pb-2 pr-4 font-medium">名稱</th>
              <th className="pb-2 pr-4 font-medium hidden md:table-cell">產業</th>
              <Th label="現價"   k="price" />
              <Th label="市值(億)" k="capYi" />
              <Th label="ROE"    k="roe" cls="hidden sm:table-cell" />
              <Th label="利益率" k="margin" cls="hidden lg:table-cell" />
              <Th label="負債比" k="debt" cls="hidden lg:table-cell" />
              <Th label="殖利率" k="yieldPct" cls="hidden sm:table-cell" />
              <th className="pb-2 font-medium text-right">
                {f.model ? MODEL_LABEL[f.model].split(' ')[0] : 'P/E'}
              </th>
            </tr>
          </thead>
          <tbody>
            {result.slice(0, 200).map(r => {
              const model = (f.model || 'pe') as Model
              const status = r[model]
              return (
                <tr key={r.code} className="border-b border-gray-50 hover:bg-gray-50">
                  <td className="py-2 pr-4 font-mono text-gray-500">
                    <Link href={`/stock/${r.code}`} className="hover:text-blue-600">{r.code}</Link>
                  </td>
                  <td className="py-2 pr-4">
                    <Link href={`/stock/${r.code}`} className="hover:text-blue-600">{r.name}</Link>
                  </td>
                  <td className="py-2 pr-4 text-gray-400 hidden md:table-cell">{r.industry ?? '—'}</td>
                  <td className="py-2 pr-4 text-right">{r.price}</td>
                  <td className="py-2 pr-4 text-right text-gray-600">{r.capYi ?? '—'}</td>
                  <td className="py-2 pr-4 text-right hidden sm:table-cell">
                    {r.roe != null ? `${r.roe}%` : '—'}
                  </td>
                  <td className="py-2 pr-4 text-right hidden lg:table-cell">
                    {r.margin != null ? `${r.margin.toFixed(1)}%` : '—'}
                  </td>
                  <td className="py-2 pr-4 text-right hidden lg:table-cell">
                    {r.debt != null ? `${r.debt.toFixed(1)}%` : '—'}
                  </td>
                  <td className="py-2 pr-4 text-right hidden sm:table-cell">
                    {r.yieldPct != null ? `${r.yieldPct}%` : '—'}
                  </td>
                  <td className={`py-2 text-right font-medium ${STATUS_STYLE[status ?? ''] ?? 'text-gray-300'}`}>
                    {status ?? '—'}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>

        {result.length === 0 && (
          <p className="py-10 text-center text-gray-400 text-sm">沒有符合條件的股票</p>
        )}
        {result.length > 200 && (
          <p className="pt-3 text-xs text-gray-400">
            僅顯示前 200 筆（共 {result.length} 筆）。請縮小條件範圍。
          </p>
        )}
      </div>

      <p className="text-xs text-gray-400 mt-3 leading-relaxed">
        「—」代表這支股票沒有這項數字，不是 0：金融股沒有營業利益率、
        虧損股沒有殖利率、淨值為負者算不出 ROE。**有下限或上限的條件會把缺值排除**，
        因為「沒有這個數字」不等於「達標」。
        市值 = 已發行股數 × 現價；殖利率為近四季現金股利 ÷ 現價。
      </p>
    </div>
  )
}
