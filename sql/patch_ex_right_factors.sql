-- 除權息還原因子表（2026-07-22）
--
-- 原本的還原因子由「現金股利 ＋ 配股」自算：
--   factor = (前收 − 現金股利) ÷ (前收 × (1 + 配股率))
-- 該公式對「只有配息配股」完全正確（實測 1808／2540／3056 與交易所公告
-- 參考價分毫不差），但涵蓋不了現金增資與減資。
--
-- audit_external.py 首次量化這個缺口：近 20 天 217 筆除權息中 6 筆對不上。
--   8112 至上 2026-07-06  現金股利 3.80 ＋ 現金增資（認購價 66）→ 差 1.57 元
--   3028 零壹 2026-07-17  配息配股皆為 0、只辦現金增資
--                         → dividends 表根本沒這筆，等於完全沒還原
--
-- 解法：不再自己推公式，直接存交易所公告的兩個價格，相除即為還原因子。
-- 涵蓋現金股利、配股、現金增資、減資，以及未來任何新型態的分派。
-- 只存來源提供的原始值，factor 由程式即時計算（衍生值不入庫）。
--
-- 涵蓋範圍的落差：
--   上市 TWT49U              2016-01 起 10,694 筆，一次請求可全數回補
--   上櫃 tpex_exright_daily  只有當日，須每日累積；歷史仍走自算路徑

CREATE TABLE IF NOT EXISTS ex_right_factors (
    stock_id   TEXT    NOT NULL,
    ex_date    DATE    NOT NULL,
    prev_close NUMERIC NOT NULL,   -- 交易所公告「除權息前收盤價」
    ref_price  NUMERIC NOT NULL,   -- 交易所公告「除權息參考價」
    source     TEXT    NOT NULL,   -- 'TWSE' / 'TPEX'，涵蓋期間不同，查問題時要分得出來
    PRIMARY KEY (stock_id, ex_date)
);

CREATE INDEX IF NOT EXISTS idx_erf_stock ON ex_right_factors(stock_id, ex_date);
