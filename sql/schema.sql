-- =============================================
-- ⚠️ 已棄用（2026-07-22 標記）— 請勿執行此檔
--
-- 實際使用的完整 schema 是【專案根目錄】的 schema.sql（含歷次 ALTER TABLE 擴充）。
-- 本檔停留在 2026-06-27 的初版，缺少之後新增的所有欄位與資料表
-- （替代估值模型、品質指標、下市偵測、除權息還原因子…）。
--
-- 兩個檔案同名、只差一層目錄，拿錯會建出缺欄位的資料庫，
-- 而症狀要等到某支腳本寫入時才會冒出來。保留此檔僅為歷史紀錄。
--
-- 本目錄其餘 patch_*.sql 仍然有效，那些是增量變更腳本。
-- =============================================

-- =============================================
-- 台股估值查詢網站 — 資料庫 Schema（初版，2026-06-27）
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
  warning          TEXT,                         -- 非空時表示 TTM EPS 含疑似一次性收益，估值已調整
  updated_at       TIMESTAMPTZ DEFAULT NOW()
);

-- 索引：加速股票名稱搜尋與歷史資料查詢
CREATE INDEX IF NOT EXISTS idx_stocks_name       ON stocks(name);
CREATE INDEX IF NOT EXISTS idx_eps_stock_date    ON eps_quarterly(stock_id, quarter_end_date DESC);
CREATE INDEX IF NOT EXISTS idx_prices_stock_date ON daily_prices(stock_id, date DESC);
