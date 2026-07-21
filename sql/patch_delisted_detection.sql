-- 2026-07-21：下市偵測欄位
--
-- 下市股的價格凍結在最後一個交易日，目標價卻仍隨財報更新，折價越算越誇張，
-- 於是專門往排行榜頂端跑。實測 2,448 檔中 120 檔已下市（4.9%），
-- 其中 6 檔佔據 P/E 便宜榜（前 6 名中 4 名），且全數計入市場溫度計的分母。
--
-- last_seen_date：最後一次出現在交易所全市場清單的資料日期（非系統日期）
-- delisted_at   ：判定下市的資料日期；NULL 表示仍在市
--
-- 執行順序：
--   1. 本檔（建欄位）
--   2. python scripts/backfill_last_seen.py   ← 補既有 2,448 檔的起始值
--   之後由 daily_price_update.py 每日自動維護，不需再手動介入。

ALTER TABLE stocks
  ADD COLUMN IF NOT EXISTS last_seen_date DATE,
  ADD COLUMN IF NOT EXISTS delisted_at    DATE;

CREATE INDEX IF NOT EXISTS idx_stocks_delisted ON stocks(delisted_at);

-- 驗證：回填後 delisted_at 非空者應為 120 檔上下
-- SELECT count(*) FILTER (WHERE delisted_at IS NOT NULL) AS 已下市,
--        count(*) FILTER (WHERE last_seen_date IS NULL)  AS 從無報價,
--        count(*) AS 全部
-- FROM stocks;
