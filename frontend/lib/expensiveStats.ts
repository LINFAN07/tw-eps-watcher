// 由 scripts/backtest_expensive.py 產生，請勿手動編輯。重跑會覆寫此檔。
// 手寫的警語在 expensiveBacktest.ts；那裡會比對本檔的數字，
// 不一致時只拿掉數字、保留定義性警語（不給過時數字，也不拿掉安全提醒）。

export const EXPENSIVE_STATS = {
  horizon: 12,
  n: 29683,
  excess: 2.16,
} as const
