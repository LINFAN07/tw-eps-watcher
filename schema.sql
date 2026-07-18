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

-- 現金股利紀錄（除息日 + 每股現金股利）
CREATE TABLE IF NOT EXISTS dividends (
  stock_id      VARCHAR(10)    NOT NULL REFERENCES stocks(stock_id) ON DELETE CASCADE,
  ex_date       DATE           NOT NULL,            -- 除息基準日
  cash_dividend DECIMAL(10, 4) NOT NULL DEFAULT 0,  -- 每股現金股利（元）
  PRIMARY KEY (stock_id, ex_date)
);

-- 索引：加速股票名稱搜尋與歷史資料查詢
CREATE INDEX IF NOT EXISTS idx_stocks_name       ON stocks(name);
CREATE INDEX IF NOT EXISTS idx_eps_stock_date    ON eps_quarterly(stock_id, quarter_end_date DESC);
CREATE INDEX IF NOT EXISTS idx_prices_stock_date ON daily_prices(stock_id, date DESC);

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
CREATE INDEX IF NOT EXISTS idx_bsq_stock_date ON balance_sheet_quarterly(stock_id, quarter_end_date DESC);

-- 月營收（供 P/S 估值用；revenue 單位：千元）
CREATE TABLE IF NOT EXISTS monthly_revenue (
  stock_id   VARCHAR(10) NOT NULL REFERENCES stocks(stock_id) ON DELETE CASCADE,
  year_month DATE        NOT NULL,  -- 該月第一天，例如 2024-01-01
  revenue    BIGINT      NOT NULL,  -- 月營收（千元）
  PRIMARY KEY (stock_id, year_month)
);
CREATE INDEX IF NOT EXISTS idx_rev_stock_month ON monthly_revenue(stock_id, year_month DESC);

-- 季度現金流量（供 P/FCF 估值用；單位：千元）
CREATE TABLE IF NOT EXISTS cash_flows_quarterly (
  stock_id         VARCHAR(10)    NOT NULL REFERENCES stocks(stock_id) ON DELETE CASCADE,
  quarter_end_date DATE           NOT NULL,
  operating_cf     DECIMAL(20, 2),  -- 營業活動現金流量（千元）
  capex            DECIMAL(20, 2),  -- 資本支出（千元，通常為負值）
  PRIMARY KEY (stock_id, quarter_end_date)
);
CREATE INDEX IF NOT EXISTS idx_cf_stock_date ON cash_flows_quarterly(stock_id, quarter_end_date DESC);

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
CREATE INDEX IF NOT EXISTS idx_is_stock_date ON income_statement_quarterly(stock_id, quarter_end_date DESC);

-- valuations 表新增業外收支警告欄位
ALTER TABLE valuations
  ADD COLUMN IF NOT EXISTS nonop_warning TEXT;

-- 品質指標擴充
ALTER TABLE valuations
  ADD COLUMN IF NOT EXISTS operating_margin DECIMAL(6, 2),  -- TTM 營業利益率（%）
  ADD COLUMN IF NOT EXISTS debt_ratio       DECIMAL(6, 2);  -- 最新負債比（TotalLiabilities / TotalAssets × 100）

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
