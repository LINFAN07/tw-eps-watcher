import { getSupabase } from '@/lib/supabase'
import { isPeUnreliable } from '@/lib/peReliability'
import { getBandStability } from '@/lib/bandStability'
import CheapLeaderboardClient, { type LeaderboardRow, type LeaderboardData } from './CheapLeaderboardClient'

const PAGE = 1000

/** 各模型的 (便宜, 合理, 昂貴) 倍數欄位，供計算估值帶寬 */
const RATIO_COLS: Record<string, [string, string, string] | null> = {
  pe: ['cheap_pe', 'fair_pe', 'expensive_pe'],
  pb: ['pb_cheap_pb', 'pb_fair_pb', 'pb_expensive_pb'],
  ps: null,
  pfcf: null,
}

async function fetchModel(
  db: ReturnType<typeof getSupabase>,
  model: 'pe' | 'pb' | 'ps' | 'pfcf'
): Promise<LeaderboardRow[]> {
  const statusCol = model === 'pe' ? 'status' : `${model}_status`
  const priceCol  = model === 'pe' ? 'cheap_price' : `${model}_cheap_price`
  const peExtra   = model === 'pe' ? ',pe_reliable,pe_deep_discount,warning,nonop_warning' : ''
  const pbExtra   = model === 'pb' ? ',pb_reliable' : ''
  // 估值帶穩定度只在 P/E 與 P/B 驗證過預測力（見 lib/bandStability.ts），
  // 其餘模型不取倍數欄位，也不套用這兩者的門檻
  const ratioCols = RATIO_COLS[model]
  const ratioExtra = ratioCols ? `,${ratioCols.join(',')}` : ''
  // stocks!inner + delisted_at is null：排除已下市股票。
  // 它們的價格凍結在最後一個交易日，目標價卻仍隨財報更新，折價越算越誇張，
  // 因此會專門往榜首跑（2026-07-21 實測前 6 名中有 4 名是下市股）。
  const selectFields = `stock_id,current_price,${priceCol},ttm_eps,pb_book_value,operating_margin${peExtra}${pbExtra}${ratioExtra},stocks!inner(name,industry,market)`

  // 排序鍵（現價 ÷ 便宜價）是計算值，資料庫無法排序，必須取回完整候選再排。
  // 原本只取前 200 筆，但「便宜」股最多達 525 支（P/B），
  // 導致排行榜是從任意子集挑出的前 50 名，而非真正的前 50。
  const data: Record<string, unknown>[] = []
  for (let offset = 0; ; offset += PAGE) {
    const { data: page, error } = await db.from('valuations')
      .select(selectFields)
      .eq(statusCol, '便宜')
      .gt('current_price', 0)
      .not(priceCol, 'is', null)
      .is('stocks.delisted_at', null)
      .order('stock_id')   // 固定排序，確保跨頁不重複、不遺漏
      .range(offset, offset + PAGE - 1)
    // 故障要拋出，不可吞成空清單：否則暫時性 DB 錯誤會偽裝成「沒有便宜股」
    if (error) throw new Error(`排行榜查詢失敗（${model}）：${error.message}`)
    if (!page) break
    data.push(...(page as unknown as Record<string, unknown>[]))
    if (page.length < PAGE) break
  }

  let rows: LeaderboardRow[] = data.map(r => ({
    stock_id:         r.stock_id as string,
    current_price:    Number(r.current_price),
    cheap_price:      Number(r[priceCol]),
    pe_reliable:      (r.pe_reliable as boolean | null) ?? null,
    pe_deep_discount: (r.pe_deep_discount as boolean | null) ?? null,
    pb_reliable:      (r.pb_reliable as boolean | null) ?? null,
    warning:          (r.warning as string | null) ?? null,
    nonop_warning:    (r.nonop_warning as string | null) ?? null,
    ttm_eps:          r.ttm_eps != null ? Number(r.ttm_eps) : null,
    pb_book_value:    r.pb_book_value != null ? Number(r.pb_book_value) : null,
    operating_margin: r.operating_margin != null ? Number(r.operating_margin) : null,
    band_level:       ratioCols
      ? getBandStability(r[ratioCols[0]] as number, r[ratioCols[1]] as number,
                         r[ratioCols[2]] as number, model)?.level ?? null
      : null,
    stocks:           r.stocks as { name: string; industry: string; market: string } | null,
  }))

  if (model === 'pe') {
    rows = rows.filter(r => !isPeUnreliable(r))
  }
  // P/B 便宜價超過現價 2 倍者排除：那多半不是跌得便宜，是歷史倍數已不適用
  // （公司基本面劇變，早年的高倍數對現在沒有參考價值）。回測實證：持有 12 個月，
  // 折價 2~3 倍組 -4.94%、>3 倍組 -7.72%，全市場等權為 +5.09%（皆為逐月中位數
  // 的中位，已控制時點集中）。門檻與判斷邏輯寫在 valuations.pb_reliable 生成欄位。
  if (model === 'pb') {
    rows = rows.filter(r => r.pb_reliable !== false)
  }

  return rows
    .sort((a, b) => (a.current_price / a.cheap_price) - (b.current_price / b.cheap_price))
    .slice(0, 50)
}

