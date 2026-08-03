-- =============================================
-- 台股估值查詢網站 — 資料庫 Schema
-- =============================================

-- 股票名冊
CREATE TABLE IF NOT EXISTS stocks (
  stock_id    VARCHAR(10)  PRIMARY KEY,           -- 股票代碼，例如 "2330"
  name        VARCHAR(100) NOT NULL,              -- 公司名稱，例如 "台積電"
  market      VARCHAR(10)  NOT NULL,              -- "TWSE"（上市）/ "TPEx"（上櫃）/ "Emerging"（興櫃）；由 daily_price_update.update_market() 每日以交易所清單維護
  industry    VARCHAR(100)                        -- 產業別，例如 "半導體"；由 backfill_industry.py 填入
);

-- 季度 EPS（稅後每股盈餘）
CREATE TABLE IF NOT EXISTS eps_quarterly (
  stock_id          VARCHAR(10)  NOT NULL REFERENCES stocks(stock_id),
  quarter_end_date  DATE         NOT NULL,        -- 季度截止日，例如 2026-03-31（Q1）
  eps               DECIMAL(10, 2) NOT NULL,      -- 當季稅後 EPS
  PRIMARY KEY (stock_id, quarter_end_date)
);

-- 日收盤價（近 10 年）
CREATE TABLE IF NOT EXISTS daily_prices (
  stock_id     VARCHAR(10)    NOT NULL REFERENCES stocks(stock_id),
  date         DATE           NOT NULL,
  close_price  DECIMAL(10, 2) NOT NULL,
  PRIMARY KEY (stock_id, date)
);

-- 估值結果（預計算，每日更新）
CREATE TABLE IF NOT EXISTS valuations (
  stock_id         VARCHAR(10)    PRIMARY KEY REFERENCES stocks(stock_id),
  ttm_eps          DECIMAL(10, 2),               -- 近四季 EPS 合計（TTM）
  cheap_pe         DECIMAL(6, 2),                -- 歷史 P/E 第 20 百分位數
  fair_pe          DECIMAL(6, 2),                -- 歷史 P/E 第 50 百分位數（中位數）
  expensive_pe     DECIMAL(6, 2),                -- 歷史 P/E 第 80 百分位數
  cheap_price      DECIMAL(10, 2),               -- 便宜價 = TTM EPS × cheap_pe
  fair_price       DECIMAL(10, 2),               -- 合理價 = TTM EPS × fair_pe
  expensive_price  DECIMAL(10, 2),               -- 昂貴價 = TTM EPS × expensive_pe
  current_price    DECIMAL(10, 2),               -- 今日收盤價
  status           VARCHAR(10),                  -- "便宜" / "合理" / "昂貴" / "無法計算"
  normalized_eps   DECIMAL(10, 2),               -- 近 20 季（5 年）EPS 均值；景氣谷底時的計算基準
  warning          TEXT,                         -- 警告訊息：一次性收益 / EPS 過低等異常提示
  updated_at       TIMESTAMPTZ DEFAULT NOW()
);

-- 除權息紀錄（除權息日 + 每股現金股利 + 每股股票股利）
CREATE TABLE IF NOT EXISTS dividends (
  stock_id      VARCHAR(10)    NOT NULL REFERENCES stocks(stock_id) ON DELETE CASCADE,
  ex_date       DATE           NOT NULL,            -- 除權或除息基準日
  cash_dividend DECIMAL(10, 4) NOT NULL DEFAULT 0,  -- 每股現金股利（元）
  PRIMARY KEY (stock_id, ex_date)
);

-- 每股股票股利（配股，元）。除權會讓股價機械性下跌，不還原就會被當成估值變化。
--
-- 2026-07-22 發現：原本只抓現金股利，配股造成的除權從未被還原。
-- 實例 1436：2025-07-25 原始單日跌 32.9%（台股漲跌幅上限 10%，超過必為除權息），
-- 以現金股利還原後【仍有 −26.7% 跳空】——那是配股 3.01 元造成的。
-- 影響 1,790 支（74%）：近 10 年配過股 1,310 支、減資過 480 支。
-- 方向：後向還原把歷史價換算成「今天的股數基準」，配股使股數變多，故歷史價再除以
-- (1 + 配股率) 後【更低】→ 歷史倍數更低 → 目標價更低。
-- 亦即【未還原等於高估目標價，讓股票看起來比實際便宜】（實測 1436 三價下修 25~28%）。
ALTER TABLE dividends
  ADD COLUMN IF NOT EXISTS stock_dividend DECIMAL(10, 4) NOT NULL DEFAULT 0;

