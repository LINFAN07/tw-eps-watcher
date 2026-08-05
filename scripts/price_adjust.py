"""
price_adjust.py — 除權息後向還原（共用純函式）

除權息還原改採「即時計算、不儲存」：不把還原價寫進資料庫（免費層 500MB 容量
容不下多一份價格序列與更新膨脹），而是在算估值與畫河流圖時，用手上的 dividends
即時還原。此模組提供後端與（對應的 TypeScript 版）前端共用的還原邏輯。

## 後向還原

- 每個除權息日 d 的還原因子，即當日的「除權息參考價 ÷ 除權息前收盤價」：

      factor_d = (前收盤 − 現金股利) ÷ (前收盤 × (1 + 股票股利 ÷ 10))

  分子處理除息、分母處理除權（配股率 = 股票股利 ÷ 10，面額 10 元）。
- adjusted(t) = close(t) × ∏ factor_d（對所有 ex_date d > t）。

**2026-07-22 修正：配股（除權）先前完全沒有還原。**
實例 1436：2025-07-25 原始單日跌 32.9%（台股漲跌幅上限 10%，超過必為除權息），
只用現金股利還原後【仍有 −26.7% 跳空】，那是配股 3.0143 元造成的。
驗證：(116 − 9.7965) ÷ (1 + 3.0143/10) = 81.60，與該日走勢相符。
影響 1,790 支（74%）——近 10 年配過股 1,310 支、減資過 480 支。

**方向**（初版註解曾寫反，2026-07-22 實測更正）：
後向還原是把歷史價格換算成「今天的股數基準」。配股使股數變多，
故歷史價還需再除以 (1 + 配股率)，還原後的歷史價**更低**。
於是歷史倍數更低、目標價更低——**未還原等於高估目標價，讓股票看起來比實際便宜**。
實測：1436 三價下修 25～28%、1519 下修 17.4%。
（配股若發生在序列最早期則影響甚微，如 2317 唯一一次配股在 2016-09-02，
目標價幾乎不變——那段樣本只佔全序列不到 2%。）

**已知限制**：本檔的【自算公式】涵蓋不了現金增資與減資——前者股東須自行認購、
對每股價值的影響取決於認購價，後者需區分現金減資與彌補虧損減資，公式不同。
但這兩類事件多半能從 `official` 參數補進來，兩個來源見 `ex_factors.py`：
交易所公告因子（涵蓋現金增資與走除權程序的減資），以及 2026-08-05 補上的
減資／分割推算因子（`audit_capital_events.py` 確認事件後取 1 ÷ 股數比）。
仍補不到的是「不走除權公告、且股本變動與價格跳動對不上」的那批
（`unadjusted_capital_events.adjustable = false`，52 支），它們由前端排除出
排行榜而非還原——判不出該用多少倍率時，硬補會引入新錯誤。
- 錨定今日：最新一日沒有更晚的除息日，factor 連乘為 1，故 adjusted 最新一日
  == close 最新一日——現價與現在的本益比不變，只有歷史被還原下移。

僅供 P/E、P/B、P/S、P/FCF 的「歷史倍數分布」使用；殖利率維持原始價
（殖利率本質是實際價 vs 股利，還原會虛增歷史殖利率）。
"""

import bisect


def back_adjust(dates: list[str], closes: list[float],
                ex_list: list[tuple[str, float, float]],
                official: dict[str, float] | None = None) -> list[float]:
    """
    後向還原。回傳與 dates 對齊的還原價陣列（純函式，可單元測試）。

    dates 須為升冪的 ISO 日期字串。
    ex_list 為 (除權息日, 現金股利, 股票股利)——股票股利不可省略，
    只還原現金股利會在配股日留下數十個百分點的假跌幅（見模組說明）。

    official 為 {除權息日: 還原因子}，來自交易所公告的「參考價 ÷ 前收盤價」。
    有官方值就用官方值，它涵蓋現金增資與減資——自算公式涵蓋不了那兩者。
    兩者的日期取聯集：只辦現金增資的除權息（配息配股皆為 0，如 3028 零壹
    2026-07-17）根本不會出現在 ex_list，只存在於官方資料。

    只採計「除權息日 ≤ 最後交易日」且能取得前一交易日收盤價者，
    確保最新一日 factor=1（現價不被改動）。
    """
    return _apply(dates, closes, _build_factors(dates, closes, ex_list, official))


