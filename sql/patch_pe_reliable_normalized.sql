-- 2026-07-21：pe_reliable 追加「遠低於常態水準」條件
--
-- 生成欄位無法用 ALTER ... SET EXPRESSION 修改，必須先 DROP 再重建。
-- 欄位是 STORED GENERATED，重建當下 Postgres 會為既有列即時算出新值，
-- 不需回填腳本、不需重跑 calculate_valuation.py。
--
-- 為什麼加這一條：TTM EPS 崩跌時改用「近 5 年常態化 EPS」推算目標價的分支
-- （calculate_valuation.py:203-211），等於賭獲利會回到歷史水準。
-- 2026-07-21 回測（2016-06 起、月採樣、持有 12 個月）：
--   TTM≤0 靠常態化判便宜   n=499  中位報酬 3.74%（全市場等權 3.65%，即隨機挑股）
--   獲利谷底(TTM<均值30%)  n=949  中位報酬 0.95%（比隨機挑股差 2.7pp）
-- 看不出選股能力，依「沒有實證支持的訊號不放推薦位」原則排除出排行榜與推薦模型。
-- 個股頁不受影響——常態化估值照常顯示，那是查詢不是推薦。

ALTER TABLE valuations DROP COLUMN IF EXISTS pe_reliable;

ALTER TABLE valuations
  ADD COLUMN pe_reliable BOOLEAN
  GENERATED ALWAYS AS (
    nonop_warning IS NULL
    AND (
      warning IS NULL
      OR (warning NOT LIKE '%EPS 長期偏低%'
          AND warning NOT LIKE '%顯著高於長期均值%'
          AND warning NOT LIKE '%遠低於常態水準%')
    )
  ) STORED;

-- 驗證：執行後應為 false ≈ 804（原 765 + 常態化分支 39）
-- SELECT pe_reliable, count(*) FROM valuations GROUP BY pe_reliable;