-- 索引：加速股票名稱搜尋
CREATE INDEX IF NOT EXISTS idx_stocks_name ON stocks(name);
-- 註：不再建 (stock_id, 日期 DESC) 的次要索引——各表主鍵已是 (stock_id, 日期)，
--     btree 可同時服務 ASC/DESC 查詢，額外索引只是白白多存一份。
--     daily_prices 那份曾達 259MB，是免費層 500MB 爆量主因，已於 2026-07-18 移除。
--     （原 idx_eps_stock_date、idx_prices_stock_date 一併移除）

-- =============================================
-- 替代估值模型擴充（P/B、P/S、P/FCF）
-- 請在 Supabase SQL Editor 執行以下語句
-- =============================================

-- stocks 表新增流通股數（供 P/S、P/FCF 計算用；單位：千股）
ALTER TABLE stocks ADD COLUMN IF NOT EXISTS listed_shares BIGINT;

-- 每股淨值（季度，供 P/B 估值用）
CREATE TABLE IF NOT EXISTS balance_sheet_quarterly (
  stock_id             VARCHAR(10)    NOT NULL REFERENCES stocks(stock_id) ON DELETE CASCADE,
  quarter_end_date     DATE           NOT NULL,
  book_value_per_share DECIMAL(12, 4) NOT NULL,  -- 每股淨值（元）
  PRIMARY KEY (stock_id, quarter_end_date)
);
-- （idx_bsq_stock_date 已移除：與主鍵 (stock_id, quarter_end_date) 重複）

-- 月營收（供 P/S 估值用；revenue 單位：千元）
CREATE TABLE IF NOT EXISTS monthly_revenue (
  stock_id   VARCHAR(10) NOT NULL REFERENCES stocks(stock_id) ON DELETE CASCADE,
  year_month DATE        NOT NULL,  -- 該月第一天，例如 2024-01-01
  revenue    BIGINT      NOT NULL,  -- 月營收（千元）
  PRIMARY KEY (stock_id, year_month)
);
-- （idx_rev_stock_month 已移除：與主鍵 (stock_id, year_month) 重複）

-- 季度現金流量（供 P/FCF 估值用；單位：千元）
CREATE TABLE IF NOT EXISTS cash_flows_quarterly (
  stock_id         VARCHAR(10)    NOT NULL REFERENCES stocks(stock_id) ON DELETE CASCADE,
  quarter_end_date DATE           NOT NULL,
  operating_cf     DECIMAL(20, 2),  -- 營業活動現金流量（千元）
  capex            DECIMAL(20, 2),  -- 資本支出（千元，通常為負值）
  PRIMARY KEY (stock_id, quarter_end_date)
);
-- （idx_cf_stock_date 已移除：與主鍵 (stock_id, quarter_end_date) 重複）

-- valuations 表新增替代估值欄位
ALTER TABLE valuations
  ADD COLUMN IF NOT EXISTS pb_book_value        DECIMAL(12, 4),   -- 最新每股淨值（元）
  ADD COLUMN IF NOT EXISTS pb_cheap_pb          DECIMAL(6, 4),    -- 歷史 P/B 第 20 百分位
  ADD COLUMN IF NOT EXISTS pb_fair_pb           DECIMAL(6, 4),    -- 歷史 P/B 第 50 百分位
  ADD COLUMN IF NOT EXISTS pb_expensive_pb      DECIMAL(6, 4),    -- 歷史 P/B 第 80 百分位
  ADD COLUMN IF NOT EXISTS pb_cheap_price       DECIMAL(10, 2),
  ADD COLUMN IF NOT EXISTS pb_fair_price        DECIMAL(10, 2),
  ADD COLUMN IF NOT EXISTS pb_expensive_price   DECIMAL(10, 2),
  ADD COLUMN IF NOT EXISTS pb_status            VARCHAR(10),
  ADD COLUMN IF NOT EXISTS ps_revenue_per_share DECIMAL(12, 4),   -- TTM 每股營收（元）
  ADD COLUMN IF NOT EXISTS ps_cheap_ps          DECIMAL(6, 4),    -- 歷史 P/S 第 20 百分位
  ADD COLUMN IF NOT EXISTS ps_fair_ps           DECIMAL(6, 4),
  ADD COLUMN IF NOT EXISTS ps_expensive_ps      DECIMAL(6, 4),
  ADD COLUMN IF NOT EXISTS ps_cheap_price       DECIMAL(10, 2),
  ADD COLUMN IF NOT EXISTS ps_fair_price        DECIMAL(10, 2),
  ADD COLUMN IF NOT EXISTS ps_expensive_price   DECIMAL(10, 2),
  ADD COLUMN IF NOT EXISTS ps_status            VARCHAR(10),
  ADD COLUMN IF NOT EXISTS pfcf_per_share       DECIMAL(12, 4),   -- TTM 每股自由現金流（元）
  ADD COLUMN IF NOT EXISTS pfcf_cheap_pfcf      DECIMAL(6, 4),    -- 歷史 P/FCF 第 20 百分位
  ADD COLUMN IF NOT EXISTS pfcf_fair_pfcf       DECIMAL(6, 4),
  ADD COLUMN IF NOT EXISTS pfcf_expensive_pfcf  DECIMAL(6, 4),
  ADD COLUMN IF NOT EXISTS pfcf_cheap_price     DECIMAL(10, 2),
  ADD COLUMN IF NOT EXISTS pfcf_fair_price      DECIMAL(10, 2),
  ADD COLUMN IF NOT EXISTS pfcf_expensive_price DECIMAL(10, 2),
  ADD COLUMN IF NOT EXISTS pfcf_status          VARCHAR(10);

