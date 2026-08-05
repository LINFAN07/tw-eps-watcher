"""
ex_factors.py — 非自算路徑的還原因子（整表快取）

兩個來源，優先序由高到低：
  1. `ex_right_factors`      交易所公告的參考價 ÷ 前收盤價
  2. `unadjusted_capital_events` 減資／分割推算的 1 ÷ 股數比（僅 adjustable 者）
兩者都優先於 `price_adjust` 的股利自算公式——自算涵蓋不了現金增資與減資。

## 為什麼要快取

`ex_right_factors` 的用法是「逐股取該股的所有除權息因子」，而兩支計算腳本
的主迴圈都是逐股循序跑。若每支股票查一次資料庫，就是 2,500 次往返 × 2 支
腳本 ＝ 5,000 次，每次回傳往往只有 0～10 列——付的全是往返延遲，實測會讓
每支腳本多花數分鐘，而這兩支在 monthly／quarterly／dividends 四個 workflow
都會跑。

整張表約 10,700 列（見 schema.sql 的 ex_right_factors），一次讀進記憶體
只要 11 次分頁查詢。首次呼叫時載入，之後查表。

## 因子的定義

factor = 交易所公告參考價 ÷ 交易所公告除權息前收盤價

只存來源提供的兩個原始價格、不存 factor（衍生值不入庫，這樣每個欄位都
答得出「這是誰給的、哪一天的」），相除在這裡做。

## 推算因子（2026-08-05 補上）

減資、面額分割、股份換發不走除權除息公告，交易所因子與股利自算都接不到，
歷史股價因此停在舊股數基準、估值帶整體位移。`audit_capital_events.py` 用
三個條件交叉確認這類事件後，其還原因子可由股數變動直接推得：

    factor = 1 ÷ share_ratio

方向驗算：減資 44% → 股數 ×0.56 → factor 1.79 → 歷史價 21 × 1.79 = 37.6，
與事件後的 38 接得上（實例 1472 三洋實業 2017-11-03）。

**一律用 share_ratio，不可用 price_ratio。** 後者是觀測到的價格比，
含當週的真實市場波動，拿它當因子會把真實波動一起消掉——那是竄改市場資料。
兩者的差距（product 偏離 1 的部分）本來就該留在序列裡。

只採計 `adjustable`（product 0.9~1.1）者：偏離越大，「這個跳空確實由該次
股本變動造成」的信心越低，補上去反而引入新錯誤。其餘維持排除出排行榜。
門檻寫在 schema.sql 的生成欄位，前後端共讀，不在程式裡各判一次。
"""

_cache: dict[str, dict[str, float]] | None = None


def _paged(supabase, table: str, cols: str, *order_cols: str):
    """分頁讀取。務必帶 order——無排序的多次查詢，Postgres 不保證跨頁順序一致。"""
    offset = 0
    while True:
        q = supabase.table(table).select(cols)
        for c in order_cols:
            q = q.order(c)
        rows = q.range(offset, offset + 999).execute().data
        yield from rows
        if len(rows) < 1000:
            return
        offset += 1000


def load_all(supabase) -> dict[str, dict[str, float]]:
    """{股票代號: {除權息日: 還原因子}}，官方值優先於推算值。"""
    out: dict[str, dict[str, float]] = {}
    for r in _paged(supabase, "ex_right_factors",
                    "stock_id,ex_date,prev_close,ref_price", "stock_id", "ex_date"):
        prev = float(r["prev_close"] or 0)
        if prev > 0 and r["ref_price"] is not None:
            out.setdefault(r["stock_id"], {})[r["ex_date"]] = float(r["ref_price"]) / prev

    # 減資／分割的推算因子（見模組說明）。
    # 這張表只有百餘列，整批載入後在程式端篩 adjustable，不另外組查詢條件。
    added = 0
    for r in _paged(supabase, "unadjusted_capital_events",
                    "stock_id,event_date,share_ratio,adjustable", "stock_id", "event_date"):
        ratio = float(r["share_ratio"] or 0)
        if not r["adjustable"] or ratio <= 0:
            continue
        # 不覆寫既有鍵：同一日若已有交易所公告值，以公告值為準——那是來源直接
        # 給的，推算值是我們算的（前端 exRights.ts 的 `!(date in official)` 同語意）
        factors = out.setdefault(r["stock_id"], {})
        if r["event_date"] not in factors:
            factors[r["event_date"]] = 1 / ratio
            added += 1
    if added:
        print(f"  [還原因子] 併入減資／分割推算 {added} 筆")
    return out


def for_stock(supabase, stock_id: str) -> dict[str, float]:
    """
    某支股票的 {除權息日: 還原因子}。首次呼叫載入整表，之後查記憶體。

    優先於股利自算——自算公式涵蓋不了現金增資與減資（見 price_adjust.py）。
    上櫃／興櫃只有當日資料、無歷史，查無官方值時呼叫端會自動回退自算。
    含減資／分割的推算因子（見模組說明），故未必都是交易所公告值。
    """
    global _cache
    if _cache is None:
        _cache = load_all(supabase)
        print(f"  [還原因子] 載入 {len(_cache)} 支股票、"
              f"{sum(len(v) for v in _cache.values())} 筆")
    return _cache.get(stock_id, {})
