// 除權息還原所需的資料，四個河流圖 API 共用。
//
// 分多個來源是刻意的，不是過渡狀態。優先序由高到低：
//   ex_right_factors  交易所公告的「參考價 ÷ 前收盤價」。涵蓋現金股利、配股、
//                     現金增資、減資與任何未來的新型態分派，優先使用。
//                     但只有上市有 10 年歷史，上櫃／興櫃僅每日累積。
//   unadjusted_capital_events
//                     減資／分割／換發不走除權除息公告，上面那張表接不到。
//                     由 audit_capital_events.py 三條件交叉確認後，其因子可由
//                     股數變動推得：factor = 1 ÷ share_ratio。
//                     只採計 adjustable 者（門檻是 DB 生成欄位，前後端共讀）。
//   dividends         股利明細，供沒有以上兩者的日期自算（見 priceAdjust.ts）。
//
// 除權息日取聯集：只辦現金增資的除權息（配息配股皆為 0，如 3028 零壹
// 2026-07-17）根本不會出現在 dividends，只存在於官方因子。
//
// 【與後端 ex_factors.py 必須同語意】：河流圖在這裡即時還原，估值帶由後端算，
// 兩邊對同一支股票用不同因子的話，圖上的線和卡片上的目標價會對不起來。

import { SupabaseClient } from '@supabase/supabase-js'
import { type ExEvent } from '@/lib/priceAdjust'

export async function fetchExAdjustment(db: SupabaseClient, stockId: string) {
  const [divRes, facRes, capRes] = await Promise.all([
    db.from('dividends')
      .select('ex_date,cash_dividend,stock_dividend').eq('stock_id', stockId),
    db.from('ex_right_factors')
      .select('ex_date,prev_close,ref_price').eq('stock_id', stockId),
    db.from('unadjusted_capital_events')
      .select('event_date,share_ratio').eq('stock_id', stockId).eq('adjustable', true),
  ])

  // 配股必須一起帶：只還原現金股利會在配股日留下數十個百分點的假跌幅
  const exList: ExEvent[] = (divRes.data ?? []).map(d =>
    [d.ex_date, Number(d.cash_dividend ?? 0), Number(d.stock_dividend ?? 0)])

  // ref_price 的空值檢查不可省：Number(null) 是 0，會讓 official[d] = 0，
  // 在 backAdjust 裡被判定為「有官方值但不合格」。後端 ex_factors.py 是
  // 跳過該鍵、回退自算——兩邊必須同樣語意，否則同一筆髒資料會讓
  // 前端圖表與後端估值帶對不上（目前 schema 有 NOT NULL 擋著，這是防禦）。
  const official: Record<string, number> = {}
  for (const f of facRes.data ?? []) {
    const prev = Number(f.prev_close)
    const ref = f.ref_price == null ? NaN : Number(f.ref_price)
    if (prev > 0 && Number.isFinite(ref)) official[f.ex_date] = ref / prev
  }

  // 減資／分割的推算因子。不覆寫既有鍵：同一日若已有交易所公告值，以公告值為準
  // ——那是來源直接給的，推算值是我們算的（後端 ex_factors.load_all 用 setdefault
  // 表達同一件事，兩邊必須同語意）。
  for (const c of capRes.data ?? []) {
    const ratio = Number(c.share_ratio)
    if (ratio > 0 && !(c.event_date in official)) official[c.event_date] = 1 / ratio
  }

  return { exList, official }
}