-- 季度損益表（供業外收支偵測用；單位：元 NTD）
CREATE TABLE IF NOT EXISTS income_statement_quarterly (
  stock_id         VARCHAR(10)    NOT NULL REFERENCES stocks(stock_id) ON DELETE CASCADE,
  quarter_end_date DATE           NOT NULL,
  operating_income DECIMAL(20, 2),  -- 營業利益（元）
  net_income       DECIMAL(20, 2),  -- 稅後淨利（元）
  PRIMARY KEY (stock_id, quarter_end_date)
);
-- （idx_is_stock_date 已移除：與主鍵 (stock_id, quarter_end_date) 重複）

-- valuations 表新增業外收支警告欄位
ALTER TABLE valuations
  ADD COLUMN IF NOT EXISTS nonop_warning TEXT;

-- 品質指標擴充
ALTER TABLE valuations
  ADD COLUMN IF NOT EXISTS operating_margin DECIMAL(10, 2), -- TTM 營業利益率（%）
  ADD COLUMN IF NOT EXISTS debt_ratio       DECIMAL(6, 2);  -- 最新負債比（TotalLiabilities / TotalAssets × 100）

-- 營業利益率放寬欄位寬度（2026-07-22）
--
-- 原為 DECIMAL(6,2)，最大只到 ±9999.99，calculate_quality_metrics.py 因此把值
-- clamp 到 ±999.99。但邊界值是【假數字】——畫面顯示「-999.99%」，實際上 6467
-- 是 -18,375%，使用者會當成真實比率讀。
-- 曾考慮超出範圍寫 null，實測後否決：75 支比率 < -100% 的股票中，39 支 ROE ≥0
-- （本業大虧、靠業外撐住帳面獲利），而排行榜正是靠「利益率 < 0」把它們擋掉，
-- 寫 null 會讓其中 14 支便宜股漏進榜單。故改為放寬欄位、保留真實值。
ALTER TABLE valuations
  ALTER COLUMN operating_margin TYPE DECIMAL(10, 2);

-- balance_sheet_quarterly 新增負債比欄位（每季追蹤）
ALTER TABLE balance_sheet_quarterly
  ADD COLUMN IF NOT EXISTS debt_ratio DECIMAL(6, 2);  -- 當季負債比（%）

-- 殖利率估值模型欄位
-- 邏輯：殖利率高 = 股價便宜（便宜對應第 80 百分位殖利率）
ALTER TABLE valuations
  ADD COLUMN IF NOT EXISTS yield_ttm_div         DECIMAL(10, 2),   -- TTM 現金股利（元）
  ADD COLUMN IF NOT EXISTS yield_cheap_yield     DECIMAL(6, 4),    -- 歷史殖利率第 80 百分位（%）
  ADD COLUMN IF NOT EXISTS yield_fair_yield      DECIMAL(6, 4),    -- 歷史殖利率第 50 百分位（%）
  ADD COLUMN IF NOT EXISTS yield_expensive_yield DECIMAL(6, 4),    -- 歷史殖利率第 20 百分位（%）
  ADD COLUMN IF NOT EXISTS yield_cheap_price     DECIMAL(10, 2),
  ADD COLUMN IF NOT EXISTS yield_fair_price      DECIMAL(10, 2),
  ADD COLUMN IF NOT EXISTS yield_expensive_price DECIMAL(10, 2),
  ADD COLUMN IF NOT EXISTS yield_status          VARCHAR(10);

