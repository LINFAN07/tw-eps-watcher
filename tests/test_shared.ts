// TypeScript 端的共用案例驗證（另有 tests/test_shared.py 讀同一份 JSON）。
//
// 為什麼要有這支：lib/priceAdjust.ts 的 backAdjust 與 scripts/price_adjust.py 的
// back_adjust、lib/periodicity.ts 的 reportWindow 與 scripts/periodicity.py 的
// report_window，都是同一套規則的兩份實作。檔頭寫著「兩邊必須同步修改」，
// 但 2026-07-22 一天之內就漂移了三次（期數判定跑出三種答案、P/FCF 視窗停在
// 8 期、稽核用真超集判反）。人工比對只能證明「比對的那一次」一致。
//
// 兩邊讀同一份 fixture，任一邊改壞就會有一邊紅。
//
// 跑法：cd frontend && npx tsx ../tests/test_shared.ts

import { readFileSync } from 'fs'
import { join } from 'path'
import { backAdjust, type ExEvent } from '../frontend/lib/priceAdjust'
import { reportWindow, ttmPeriods, ttmMonthWindow } from '../frontend/lib/periodicity'

interface AdjustCase {
  name: string
  source: string
  dates: string[]
  closes: number[]
  ex_list: [string, number, number][]
  official: Record<string, number> | null
  expect_first: number
}

interface WindowCase {
  name: string
  source: string
  quarter_ends: string[]
  expect: number
}

interface TtmPeriodsCase {
  name: string
  source: string
  period_ends: string[]
  expect: string[] | null
}

interface TtmMonthCase {
  name: string
  source: string
  available: string[]
  end_month: string
  expect: string[] | null
}

/** 陣列或 null 的相等比較（fixture 的預期值可能是 null） */
function sameList(a: string[] | null, b: string[] | null): boolean {
  if (a === null || b === null) return a === b
  return a.length === b.length && a.every((v, i) => v === b[i])
}

const show = (v: string[] | null) => (v === null ? 'null' : `[${v.join(', ')}]`)

const TOLERANCE = 0.01
const fixture = JSON.parse(
  readFileSync(join(__dirname, 'fixtures', 'shared_cases.json'), 'utf-8'),
) as {
  back_adjust: AdjustCase[]
  report_window: WindowCase[]
  ttm_periods: TtmPeriodsCase[]
  ttm_month_window: TtmMonthCase[]
}

const failures: string[] = []

console.log('=== backAdjust ===')
for (const c of fixture.back_adjust) {
  const got = backAdjust(c.dates, c.closes, c.ex_list as ExEvent[], c.official ?? undefined)[0]
  const ok = Math.abs(got - c.expect_first) <= TOLERANCE
  console.log(`  ${ok ? '✓' : '✗'} ${c.name}`)
  if (!ok) {
    console.log(`      得到 ${got.toFixed(4)}，預期 ${c.expect_first}（${c.source}）`)
    failures.push(c.name)
  }
}

console.log('\n=== reportWindow ===')
for (const c of fixture.report_window) {
  const got = reportWindow(c.quarter_ends)
  const ok = got === c.expect
  console.log(`  ${ok ? '✓' : '✗'} ${c.name}`)
  if (!ok) {
    console.log(`      得到 ${got}，預期 ${c.expect}（${c.source}）`)
    failures.push(c.name)
  }
}

// ttmPeriods 是 reportWindow 的下一層：後者只答「一年幾期」，答不了
// 「哪幾期剛好 12 個月」。2026-08-06 修了 Python 端、漏了這一端，
// 43 支股票的河流圖因此用錯 TTM——這一段就是為此存在。
console.log('\n=== ttmPeriods ===')
for (const c of fixture.ttm_periods) {
  const got = ttmPeriods(c.period_ends)
  const ok = sameList(got, c.expect)
  console.log(`  ${ok ? '✓' : '✗'} ${c.name}`)
  if (!ok) {
    console.log(`      得到 ${show(got)}，預期 ${show(c.expect)}（${c.source}）`)
    failures.push(c.name)
  }
}

console.log('\n=== ttmMonthWindow ===')
for (const c of fixture.ttm_month_window) {
  const got = ttmMonthWindow(c.available, c.end_month)
  const ok = sameList(got, c.expect)
  console.log(`  ${ok ? '✓' : '✗'} ${c.name}`)
  if (!ok) {
    console.log(`      得到 ${show(got)}，預期 ${show(c.expect)}（${c.source}）`)
    failures.push(c.name)
  }
}

const total = fixture.back_adjust.length + fixture.report_window.length
  + fixture.ttm_periods.length + fixture.ttm_month_window.length
console.log(`\n${total - failures.length}/${total} 通過`)
if (failures.length) {
  console.log('失敗：' + failures.join('、'))
  process.exit(1)
}
