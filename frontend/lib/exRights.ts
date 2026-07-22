// 除權息還原所需的兩份資料，四個河流圖 API 共用。
//
// 分兩個來源是刻意的，不是過渡狀態：
//   ex_right_factors  交易所公告的「參考價 ÷ 前收盤價」。涵蓋現金股利、配股、
//                     現金增資、減資與任何未來的新型態分派，優先使用。
//                     但只有上市有 10 年歷史，上櫃／興櫃僅每日累積。
//   dividends         股利明細，供沒有官方因子的日期自算（見 priceAdjust.ts）。
//
// 兩者的除權息日取聯集：只辦現金增資的除權息（配息配股皆為 0，如 3028 零壹
// 2026-07-17）根本不會出現在 dividends，只存在於官方因子。

import { SupabaseClient } from '@supabase/supabase-js'
import { type ExEvent } from '@/lib/priceAdjust'

export async function fetchExAdjustment(db: SupabaseClient, stockId: string) {
  const [divRes, facRes] = await Promise.all([
    db.from('dividends')
      .select('ex_date,cash_dividend,stock_dividend').eq('stock_id', stockId),
    db.from('ex_right_factors')
      .select('ex_date,prev_close,ref_price').eq('stock_id', stockId),
  ])

  // 配股必須一起帶：只還原現金股利會在配股日留下數十個百分點的假跌幅
  const exList: ExEvent[] = (divRes.data ?? []).map(d =>
    [d.ex_date, Number(d.cash_dividend ?? 0), Number(d.stock_dividend ?? 0)])

  const official: Record<string, number> = {}
  for (const f of facRes.data ?? []) {
    const prev = Number(f.prev_close)
    if (prev > 0) official[f.ex_date] = Number(f.ref_price) / prev
  }

  return { exList, official }
}