-- ─────────────────────────────────────────────────────────
-- 修正：P/S 與 P/FCF 倍數欄位寬度不足（2026-07-17）
--
-- calculate_alt_valuations.py 允許的倍數上限為 200（PS_MAX / PFCF_MAX），
-- 但欄位定義為 DECIMAL(6, 4)，最大只能存到 99.9999。
-- 倍數落在 100~200 的股票寫入時觸發 numeric field overflow，
-- 且整筆 upsert 一併失敗，導致該股票的 P/B / P/S / P/FCF / 殖利率全部寫不進去
-- （實測全市場有 39 支受影響）。
--
-- pb_* 維持 DECIMAL(6, 4)：PB_MAX 為 50，不會溢位。
-- yield_* 維持 DECIMAL(6, 4)：殖利率以百分比儲存，不會達到 100%。
-- ─────────────────────────────────────────────────────────

ALTER TABLE valuations
  ALTER COLUMN ps_cheap_ps          TYPE DECIMAL(8, 4),
  ALTER COLUMN ps_fair_ps           TYPE DECIMAL(8, 4),
  ALTER COLUMN ps_expensive_ps      TYPE DECIMAL(8, 4),
  ALTER COLUMN pfcf_cheap_pfcf      TYPE DECIMAL(8, 4),
  ALTER COLUMN pfcf_fair_pfcf       TYPE DECIMAL(8, 4),
  ALTER COLUMN pfcf_expensive_pfcf  TYPE DECIMAL(8, 4);

-- ─────────────────────────────────────────────────────────
-- 容量監控用函式（2026-07-18）
--
-- check_data_freshness.py 每日以 rpc 呼叫此函式，取得資料庫實際大小（MB），
-- 接近 Supabase 免費層 500 MB 上限時告警。用 pg_database_size 直接量測，
-- 免 Management API token、免不可靠的 count 查詢。
-- SECURITY DEFINER 讓 anon/authenticated 角色也能呼叫。
-- ─────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION db_size_mb()
  RETURNS double precision
  LANGUAGE sql SECURITY DEFINER
  AS $$ SELECT pg_database_size(current_database()) / 1048576.0 $$;

-- ─────────────────────────────────────────────────────────
-- daily_prices 膨脹狀態（活列／死列／表大小）（2026-07-24）
--
-- 動機：db_size_mb() 只給「整庫多大」，答不出「快滿了是死列卡住還是真的在長大」。
-- 死列佔比低＝空間已回收、VACUUM 幫不上忙、容量續增只能縮短保留每日的月數；
-- 死列佔比高＝該跑一次 VACUUM (ANALYZE) daily_prices; 就能把空間變回可重用。
-- check_data_freshness.py 每日以 rpc 呼叫，純診斷、不觸發失敗。
-- pg_stat_user_tables 一般角色讀不到，故 SECURITY DEFINER。
-- ─────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION daily_prices_stats()
  RETURNS TABLE(live_tup bigint, dead_tup bigint, total_mb double precision)
  LANGUAGE sql SECURITY DEFINER
  AS $$
    SELECT n_live_tup, n_dead_tup,
           pg_total_relation_size('daily_prices') / 1048576.0
    FROM pg_stat_user_tables
    WHERE relname = 'daily_prices'
  $$;

-- ─────────────────────────────────────────────────────────
-- 股本變動偵測（減資/增資/分割）（2026-07-18）
--
-- 動機：listed_shares 只存最新值，所有「每股」序列（EPS、淨值、營收）以最新股本
-- 回算歷史，減資/增資點會在河流圖出現假斷崖，且畫面毫無提示。
-- 方向：偵測並標記（不重算歷史），符合「警告而非竄改」原則。
--
-- shares_thousand：逐季流通股數（千股），由 download_balance_sheet.py 從各季
--   CapitalStock 推得（= 股本元 / 10 / 1000）。原本每季股本抓了卻只留最新一筆，
--   此欄把歷史保存下來，才能偵測變動。
-- capital_change_warning：patch_capital_change_warning.py 偵測到相鄰季股本變動
--   ≥ 15% 時寫入的提示文字（與 warning / nonop_warning 同為 TEXT）。
-- ─────────────────────────────────────────────────────────

