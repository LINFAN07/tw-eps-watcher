-- =============================================
-- 台股估值查詢網站 — 資料庫 Schema
-- =============================================

-- 股票名冊
CREATE TABLE IF NOT EXISTS stocks (
  stock_id    VARCHAR(10)  PRIMARY KEY,           -- 股票代碼，例如 "2330"
  name        VARCHAR(100) NOT NULL,              -- 公司名稱，例如 "台積電"
  market      VARCHAR(10)  NOT NULL,              -- "TWSE"（上市）或 "TPEx"（上櫃）
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
