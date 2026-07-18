"""
price_adjust.py — 除權息後向還原（共用純函式）

除權息還原改採「即時計算、不儲存」：不把還原價寫進資料庫（免費層 500MB 容量
容不下多一份價格序列與更新膨脹），而是在算估值與畫河流圖時，用手上的 dividends
即時還原。此模組提供後端與（對應的 TypeScript 版）前端共用的還原邏輯。

## 後向還原

- 每個除息日 d 的還原因子 factor_d = 1 − 現金股利 / 除息前一交易日收盤價。
- adjusted(t) = close(t) × ∏ factor_d（對所有 ex_date d > t）。
- 錨定今日：最新一日沒有更晚的除息日，factor 連乘為 1，故 adjusted 最新一日
  == close 最新一日——現價與現在的本益比不變，只有歷史被還原下移。

僅供 P/E、P/B、P/S、P/FCF 的「歷史倍數分布」使用；殖利率維持原始價
（殖利率本質是實際價 vs 股利，還原會虛增歷史殖利率）。
"""

import bisect


def back_adjust(dates: list[str], closes: list[float],
                ex_list: list[tuple[str, float]]) -> list[float]:
    """
    後向還原。回傳與 dates 對齊的還原價陣列（純函式，可單元測試）。

    dates 須為升冪的 ISO 日期字串。ex_list 為 (除息日, 現金股利)。
    只採計「除息日 ≤ 最後交易日」且能取得除息前收盤價者，確保最新一日 factor=1。
    """
    if not dates:
        return []
    last_date = dates[-1]

    # 每個除息日的還原因子，用除息前一交易日收盤價當基準
    factors: list[tuple[str, float]] = []
    for ex_date, cash in ex_list:
        if cash is None or cash <= 0 or ex_date > last_date:
            continue
        i = bisect.bisect_left(dates, ex_date)   # 第一個 >= ex_date 的位置
        if i == 0:
            continue                             # 除息日早於所有股價，無基準可算
        prev_close = closes[i - 1]               # 除息前最後一個交易日收盤價
        f = 1.0 - cash / prev_close
        if f <= 0 or f > 1:
            continue                             # 股利 ≥ 前收（資料異常），跳過該筆
        factors.append((ex_date, f))

    factors.sort()                               # 依除息日升冪
    adjusted = [0.0] * len(dates)
    cum = 1.0
    j = len(factors) - 1                         # 由最晚的除息日往回套用
    for k in range(len(dates) - 1, -1, -1):
        while j >= 0 and factors[j][0] > dates[k]:
            cum *= factors[j][1]
            j -= 1
        adjusted[k] = closes[k] * cum
    return adjusted