ALTER TABLE balance_sheet_quarterly
  ADD COLUMN IF NOT EXISTS shares_thousand BIGINT;   -- 逐季流通股數（千股）

ALTER TABLE valuations
  ADD COLUMN IF NOT EXISTS capital_change_warning TEXT;

-- ─────────────────────────────────────────────────────────
-- P/E 可靠性旗標（2026-07-18）
--
-- 「推薦模型」與「便宜排行榜」都需要判斷「這支股票的 P/E 是否失真」。
-- 判斷本身是字串比對（warning 含「EPS 長期偏低」「顯著高於長期均值」「遠低於常態水準」
-- 或有 nonop_warning）。
-- 過去這段比對散在前端 TS，與後端寫入的中文字串跨語言耦合：後端一改用詞，
-- 前端就靜默失效。改用「生成欄位」把這唯一的判斷邏輯收斂到資料庫一處：
--   - warning / nonop_warning 每次寫入時，DB 自動重算 pe_reliable，
--     不需任何重算腳本、不需回填、不需掛進排程（避開「重算漏掛排程」那類事故）。
--   - 前端只讀這個布林值，不再持有字串常數。
-- 註：ALTER 當下 Postgres 會為既有列即時計算，無 null。
-- 2026-07-21 追加「遠低於常態水準」：TTM 崩跌時改用常態化 EPS 算目標價的那條分支
-- （calculate_valuation.py:203-211）。回測證實這類訊號沒有選股能力——持有 12 個月，
-- TTM≤0 組中位報酬 3.74%（全市場等權 3.65%，等於隨機挑股），
-- 獲利谷底組 0.95%（比隨機挑股還差 2.7pp），且逐年在 −7% ~ +20% 間劇烈擺盪。
-- 依「沒有實證支持的訊號不放推薦位」原則（同 P/S、P/FCF 不顯示回測實績），
-- 排除出排行榜與推薦模型；個股頁仍照常顯示常態化估值，那是查詢不是推薦。
ALTER TABLE valuations
  ADD COLUMN IF NOT EXISTS pe_reliable BOOLEAN
  GENERATED ALWAYS AS (
    nonop_warning IS NULL
    AND (
      warning IS NULL
      OR (warning NOT LIKE '%EPS 長期偏低%'
          AND warning NOT LIKE '%顯著高於長期均值%'
          AND warning NOT LIKE '%遠低於常態水準%')
    )
  ) STORED;

-- ─────────────────────────────────────────────────────────
-- 每日估值狀態變動記錄（供「每日市場快報」使用）
--
-- valuations 只存「當前」狀態、沒有歷史，因此回答不了
-- 「今天有哪些股票剛跌進便宜區、哪些剛離開」。
-- 這張表由 daily_price_update.py 在更新狀態時順手比對記錄，只寫【有變化】的筆數，
-- 每日約數十筆，並由該腳本自動清除保留期以外的舊資料（容量吃緊，不可無限累積）。
--
-- date 一律使用【交易所回報的資料日期】，不是系統時間
-- （資料誠信原則：休市與來源延遲都會讓系統日期與交易日脫節）。
CREATE TABLE IF NOT EXISTS status_changes (
  stock_id    VARCHAR(10) NOT NULL REFERENCES stocks(stock_id),
  date        DATE        NOT NULL,       -- 來源回報的交易日
  model       VARCHAR(10) NOT NULL,       -- pe / pb / ps / pfcf / yield
  from_status VARCHAR(10) NOT NULL,       -- 便宜 / 合理 / 昂貴
  to_status   VARCHAR(10) NOT NULL,
  PRIMARY KEY (stock_id, date, model)
);
-- 主鍵前綴為 stock_id，「查最近一日的所有變動」用不到它，故另建 date 索引。
-- 這與主鍵沒有功能重疊（曾因重複索引使資料庫暴增 259MB，勿再重蹈）。
CREATE INDEX IF NOT EXISTS idx_status_changes_date ON status_changes(date DESC);

