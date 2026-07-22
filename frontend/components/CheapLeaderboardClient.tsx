'use client'
import { useState, useMemo } from 'react'
import Link from 'next/link'
import { getTrackRecord, getWorstTrackRecord } from '@/lib/backtest'
import type { BandLevel } from '@/lib/bandStability'

export interface LeaderboardRow {
  stock_id: string
  current_price: number
  cheap_price: number
  pe_reliable?: boolean | null
  /** 便宜價 > 現價 3 倍：歷史倍數已不適用，不進排行榜 */
  pe_deep_discount?: boolean | null
  /** P/B 估值是否可信；false 代表便宜價 > 現價 2 倍，多為歷史倍數已不適用 */
  pb_reliable?: boolean | null
  warning?: string | null
  nonop_warning?: string | null
  ttm_eps?: number | null
  pb_book_value?: number | null
  operating_margin?: number | null
  /** 估值帶穩定度；僅 P/E 與 P/B 有值（其餘模型未驗證預測力，見 lib/bandStability.ts）*/
  band_level?: BandLevel | null
  stocks: { name: string; industry: string; market: string } | null
  models?: string[]  // 多模型共識標籤，如 ['P/E', 'P/B', 'P/FCF']
}

export interface LeaderboardData {
  pe: LeaderboardRow[]
  pb: LeaderboardRow[]
  ps: LeaderboardRow[]
  pfcf: LeaderboardRow[]
  consensus: LeaderboardRow[]
}

type Model = 'pe' | 'pb' | 'ps' | 'pfcf' | 'consensus'

const MODEL_META: Record<Model, { label: string; desc: string }> = {
  consensus: { label: '多模型', desc: '共識精選' },
  pe:        { label: 'P/E',   desc: '獲利估值' },
  pb:        { label: 'P/B',   desc: '資產估值' },
  ps:        { label: 'P/S',   desc: '營收估值' },
  pfcf:      { label: 'P/FCF', desc: '現金流估值' },
}

// 金融相關產業（無營業利益率，豁免利益率篩選）
const FINANCIAL_KEYWORDS = ['金融', '保險', '銀行', '證券']

function isKYStock(row: LeaderboardRow): boolean {
  return row.stocks?.name?.includes('-KY') ?? false
}

// 預設排除 KY 股的依據（回測，持有 12 個月）：KY 母體報酬中位數 −5.1%、正報酬率 43.2%，
// 而非 KY 母體是 +4.1%、56.2%。便宜訊號在 KY 股上仍有效（超額 +3.2pp，與非 KY 相當），
// 但救不回負的絕對報酬。且已下市的 KY 股早被移出 stocks 表，真實情況只會更差。
// 做成可關閉的開關而非硬性移除：這是族群統計，不是對個別公司的判決。
const KY_TOOLTIP = '此族群歷史報酬中位數 −5.1%（同期非 KY 為 +4.1%），正報酬率僅 43.2%。'
  + '便宜訊號在 KY 股上一樣有效，但拉不回負的絕對報酬。關閉此篩選即可看到它們。'

// 依據：38,274 筆便宜訊號回測，帶寬最寬的五分之一，12 個月報酬中位數 +3.4%、
// 正報酬率 55%；最窄的五分之一為 +10.0%、66%。詳見 lib/bandStability.ts。
const BAND_TOOLTIP = '估值帶＝(昂貴倍數−便宜倍數)÷合理倍數。帶太寬代表這支股票的歷史估值'
  + '散得很開，「便宜價」只是相對它自己的歷史偏低，未必真的被低估。'
  + '回測顯示帶最寬的 20% 訊號，12 個月報酬中位數僅 +3.4%（最窄組 +10.0%）。'

// 從 TTM EPS 和每股淨值推算 ROE（EPS 為負時回傳負 ROE；淨值為負時分母無意義，回傳 null）
function calcRoe(row: LeaderboardRow): number | null {
  if (row.ttm_eps != null && row.pb_book_value != null && row.pb_book_value > 0) {
    return (row.ttm_eps / row.pb_book_value) * 100
  }
  return null
}