async function fetchConsensus(db: ReturnType<typeof getSupabase>): Promise<LeaderboardRow[]> {
  const fields = [
    'stock_id', 'current_price',
    'status', 'cheap_price', 'pe_reliable', 'pe_deep_discount', 'warning', 'nonop_warning',
    ...RATIO_COLS.pe!, ...RATIO_COLS.pb!,   // 估值帶寬：共識榜的成員本就含 P/E、P/B 便宜票
    'pb_status', 'pb_cheap_price', 'pb_reliable',
    'ps_status', 'ps_cheap_price',
    'pfcf_status', 'pfcf_cheap_price',
    'ttm_eps', 'pb_book_value', 'operating_margin',
    'stocks!inner(name,industry,market)',   // inner join 以套用下市過濾
  ].join(',')

  // 逐頁取到底，不寫死批次數（全市場已達 2238 支，原本寫死兩批會漏掉尾端）。
  // 兩次獨立查詢若未指定 order，Postgres 不保證跨查詢順序一致，可能重複或遺漏。
  const all: Record<string, unknown>[] = []
  for (let offset = 0; ; offset += PAGE) {
    const { data: page, error } = await db.from('valuations')
      .select(fields)
      .gt('current_price', 0)
      .is('stocks.delisted_at', null)
      .order('stock_id')
      .range(offset, offset + PAGE - 1)
    // 故障要拋出，不可吞成空清單（同 fetchModel）
    if (error) throw new Error(`共識排行榜查詢失敗：${error.message}`)
    if (!page) break
    all.push(...(page as unknown as Record<string, unknown>[]))
    if (page.length < PAGE) break
  }

  const rows: LeaderboardRow[] = []

  for (const r of all) {
    const warning = (r.warning as string | null) ?? null

    // P/E 需額外排除不可靠警告（獲利高峰／長期偏低／業外虛胖）
    const peValid = r.status === '便宜'
      && r.cheap_price != null
      && !isPeUnreliable({
        pe_reliable:      r.pe_reliable as boolean | null,
        pe_deep_discount: r.pe_deep_discount as boolean | null,
        warning,
        nonop_warning: r.nonop_warning as string | null,
      })

    // P/B 同樣要擋掉便宜價 > 現價 2 倍者，否則失真股會繞過單模型榜的過濾、
    // 從共識榜進來——共識榜的門檻是「兩個模型都說便宜」，不會自動排除失真票
    const pbValid = r.pb_status === '便宜' && r.pb_cheap_price != null
      && r.pb_reliable !== false

    const models: string[] = []
    if (peValid)                                                    models.push('P/E')
    if (pbValid)                                                    models.push('P/B')
    if (r.ps_status   === '便宜' && r.ps_cheap_price   != null)    models.push('P/S')
    if (r.pfcf_status === '便宜' && r.pfcf_cheap_price != null)    models.push('P/FCF')

    if (models.length < 2) continue

    // 參考便宜價必須取自「投了便宜票」的模型：若只挑第一個非 null 價格，
    // 會拿一個判定「昂貴」的模型價格去算折價，導致折價欄失真甚至變負值。
    const cheapPrice = peValid                                 ? Number(r.cheap_price)
      : pbValid                                                 ? Number(r.pb_cheap_price)
      : r.ps_status === '便宜' && r.ps_cheap_price   != null    ? Number(r.ps_cheap_price)
      : Number(r.pfcf_cheap_price)

    // 估值帶寬取「投了便宜票的模型中最發散的那個」——與 getWorstTrackRecord
    // 同一原則：只要其中一個模型的帶散得到處都是，使用者就該看到警示，
    // 不能被另一個模型的好數字稀釋。P/S、P/FCF 的帶寬未經驗證，不納入。
    const levels = [
      peValid ? getBandStability(r.cheap_pe as number, r.fair_pe as number,
                                 r.expensive_pe as number, 'pe')?.level : null,
      pbValid ? getBandStability(r.pb_cheap_pb as number, r.pb_fair_pb as number,
                                 r.pb_expensive_pb as number, 'pb')?.level : null,
    ].filter(Boolean)

    rows.push({
      stock_id:         r.stock_id as string,
      current_price:    Number(r.current_price),
      cheap_price:      cheapPrice,
      band_level:       levels.includes('diffuse') ? 'diffuse'
        : levels.includes('normal') ? 'normal'
        : levels[0] ?? null,
      warning,
      ttm_eps:          r.ttm_eps != null ? Number(r.ttm_eps) : null,
      pb_book_value:    r.pb_book_value != null ? Number(r.pb_book_value) : null,
      operating_margin: r.operating_margin != null ? Number(r.operating_margin) : null,
      stocks:           r.stocks as { name: string; industry: string; market: string } | null,
      models,
    })
  }

  // 先按共識模型數量降序，同數再按折價幅度降序
  return rows
    .sort((a, b) => {
      const countDiff = (b.models?.length ?? 0) - (a.models?.length ?? 0)
      if (countDiff !== 0) return countDiff
      return (a.current_price / a.cheap_price) - (b.current_price / b.cheap_price)
    })
    .slice(0, 50)
}

export default async function CheapLeaderboard() {
  const db = getSupabase()
  const [pe, pb, ps, pfcf, consensus] = await Promise.all([
    fetchModel(db, 'pe'),
    fetchModel(db, 'pb'),
    fetchModel(db, 'ps'),
    fetchModel(db, 'pfcf'),
    fetchConsensus(db),
  ])

  if (pe.length + pb.length + ps.length + pfcf.length === 0) {
    return <p className="text-gray-400 text-center py-8">目前沒有被低估的股票</p>
  }

  return <CheapLeaderboardClient data={{ pe, pb, ps, pfcf, consensus }} />
}