-- ─────────────────────────────────────────────────────────
-- 除權息還原：改採「即時計算、不儲存」（2026-07-18）
--
-- 原本規劃把後向還原價存進 daily_prices.adjusted_close，但實測那會使更新膨脹，
-- 免費層 500MB 容不下（更新約 200 萬列會暫時多出 ~160MB、永久 +16MB 逼近上限）。
-- 改為在 calculate_valuation / calculate_alt_valuations 與前端河流圖 API 用手上的
-- dividends 即時還原（見 scripts/price_adjust.py 與 frontend/lib/priceAdjust.ts），
-- 零儲存、零膨脹。故此處【不建】adjusted_close 欄位。
--
-- 【2026-07-21 查證訂正】此處原本寫「若先前已建過該欄（全為 null、無害）」——
-- 那是錯的。該欄不但已建立，而且【已寫入資料】（抽查 2330 有 2,427 筆有值），
-- 是 compute_adjusted_prices.py 那次啟用留下的。程式碼現已完全不再引用它
-- （前後端皆改為即時還原），屬死欄位，正在白佔容量：
--   ALTER TABLE daily_prices DROP COLUMN IF EXISTS adjusted_close;
--
-- 注意 DROP COLUMN 的真實效果：Postgres 只把欄位標記為 dropped，
-- 既有列的資料【不會】歸還磁碟，只有該列被重寫時才釋放。daily_prices 幾乎
-- 只 INSERT 不 UPDATE，所以舊資料的空間不會自行回收——DROP 的實益是
-- 阻止未來每日新增的列再帶這一欄。要真正回收需 VACUUM FULL 重寫整張表，
-- 但那需要約等於表大小的暫存空間，在容量吃緊時反而危險（2026-07-21 實測
-- 已用 464.6MB / 500MB = 92.9%）。故：先 DROP，回收另行評估。
-- ─────────────────────────────────────────────────────────

-- ─────────────────────────────────────────────────────────
-- 下市偵測（2026-07-21）
--
-- 為什麼需要：下市股的價格凍結在最後一個交易日，但目標價仍隨財報更新，
-- 折價因此越算越誇張，這些「買不到的股票」會專門往排行榜頂端跑。
-- 2026-07-21 實測：2,448 檔中有 120 檔已下市（4.9%），其中 6 檔佔據
-- P/E 便宜榜（前 6 名中 4 名），且全數計入市場溫度計的分母。
-- 跨來源驗證：抽查 9 檔，全部不在 TWSE 上市與 TPEx 上櫃名單，確為真下市。
--
-- last_seen_date：最後一次出現在交易所全市場清單的「資料日期」（非系統日期）。
-- delisted_at   ：判定下市的資料日期；NULL 表示仍在市。
--
-- 判定規則寫在 daily_price_update.mark_delisted()：缺席超過 21 個日曆日
-- （約 15 個交易日）才標記，長假與短期停牌不會誤判；一旦重新出現即自動清除，
-- 停牌復牌不需人工介入。
--
-- 關鍵前提：任一市場抓取失敗的當日【不得】執行判定——那會把「來源故障」
-- 誤判成「整個市場下市」。呼應「抓取失敗必須讓工作失敗」原則。
ALTER TABLE stocks
  ADD COLUMN IF NOT EXISTS last_seen_date DATE,
  ADD COLUMN IF NOT EXISTS delisted_at    DATE;

CREATE INDEX IF NOT EXISTS idx_stocks_delisted ON stocks(delisted_at);

-- ─────────────────────────────────────────────────────────
-- 除權息還原因子（2026-07-22）
--
-- 為什麼需要：原本的還原因子由「現金股利 ＋ 配股」自算，
-- 公式為 (前收 − 現金股利) ÷ (前收 × (1 + 配股率))。
-- 該公式對「只有配息配股」的情況完全正確——2026-07-22 實測 1808／2540／3056
-- 三檔的還原價與交易所公告參考價分毫不差。
--
-- 但它涵蓋不了現金增資與減資，`price_adjust.py` 一直把兩者列為已知限制。
-- audit_external.py 首次量化：近 20 天 217 筆除權息中有 6 筆對不上，全是這個原因。
--
--   8112 至上 2026-07-06  現金股利 3.80 ＋ 現金增資 40,000,000 股（認購價 66）
--                         只扣股利 → 還原價 89.10 vs 公告 87.53
--   3028 零壹 2026-07-17  配息配股皆為 0，只有現金增資
--                         → dividends 表根本沒有這筆，等於完全沒還原
--
-- 解法是不再自己推公式，直接存交易所公告的兩個價格，相除即為還原因子。
-- 這涵蓋現金股利、配股、現金增資、減資，以及任何未來出現的新型態分派。
--
-- 只存來源提供的原始值，factor 由程式即時計算（衍生值不入庫，
-- 這樣每個欄位都答得出「這是誰給的、哪一天的」）。
--
-- 涵蓋範圍的落差要講明：
--   上市（TWT49U）      2016-01 起 10,694 筆，一次請求可全數回補
--   上櫃（tpex_exright_daily）只有當日 8 筆，無歷史，須每日累積
-- 因此上櫃／興櫃的歷史仍走自算路徑（現狀不變，不會變差）。
CREATE TABLE IF NOT EXISTS ex_right_factors (
    stock_id   TEXT    NOT NULL,
    ex_date    DATE    NOT NULL,
    prev_close NUMERIC NOT NULL,   -- 交易所公告「除權息前收盤價」
    ref_price  NUMERIC NOT NULL,   -- 交易所公告「除權息參考價」
    source     TEXT    NOT NULL,   -- 'TWSE' / 'TPEX'，兩者涵蓋期間不同，查問題時要分得出來
    PRIMARY KEY (stock_id, ex_date)
);

