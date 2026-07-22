"""
ex_factors.py — 交易所公告的除權息還原因子（整表快取）

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
"""

_cache: dict[str, dict[str, float]] | None = None


def load_all(supabase) -> dict[str, dict[str, float]]:
    """{股票代號: {除權息日: 還原因子}}。分頁且排序——無排序的多次查詢，
    Postgres 不保證跨頁順序一致，會重複或遺漏。"""
    out: dict[str, dict[str, float]] = {}
    offset = 0
    while True:
        rows = (supabase.table("ex_right_factors")
                .select("stock_id,ex_date,prev_close,ref_price")
                .order("stock_id").order("ex_date")
                .range(offset, offset + 999).execute().data)
        for r in rows:
            prev = float(r["prev_close"] or 0)
            if prev > 0 and r["ref_price"] is not None:
                out.setdefault(r["stock_id"], {})[r["ex_date"]] = float(r["ref_price"]) / prev
        if len(rows) < 1000:
            return out
        offset += 1000


def for_stock(supabase, stock_id: str) -> dict[str, float]:
    """
    某支股票的 {除權息日: 還原因子}。首次呼叫載入整表，之後查記憶體。

    優先於股利自算——自算公式涵蓋不了現金增資與減資（見 price_adjust.py）。
    上櫃／興櫃只有當日資料、無歷史，查無官方值時呼叫端會自動回退自算。
    """
    global _cache
    if _cache is None:
        _cache = load_all(supabase)
        print(f"  [除權息因子] 載入 {len(_cache)} 支股票、"
              f"{sum(len(v) for v in _cache.values())} 筆")
    return _cache.get(stock_id, {})
