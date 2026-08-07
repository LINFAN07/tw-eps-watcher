/**
 * 「昂貴」訊號的回測結論，供 UI 在顯示昂貴狀態時一併揭露。
 *
 * 存在的理由：這個網站對「便宜」一律附上回測實績，避免它被讀成「買了會賺」。
 * 「昂貴」需要同一道保險，而且方向相反——回測顯示它**不是**賣出訊號。
 *
 * 數字來源：scripts/backtest_expensive.py，原始輸出在
 * backtest_results/expensive_overall.csv，機器可讀的那份在 ./expensiveStats.ts。
 * **本檔是手寫的**——警語的措辭是判斷，不該自動生成；但它引用的數字必須追得上
 * 腳本，故下方以 isExpensiveInSync() 比對兩者（同 lib/qualityBacktest.ts 的做法）。
 *
 * 判準是「同月超額」而非直接比全市場等權：昂貴訊號會擠在多頭月份
 * （實測全市場 49% 同時被判昂貴），直接比會把行情誤讀成選股能力。
 */

import { EXPENSIVE_STATS } from './expensiveStats'

/**
 * P/E 昂貴組持有 12 個月的同月超額報酬（%）。正值代表「昂貴」之後反而贏過大盤。
 *
 * 這是**手寫**的值，必須等於 EXPENSIVE_STATS.excess。改動歷程：
 * 2026-08-06 由 1.86 更新為 2.09：`periodicity.ttm_windows()` 修正了「公司改變
 * 申報頻率時 TTM 會加總 15~21 個月」的缺陷（39 檔受影響）。只有走 TTM 的
 * P/E 與 P/FCF 變動，P/B 與 P/S 分毫未動——正好印證差異來源。
 * 2026-08-07 由 2.09 更新為 2.16：全快取重抓（--refresh）後樣本自 29,205 增至 29,683。
 */
export const PE_EXPENSIVE_EXCESS_12M = 2.16

/**
 * 手寫的數字是否仍等於腳本最新產出。false 代表 backtest_expensive.py 重跑過、
 * 而本檔沒跟著更新——此時不可顯示這個數字。
 */
export function isExpensiveInSync(): boolean {
  return EXPENSIVE_STATS.horizon === 12 &&
    Math.abs(EXPENSIVE_STATS.excess - PE_EXPENSIVE_EXCESS_12M) < 1e-6
}

/**
 * 顯示昂貴狀態時必須一起出現的說明。
 *
 * 措辭要同時傳達兩件事：這是**位置描述**（現價相對這支股票自己的歷史帶），
 * 以及**不是賣出訊號**（回測不支持）。少講任何一半都會被誤讀成建議。
 * 倖存者偏差是單向的，故只說「並未跑輸」，不說「所以可以放心續抱」。
 *
 * 失同步時**只拿掉回測那一句，保留定義那一句**——不同於 qualityBacktest 的
 * 整段隱藏。理由：那兩句的性質不同。定義句永遠為真、而且是一道安全提醒，
 * 拿掉它等於讓「昂貴」重新變回可能被讀成「該賣」的裸標籤；
 * 回測句帶著一個會過期的數字，過期就不該出現。
 * 「寧可不顯示也不給過時數字」的原則針對的是數字，不是警語本身。
 */
export function expensiveCaveat(): string {
  const definition =
    `「昂貴」指現價位在這支股票自己歷史估值帶的高檔，不是賣出訊號。`
  if (!isExpensiveInSync()) return definition
  return definition +
    `回測：被判昂貴的股票接下來一年並未跑輸大盤（同月超額 +${PE_EXPENSIVE_EXCESS_12M}%）。`
}