CREATE INDEX IF NOT EXISTS idx_erf_stock ON ex_right_factors(stock_id, ex_date);
-- P/B 可靠性旗標（2026-07-22）
--
-- P/E 有 pe_reliable 擋掉失真的股票，P/B 一直沒有等價機制。
-- 症狀：目標價遠高於現價的股票會盤據 P/B 便宜榜，而那多半不是「跌得很便宜」，
-- 是歷史倍數已經不適用了——公司基本面劇變，早年的高倍數對現在毫無參考價值。
--
--   4763 材料*-KY：每股淨值 10 年成長 8 倍（2.74 → 21.82，持續增資），
--   股價卻腰斬（107.5 → 50.3）。歷史 P/B 從 39 倍掉到 2.3 倍，
--   拿 30 幾倍的歷史中位數乘上今天的淨值 → 目標價 830 元，判定「便宜」。
--   資料全對，模型不適用。
--
-- 門檻取自回測，不是憑感覺。以「便宜價 ÷ 現價」分組，持有 12 個月，
-- 用逐月中位數的中位（控制時點集中，避免訊號擠在特定行情造成假象）：
--
--     全市場等權（對照）      +5.09%
--     P/B 折價 1.0~1.25      +4.90%   （22,167 筆）
--     P/B 折價 1.25~1.5      +0.66%   （ 4,744 筆）
--     P/B 折價 1.5~2         +2.31%   （ 1,912 筆）
--     P/B 折價 2~3           -4.94%   （   406 筆）
--     P/B 折價 >3            -7.72%   （    86 筆）
--
-- 超過 2 倍就轉為負報酬，且非時點偏誤：>3 那組跨 47 個月、27 檔股票、
-- 年度分布 2018~2025，控制時點後方向不變。故門檻定在 2 倍。
--
-- 注意 P/E 的臨界點不同（要到 3 倍才轉負：2~3 組 +1.00%、>3 組 -5.71%）。
-- 淨值是存量、變動慢，P/B 帶一旦失真就是結構性的；EPS 波動大，
-- 2 倍折價還可能是景氣循環的谷底。因此兩者不共用同一個門檻。
--
-- 用生成欄位而非重算腳本：pb_cheap_price / current_price 每次寫入時 DB 自動
-- 重算，不需回填、不需掛排程（避開「重算漏掛排程」那類事故）。
--
-- 取 null 時為 true：沒有 P/B 估值的股票本來就進不了榜（排行榜會先檢查
-- pb_status 與 pb_cheap_price），此處回 true 才不會讓語意變成「無估值＝不可靠」。

ALTER TABLE valuations
  ADD COLUMN IF NOT EXISTS pb_reliable BOOLEAN
  GENERATED ALWAYS AS (
    pb_cheap_price IS NULL
    OR current_price IS NULL
    OR current_price <= 0
    OR pb_cheap_price <= current_price * 2
  ) STORED;

-- ---------------------------------------------------------------------------
-- valuations.price_date：current_price 的「來源日期」
-- ---------------------------------------------------------------------------
-- 原本只有 updated_at（腳本執行時間），要回答「這個現價是哪一天的收盤價？」
-- 只能拿執行時間去推——但交易所資料可能是 T-1、可能因休市停留在前一交易日，
-- 執行時間不等於資料日期（見 CLAUDE.md 資料誠信原則第 1 條）。
-- 這個欄位直接存 daily_prices 那一列的 date，不做任何推算。

