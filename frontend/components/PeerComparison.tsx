/**
 * 同業相對估值：這支股票在同產業裡算便宜還是貴？
 *
 * 存在的理由：河流圖只比較「這支股票 vs 它自己的歷史」，
 * 回答不了「它便宜，是因為它便宜，還是整個產業都在低檔」。
 * 兩個基準會給出不同答案，而差異本身就是重要資訊——
 * 例如相對同業便宜卻高於自身歷史常態，通常代表整個產業在高檔。
 */

export interface PeerRow {
  stock_id: string
  current_price: number | null
  ttm_eps: number | null
  pb_book_value: number | null
}

// 與後端估值一致的倍數合理範圍，避免異常值扭曲同業中位數
const PE_MIN = 3, PE_MAX = 200
const PB_MIN = 0.1, PB_MAX = 50

interface Stats {
  mine: number
  median: number
  rank: number      // 由便宜到貴排第幾
  total: number
  pct: number       // 百分位，越小越便宜
}

function ratio(row: PeerRow, model: 'pe' | 'pb'): number | null {
  const base = model === 'pe' ? row.ttm_eps : row.pb_book_value
  if (!row.current_price || !base || base <= 0) return null
  const v = row.current_price / base
  const [lo, hi] = model === 'pe' ? [PE_MIN, PE_MAX] : [PB_MIN, PB_MAX]
  return v >= lo && v <= hi ? v : null
}

/** 偶數樣本取兩個中間值的平均，否則中位數會系統性偏高 */
function median(sorted: number[]): number {
  const mid = sorted.length / 2
  return sorted.length % 2 === 0
    ? (sorted[mid - 1] + sorted[mid]) / 2
    : sorted[Math.floor(mid)]
}

function peerStats(peers: PeerRow[], code: string, model: 'pe' | 'pb'): Stats | null {
  const mine = ratio(peers.find(p => p.stock_id === code) ?? {} as PeerRow, model)
  if (mine == null) return null
  const values = peers.map(p => ratio(p, model)).filter((v): v is number => v != null).sort((a, b) => a - b)
  if (values.length < 5) return null   // 同業樣本太少，排名沒有意義
  const rank = values.filter(v => v < mine).length + 1
  return { mine, median: median(values), rank, total: values.length, pct: (rank / values.length) * 100 }
}

/** 相對同業與相對自身歷史，兩個基準的組合結論 */
function verdict(pct: number, mine: number, ownMedian: number | null): string {
  const vsPeer = pct <= 33 ? '低於多數同業' : pct >= 67 ? '高於多數同業' : '與同業相當'
  if (ownMedian == null || ownMedian <= 0) return `目前${vsPeer}。`

  const vsSelf = mine < ownMedian * 0.9 ? 'low' : mine > ownMedian * 1.1 ? 'high' : 'mid'
  if (pct <= 33 && vsSelf === 'high') {
    return `${vsPeer}，但高於自身歷史常態——可能整個產業都在高檔，別只看同業排名。`
  }
  if (pct >= 67 && vsSelf === 'low') {
    return `${vsPeer}，但低於自身歷史常態——同業或許正處於低估區間。`
  }
  if (pct <= 33 && vsSelf === 'low') return `${vsPeer}，也低於自身歷史常態。`
  if (pct >= 67 && vsSelf === 'high') return `${vsPeer}，也高於自身歷史常態。`
  return `${vsPeer}。`
}

function Row({ label, s, ownMedian }: { label: string; s: Stats; ownMedian: number | null }) {
  const tone = s.pct <= 33 ? 'text-green-600' : s.pct >= 67 ? 'text-red-500' : 'text-gray-700'
  return (
    <div className="py-3 first:pt-0 last:pb-0">
      <div className="flex items-baseline justify-between flex-wrap gap-x-4 gap-y-1">
        <span className="text-sm text-gray-700">{label}</span>
        <div className="flex items-baseline gap-3 text-sm">
          <span>
            本股 <strong className={tone}>{s.mine.toFixed(1)}</strong>
          </span>
          <span className="text-gray-400">同業中位 {s.median.toFixed(1)}</span>
          <span className="text-gray-500">
            第 <strong className={tone}>{s.rank}</strong> / {s.total} 便宜
          </span>
        </div>
      </div>
      {/* 位置條：越靠左代表在同業中越便宜 */}
      <div className="mt-2 h-1.5 rounded-full bg-gradient-to-r from-green-100 via-gray-100 to-red-100 relative">
        <div
          className={`absolute top-1/2 -translate-y-1/2 -translate-x-1/2 w-2.5 h-2.5 rounded-full border-2 border-white shadow ${
            s.pct <= 33 ? 'bg-green-500' : s.pct >= 67 ? 'bg-red-500' : 'bg-gray-500'
          }`}
          style={{ left: `${Math.min(98, Math.max(2, s.pct))}%` }}
        />
      </div>
      <p className="text-xs text-gray-500 mt-2">{verdict(s.pct, s.mine, ownMedian)}</p>
    </div>
  )
}

export default function PeerComparison({
  peers, code, industry, ownFairPe, ownFairPb,
}: {
  peers: PeerRow[]
  code: string
  industry: string
  /** 自身歷史 P/E 中位數（valuations.fair_pe），用來對照「相對自己」 */
  ownFairPe: number | null
  ownFairPb: number | null
}) {
  const pe = peerStats(peers, code, 'pe')
  const pb = peerStats(peers, code, 'pb')
  if (!pe && !pb) return null

  return (
    <section className="mb-8">
      <h2 className="text-base font-semibold text-gray-700 mb-3">同業相對估值</h2>
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 px-5 py-4 divide-y divide-gray-50">
        {pe && <Row label="本益比 P/E" s={pe} ownMedian={ownFairPe} />}
        {pb && <Row label="股價淨值比 P/B" s={pb} ownMedian={ownFairPb} />}
      </div>
      <p className="text-xs text-gray-400 mt-2 px-1">
        與 {industry} 同業比較，排名由便宜到貴。倍數超出合理範圍者（P/E 3～200、P/B 0.1～50）
        不納入，避免異常值扭曲中位數。「自身歷史常態」為該股歷史倍數的第 50 百分位。
      </p>
    </section>
  )
}
