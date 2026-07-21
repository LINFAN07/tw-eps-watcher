-- =============================================
-- 週採樣瘦身：把舊的每日股價降為「每週最後一個交易日」
--
-- 動機：daily_prices 佔 397MB（全庫 464.6/500MB＝92.9%），
-- 且每年增長約 50MB，估計 8～10 個月後 Supabase 免費層會鎖為唯讀。
--
-- 為什麼可以這樣刪：P/B / P/S / P/FCF / 殖利率本來就在內部季採樣或月採樣，
-- 只有 P/E 逐日取點。實測（2026-07-21）全體週採樣後 P/E 估值帶位移
-- 中位數 0.59%、最大 1.70%，且不改變便宜/合理/昂貴標籤。
-- 留下來的每一筆都是真實成交價，不捏造、可追溯，不違反資料誠信原則。
--
-- 【必須先完成的前置作業】
-- calculate_valuation.to_weekly() 必須已上線，讓 P/E 序列在計算時統一降週。
-- 否則「近 3 個月每日 + 更早每週」的混合密度會使近期價格權重放大約 5 倍，
-- 實測台積電 P/E 中位數偏高 7.6%、長榮 33.8%，整條估值帶被污染。
--
-- 為什麼保留近 3 個月每日：看門狗、現價判定與跨來源比對都需要每日資料。
--
-- 【已知副作用：除權息還原的基準價精度下降】（2026-07-21 執行後才發現）
-- back_adjust 的還原因子要用「除息日【前一個交易日】的收盤價」當基準，
-- 瘦身後那一天多半已被刪除，只能退用「前一個【保留的】交易日」（最多早 7 天），
-- 那幾天的股價波動會造成 factor 微小偏差。實測估值三價因此再位移 0.01~0.8%，
-- 小於週採樣本身的位移（1.7%），且用的仍是真實成交價，故接受。
--
-- 【下次改進】在 rn > 1 的刪除條件中排除「dividends.ex_date 的前一個交易日」，
-- 額外保留約 3 萬列（相對 368 萬微不足道）即可完全避免此偏差。
-- 本次已刪除的資料無法復原，故只對往後滾動的瘦身有效。
-- =============================================

-- 刪除指定股票在 p_cutoff 之前、非該週最後一個交易日的列，回傳刪除筆數。
--
-- 按 stock_id 分批呼叫（而非按列數分批）：daily_prices 主鍵為 (stock_id, date)，
-- 沒有 date 的獨立索引，若以日期範圍分批，每批都會全表掃描 400 萬列。
--
-- p_cutoff 由呼叫端以【資料本身的最新交易日】回推，不可用系統時間
-- （資料誠信原則：不得用系統時間當作資料日期）。
CREATE OR REPLACE FUNCTION thin_daily_prices(
  p_stock_ids TEXT[],
  p_cutoff    DATE,
  p_dry_run   BOOLEAN DEFAULT FALSE
)
RETURNS INTEGER
LANGUAGE plpgsql
AS $$
DECLARE
  n INTEGER;
BEGIN
  IF p_dry_run THEN
    SELECT count(*) INTO n FROM (
      SELECT row_number() OVER (
               PARTITION BY stock_id, date_trunc('week', date) ORDER BY date DESC) AS rn
      FROM daily_prices
      WHERE stock_id = ANY(p_stock_ids) AND date < p_cutoff
    ) t WHERE t.rn > 1;
    RETURN n;
  END IF;

  WITH ranked AS (
    SELECT ctid,
           row_number() OVER (
             PARTITION BY stock_id, date_trunc('week', date) ORDER BY date DESC) AS rn
    FROM daily_prices
    WHERE stock_id = ANY(p_stock_ids) AND date < p_cutoff
  )
  DELETE FROM daily_prices
  WHERE ctid IN (SELECT ctid FROM ranked WHERE rn > 1);

  GET DIAGNOSTICS n = ROW_COUNT;
  RETURN n;
END $$;

-- 瘦身後執行一次（不是 VACUUM FULL）。
-- VACUUM 把 dead tuple 標記為可重用，不需額外空間；
-- VACUUM FULL 會重寫整張表、需要約 252MB 暫存空間，在容量吃緊時會失敗，切勿使用。
--   VACUUM (ANALYZE) daily_prices;