ALTER TABLE valuations
  ADD COLUMN IF NOT EXISTS price_date DATE;

-- ─────────────────────────────────────────────────────────
-- P/E 折價過深旗標（2026-07-22）
--
-- pe_reliable 只擋「獲利高峰／EPS 長期偏低／業外虛胖」，沒有擋折價過深。
-- 但回測顯示 P/E 也有同樣的毛病——便宜價遠高於現價時，多半不是跌得便宜，
-- 是歷史倍數已經不適用了（公司基本面劇變，早年的高倍數對現在沒有參考價值）。
--
-- 依據（持有 12 個月，逐月中位數的中位，已控制時點集中）：
--     全市場等權（對照）  +5.09%  ← universe.csv 逐月中位數的中位
--     折價 1.0~1.5 倍     +1.88%   （12,334 筆）
--     折價 1.5~2 倍       +2.21%   （ 1,519 筆）
--     折價 2~3 倍         +1.00%   （   511 筆）
--     折價 >3 倍          -5.71%   （   206 筆，跨 57 個月）
--
-- 門檻 3 倍高於 P/B 的 2 倍（見 pb_reliable）：EPS 波動大，2 倍折價還可能是
-- 景氣循環的谷底；淨值是存量、變動慢，P/B 帶一旦失真就是結構性的。
--
-- 為什麼獨立成新欄位，而不併進 pe_reliable：
-- pe_reliable 是既有生成欄位，加條件必須 DROP 後重建，期間排行榜與推薦模型
-- 都查不到它、網站會短暫報錯。純新增零風險，代價只是判斷散在兩個欄位。
-- 前端在 lib/peReliability.isPeUnreliable() 把兩者一起檢查。
ALTER TABLE valuations
  ADD COLUMN IF NOT EXISTS pe_deep_discount BOOLEAN
  GENERATED ALWAYS AS (
    cheap_price IS NOT NULL AND current_price > 0
    AND cheap_price > current_price * 3
  ) STORED;

-- =============================================
-- 除權息還原的官方背書程度（2026-08-03）
-- =============================================
--
-- 這支股票的歷史序列中，有幾次除權息是【沒有交易所官方因子背書】、
-- 只能用 dividends 的現金股利與股票股利自算的。由 calculate_valuation.py
-- 寫入（值出自 price_adjust.unofficial_adjustments()，與 back_adjust 共用
-- 同一份因子建構邏輯，兩邊不會漂移）。
--
-- 語意是「這段還原有沒有官方背書」——查得到答案的事實，
-- 不是「這支股票估值有問題」的推測。自算公式對配息與配股完全正確，
-- 涵蓋不了的只有【現金增資與減資】，而那兩者不會出現在 dividends 表裡，
-- 我們無從得知它是否發生過。所以這個數字讀作【曝險次數】，不是錯誤次數。
--
-- 為什麼會有曝險（2026-08-03 實測）：
--     TWSE 的 TWT49U 可查 10 年區間 → 上市官方因子涵蓋 1,031/1,093 家、回溯 2016 年
--     TPEx 的端點【只給當日】，漏跑永久補不回 → 上櫃僅 83/887 家且只有 2025 年起
-- 亦即上櫃 2016～2024 這九年的除權息全靠自算。
-- 上市的 8,566 筆官方因子事件中有 409 筆（4.8%）在 dividends 查無對應，
-- 那正是自算路徑接不到的那一類；同比例套到上櫃即為其曝險規模。
--
-- 為什麼要標示：未還原的資本事件讓歷史股價偏高 → 歷史倍數偏高 → 目標價虛高，
-- 方向固定是【看起來比實際便宜】，受影響的股票會系統性往便宜排行榜頂端跑
-- （同型現象見 dividends.stock_dividend 的 1436 實例、stocks.delisted_at 的下市股）。
--
-- 盲區：這個欄位只答得出「有沒有官方背書」，答不出「那段期間到底有沒有發生
-- 現金增資或減資」。次數為 0 不代表還原一定正確，只代表沒有這一類曝險；
-- 次數高也不代表一定錯，只代表無從查證。真正要抓「實際發生了未還原事件」
-- 得靠價格斷崖偵測（validate_valuations.py C 段），但那段目前只掃近 30 天，
-- 更早的歷史是週採樣、10% 門檻失去意義，全歷史普查尚未做。
ALTER TABLE valuations
  ADD COLUMN IF NOT EXISTS unofficial_adjustments SMALLINT;