def _build_factors(dates: list[str], closes: list[float],
                   ex_list: list[tuple[str, float, float]],
                   official: dict[str, float] | None
                   ) -> list[tuple[str, float, str]]:
    """
    產生升冪的 (除權息日, 還原因子, 來源) 清單，來源為 "official" 或 "computed"。

    抽出來共用而非讓 unofficial_adjustments() 自己判一次：
    兩份平行的判準必然隨時間漂移，屆時「旗標說自算、實際用官方」這種
    對不上的錯誤沒有任何機制會發現（同型教訓見 CLAUDE.md 的
    audit_external.check_ttm_window 必須與計算端同回看期數）。
    """
    if not dates:
        return []
    last_date = dates[-1]
    official = official or {}

    events = {d: (c or 0.0, s or 0.0) for d, c, s in ex_list}
    factors: list[tuple[str, float, str]] = []
    for ex_date in sorted(set(events) | set(official)):
        if ex_date > last_date:
            continue
        i = bisect.bisect_left(dates, ex_date)   # 第一個 >= ex_date 的位置
        if i == 0:
            continue                             # 除權息日早於所有股價，無基準可算

        f, source = official.get(ex_date), "official"
        # 官方因子容許 >1：減資會使參考價高於前收，那是真實情況不是異常。
        # 上限取 20：彌補虧損型減資 95% 的參考價約為前收的 20 倍，台灣不罕見；
        # 先前設 5 會把減資 80% 以上的案例當成異常丟掉。
        # 超界時【回退自算】而非整筆跳過——跳過等於那天完全不還原，
        # 會在還原序列留下一個假跳空，比自算更差。
        if f is not None and not 0 < f <= 20:
            f = None
        if f is None:
            source = "computed"
            cash, stock = events[ex_date]
            if cash <= 0 and stock <= 0:
                continue
            # 序列中除權息日前的最後一筆收盤價。注意這未必是「前一交易日」——
            # 週採樣瘦身後三個月以前只剩週頻，實測會取到 6～7 天前的價格。
            # 誤差 <1%（有配股時分母由配股率主導，對 prev_close 不敏感），詳見 TODO 1f。
            prev_close = closes[i - 1]
            # 除權息參考價 ÷ 前收：分子除息、分母除權（配股率 = 股票股利 ÷ 10）
            f = (prev_close - cash) / (prev_close * (1 + stock / 10))
            if f <= 0 or f > 1:
                continue                         # 股利 ≥ 前收（資料異常），跳過該筆
        factors.append((ex_date, f, source))
    return factors                               # sorted() 迭代產生，天然升冪


def _apply(dates: list[str], closes: list[float],
           factors: list[tuple[str, float, str]]) -> list[float]:
    """把還原因子由最晚的除息日往回連乘，套回價格序列"""
    adjusted = [0.0] * len(dates)
    cum = 1.0
    j = len(factors) - 1
    for k in range(len(dates) - 1, -1, -1):
        while j >= 0 and factors[j][0] > dates[k]:
            cum *= factors[j][1]
            j -= 1
        adjusted[k] = closes[k] * cum
    return adjusted


def unofficial_adjustments(dates: list[str], closes: list[float],
                           ex_list: list[tuple[str, float, float]],
                           official: dict[str, float] | None = None) -> int:
    """
    這支股票的歷史序列中，有幾次除權息是【沒有交易所官方因子背書】的。

    語意是「這段還原有沒有官方背書」——一個查得到答案的事實，
    不是「這支股票的估值有問題」那種推測。差別很重要：
    自算公式對配息與配股完全正確，只有【現金增資與減資】涵蓋不了，
    而那兩者不會出現在 dividends 表裡，我們無從得知它是否發生過。
    所以這個數字讀作「曝險次數」，不是「錯誤次數」。

    為什麼有曝險：TWSE 的 TWT49U 可查 10 年歷史，TPEx 的端點【只給當日】，
    漏跑就永久補不回。實測（2026-08-03）官方因子涵蓋率
    上市 1,031/1,093 家、回溯 2016 年；上櫃僅 83/887 家且只有 2025 年起 ——
    上櫃 2016～2024 這九年的除權息全靠自算。

    未還原的資本事件會讓歷史股價偏高 → 歷史倍數偏高 → 目標價虛高，
    方向固定是【看起來比實際便宜】（見模組開頭 1436 的實例），
    所以受影響的股票會系統性地往便宜排行榜頂端跑。
    """
    return sum(1 for _, _, source in _build_factors(dates, closes, ex_list, official)
               if source == "computed")