// 品質徽章樣式
function qualityBadge(value: number, tiers: { min: number; cls: string }[]): string {
  return tiers.find(t => value >= t.min)?.cls ?? 'text-gray-400'
}

const LOSS_TIERS   = [{ min: 0, cls: 'text-red-500' }, { min: -Infinity, cls: 'text-red-600' }]
const ROE_TIERS    = [{ min: 15, cls: 'text-green-600' }, { min: 8, cls: 'text-amber-500' }, ...LOSS_TIERS]
const MARGIN_TIERS = [{ min: 20, cls: 'text-green-600' }, { min: 10, cls: 'text-amber-500' }, ...LOSS_TIERS]

export default function CheapLeaderboardClient({ data }: { data: LeaderboardData }) {
  const [model, setModel]               = useState<Model>('consensus')
  const [industry, setIndustry]         = useState<string>('全部')
  const [filterRoe, setFilterRoe]       = useState(true)   // ROE ≥ 15%
  const [filterMargin, setFilterMargin] = useState(true)   // 利益率 ≥ 10%
  const [excludeKY, setExcludeKY]       = useState(true)   // 排除 KY 股（見 KY_TOOLTIP）
  // 2026-07-22 改為預設啟用。回測（38,274 筆便宜訊號、持有 12 個月）顯示
  // 帶寬五分位 Q1→Q5 的報酬中位數 +10.00%→+3.39%、正報酬率 66.4%→54.9%，
  // 幾乎單調遞減，P/E 與 P/B 分開看都成立；排除後榜單仍有 157/392 檔，不枯竭。
  // 原本顧慮「直接隱藏會讓使用者連選擇的機會都沒有」——改以開關旁顯示
  // 「已排除 N 檔」解決：系統做了判斷就要說出來，一鍵即可看回來。
  // 已知分歧：「勝過 0050 的比率」在帶寬分組中是反向的（38.7%→47.2%），
  // 帶寬大的絕對報酬差、相對 0050 略好，因為它們較常發生在 0050 也不好的時期。
  // 三個指標中兩個支持排除，此處採信多數（同 lib/bandStability.ts 的立場）。
  const [excludeDiffuse, setExcludeDiffuse] = useState(true)

  const rows = data[model]

  // ROE 預先計算一次，filter 和 render 共用（避免雙重計算）
  const rowsWithRoe = useMemo(() => rows.map(r => ({ ...r, roe: calcRoe(r) })), [rows])

  const industries = useMemo(() => ['全部', ...Array.from(
    rows.reduce((map, r) => {
      const ind = r.stocks?.industry || '其他'
      map.set(ind, (map.get(ind) ?? 0) + 1)
      return map
    }, new Map<string, number>())
  ).sort((a, b) => b[1] - a[1]).map(([ind]) => ind)], [rows])

  // 帶寬篩選單獨留到最後：要先知道「其他條件都通過、只差帶寬」的有幾檔，
  // 才能在開關上顯示排除數量。filter 可交換，拆開不影響結果。
  const beforeDiffuse = rowsWithRoe
    // 永久排除虧損股：估值帶對虧損股無意義，不受品質篩選開關影響
    .filter(r => !((r.roe != null && r.roe < 0) || (r.operating_margin != null && r.operating_margin < 0)))
    .filter(r => industry === '全部' || (r.stocks?.industry || '其他') === industry)
    .filter(r => !excludeKY    || !isKYStock(r))
    .filter(r => !filterRoe    || (r.roe ?? 0) >= 15)
    .filter(r => {
      if (!filterMargin) return true
      if (r.operating_margin != null) return r.operating_margin >= 10
      // null 利益率：僅金融/保險/銀行/證券類股豁免，其他產業視為不符合
      const industry = r.stocks?.industry ?? ''
      return FINANCIAL_KEYWORDS.some(kw => industry.includes(kw))
    })

  const diffuseCount = beforeDiffuse.filter(r => r.band_level === 'diffuse').length
  const filtered = excludeDiffuse
    ? beforeDiffuse.filter(r => r.band_level !== 'diffuse')
    : beforeDiffuse

  // 共識 Tab：頂級優質（ROE≥15% 且利益率≥10%）置頂，其餘保持原排序
  const displayRows = model === 'consensus'
    ? [...filtered].sort((a, b) => {
        const score = (r: typeof a) =>
          (r.roe != null && r.roe >= 15 && r.operating_margin != null && r.operating_margin >= 10) ? 1 : 0
        return score(b) - score(a)
      })
    : filtered

  return (
    <>
      {/* 估值模型 Tab */}
      <div className="flex gap-1 mb-4 bg-gray-100 rounded-xl p-1">
        {(Object.keys(MODEL_META) as Model[]).map(m => (
          <button
            key={m}
            onClick={() => { setModel(m); setIndustry('全部') }}
            className={[
              'flex-1 py-1.5 rounded-lg text-sm font-medium transition-colors',
              model === m ? 'bg-white shadow-sm text-gray-800' : 'text-gray-500 hover:text-gray-700',
            ].join(' ')}
          >
            <span>{MODEL_META[m].label}</span>
            <span className="hidden sm:inline text-xs ml-1 opacity-60">{MODEL_META[m].desc}</span>
            {data[m].length > 0 && (
              <span className={`ml-1 text-xs px-1.5 rounded-full ${
                m === 'consensus'
                  ? 'bg-blue-100 text-blue-700'
                  : 'bg-green-100 text-green-700'
              }`}>
                {data[m].length}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* 產業篩選 */}
      <FilterBar industries={industries} selected={industry} onSelect={setIndustry} />

      {/* 品質篩選 */}
      <div className="flex items-center gap-2 mt-3 mb-1">
        <span className="text-xs text-gray-400">品質篩選</span>
        <QualityToggle active={filterRoe}    onClick={() => setFilterRoe(v => !v)}    label="ROE ≥ 15%" />
        <QualityToggle active={filterMargin} onClick={() => setFilterMargin(v => !v)} label="利益率 ≥ 10%" />
        <QualityToggle active={excludeKY}    onClick={() => setExcludeKY(v => !v)}    label="排除 KY 股" title={KY_TOOLTIP} />
        {/* 帶寬只在 P/E 與 P/B 驗證過。共識榜的成員本就含 P/E、P/B 便宜票，
            同樣算得出帶寬（取投票模型中最發散者），故一併提供開關；
            P/S、P/FCF 榜確實沒有資料可篩，維持不顯示。 */}
        {(model === 'pe' || model === 'pb' || model === 'consensus') && (
          <QualityToggle
            active={excludeDiffuse}
            onClick={() => setExcludeDiffuse(v => !v)}
            label="排除估值帶發散"
            title={BAND_TOOLTIP}
            count={diffuseCount}
          />
        )}
      </div>

      {/* 多模型共識說明 */}
      {model === 'consensus' && (
        <p className="text-xs text-gray-400 mt-1 mb-2">
          同時被 2 個以上估值模型認定為便宜，訊號可信度更高。排序：共識模型數量多 → 折價幅度大。
        </p>
      )}

      {filtered.length === 0 ? (
        <p className="text-gray-400 text-center py-8">此條件目前沒有符合的股票</p>
      ) : (
        <div className="overflow-x-auto mt-4">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-200 text-gray-500 text-left">
                <th className="pb-3 pr-4 font-medium">#</th>
                <th className="pb-3 pr-4 font-medium">代碼</th>
                <th className="pb-3 pr-4 font-medium">公司</th>
                <th className="pb-3 pr-4 font-medium hidden md:table-cell">產業</th>
                <th className="pb-3 pr-4 font-medium text-right hidden lg:table-cell">ROE</th>
                <th className="pb-3 pr-4 font-medium text-right hidden lg:table-cell">利益率</th>
                <th className="pb-3 pr-4 font-medium text-right">現價</th>
                <th className="pb-3 pr-4 font-medium text-right hidden sm:table-cell">
                  {model === 'consensus' ? '參考便宜價' : '便宜價'}
                </th>
                <th className="pb-3 font-medium text-right">折價</th>
              </tr>
            </thead>
            <tbody>
              {displayRows.map((r, i) => {
                const discount = (((r.cheap_price - r.current_price) / r.cheap_price) * 100).toFixed(1)
                const isKY = isKYStock(r)
                const isTopQuality = r.roe != null && r.roe >= 15
                  && r.operating_margin != null && r.operating_margin >= 10
                // KY 股帳上現金不可驗證，不適用潛力黑馬推論
                const isPotential = !isKY && !isTopQuality
                  && r.operating_margin != null && r.operating_margin >= 10
                  && r.roe != null && r.roe >= 0
                // 此模型在該產業的歷史表現。只在落後同業時標示，不標好消息——
                // 避免徽章泛濫。呈現一律中性：樣本外檢驗顯示產業差異不會延續
                // （見 lib/backtest.ts 的 OOS_CAVEAT），不該讀成預警。
                const trap = model === 'consensus'
                  ? getWorstTrackRecord(r.models, r.stocks?.industry)
                  : getTrackRecord(model, r.stocks?.industry)
                // 把來源模型帶進個股頁，估值卡才會預設顯示使用者剛才在看的那個。
                // 否則會出現「P/B 榜說便宜，點進去只看到 P/E」的矛盾。
                // 共識榜是多模型投票，沒有單一來源可帶。
                const href = model === 'consensus'
                  ? `/stock/${r.stock_id}`
                  : `/stock/${r.stock_id}?model=${model}`
                return (
                  <tr key={r.stock_id} className="border-b border-gray-50 transition-colors hover:bg-gray-50">
                    <td className="py-3 pr-4 text-gray-400">{i + 1}</td>
                    <td className="py-3 pr-4">
                      <Link href={href} className="font-mono font-bold text-blue-600 hover:underline">
                        {r.stock_id}
                      </Link>
                    </td>
                    <td className="py-3 pr-4">
                      <Link href={href} className="text-gray-800 hover:text-blue-600">
                        {r.stocks?.name ?? '—'}
                      </Link>
                      {isKY && (
                        <span className="ml-1.5 text-[10px] px-1.5 py-0.5 rounded bg-orange-50 text-orange-600 border border-orange-200 font-medium">
                          ⚠️ KY
                        </span>
                      )}
                      {/* 多模型共識徽章 */}
                      {r.models && (
                        <div className="flex gap-1 mt-0.5 flex-wrap">
                          {r.models.map(m => (
                            <span key={m} className="text-[10px] px-1.5 py-0.5 rounded bg-blue-50 text-blue-600 font-medium leading-tight">
                              {m}
                            </span>
                          ))}
                        </div>
                      )}
                      {isTopQuality && (
                        <span className="inline-block text-[10px] px-1.5 py-0.5 rounded bg-green-50 text-green-700 border border-green-200 font-medium leading-tight mt-0.5">
                          ⭐ 頂級優質
                        </span>
                      )}
                      {isPotential && (
                        <span
                          title="本業獲利強勁，但資金效率尚未完全釋放（帳上現金充沛或處於擴產期）。一旦提高配息或產能放量，ROE 有望爆發。屬進階型潛在價值股，需留意等待時間成本。"
                          className="inline-block text-[10px] px-1.5 py-0.5 rounded bg-amber-50 text-amber-600 border border-amber-200 font-medium leading-tight mt-0.5 cursor-help"
                        >
                          🔍 潛力黑馬
                        </span>
                      )}
                      {isKY && (
                        <div className="text-[10px] text-orange-600 mt-0.5">
                          帳上現金難以驗證，請留意海外資產真實性
                        </div>
                      )}
                      {/* 中性呈現：原本是紅框「🪤 產業陷阱」，等於叫使用者別碰。
                          2026-07-22 樣本外檢驗證明產業差異不會延續（前後期相關性 −0.06，
                          前期落後者後期反而略好），紅色警示是資料不支持的預測性暗示。
                          數字保留給想深究的人看，判斷不替使用者做。 */}
                      {trap?.tone === 'bad' && (
                        <span
                          title={trap.verdict}
                          className="inline-block text-[10px] px-1.5 py-0.5 rounded bg-gray-50 text-gray-500 border border-gray-200 leading-tight mt-0.5 cursor-help"
                        >
                          📉 同業歷史 {trap.excess.toFixed(1)}pp
                        </span>
                      )}
                    </td>
                    <td className="py-3 pr-4 text-gray-400 hidden md:table-cell">
                      {r.stocks?.industry ?? r.stocks?.market ?? '—'}
                    </td>
                    <td className={`py-3 pr-4 text-right font-medium hidden lg:table-cell ${r.roe != null ? qualityBadge(r.roe, ROE_TIERS) : 'text-gray-300'}`}>
                      {r.roe != null ? `${r.roe.toFixed(1)}%` : '—'}
                    </td>
                    <td className={`py-3 pr-4 text-right font-medium hidden lg:table-cell ${r.operating_margin != null ? qualityBadge(r.operating_margin, MARGIN_TIERS) : 'text-gray-300'}`}>
                      {r.operating_margin == null ? '—'
                        : Math.abs(r.operating_margin) > 100 ? '大虧'
                        : `${r.operating_margin.toFixed(1)}%`}
                    </td>
                    <td className="py-3 pr-4 text-right font-medium">{r.current_price}</td>
                    <td className="py-3 pr-4 text-right text-green-600 hidden sm:table-cell">{r.cheap_price}</td>
                    <td className="py-3 text-right">
                      <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-700">
                        -{discount}%
                      </span>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}

function FilterBar({ industries, selected, onSelect }: {
  industries: string[]
  selected: string
  onSelect: (v: string) => void
}) {
  return (
    <div className="flex flex-wrap gap-2 mb-1">
      {industries.map(ind => (
        <button
          key={ind}
          onClick={() => onSelect(ind)}
          className={`text-xs px-3 py-1 rounded-full border transition-colors ${
            selected === ind
              ? 'bg-gray-800 text-white border-gray-800'
              : 'bg-gray-50 text-gray-500 border-gray-200 hover:border-gray-400 hover:text-gray-700'
          }`}
        >
          {ind}
        </button>
      ))}
    </div>
  )
}

function QualityToggle({ active, onClick, label, title, count }: {
  active: boolean
  onClick: () => void
  label: string
  title?: string
  /** 這個開關目前濾掉幾檔。預設啟用的篩選必須把數量說出來，
      否則使用者會以為看到的就是全部，不知道系統替他做了判斷。 */
  count?: number
}) {
  return (
    <button
      onClick={onClick}
      title={title}
      className={`text-xs px-3 py-1 rounded-full border transition-colors font-medium ${
        active
          ? 'bg-green-600 text-white border-green-600'
          : 'bg-white text-gray-500 border-gray-300 hover:border-green-400 hover:text-green-600'
      }`}
    >
      {active ? '✓ ' : ''}{label}
      {count != null && count > 0 && (
        <span className={active ? 'ml-1 opacity-80' : 'ml-1 text-gray-400'}>
          （{active ? `已排除 ${count}` : `可排除 ${count}`} 檔）
        </span>
      )}
    </button>
  )
}
