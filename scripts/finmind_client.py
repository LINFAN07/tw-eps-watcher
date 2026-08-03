"""
FinMind API 共用客戶端。

## 為什麼要有這個模組

原本 6 個 download_*.py 各自複製同一份 `finmind_get()`，而那份實作有個共同缺陷：
連續重試失敗後 **回傳空清單**，與「該股票確實沒有這項資料」完全無法區分。
呼叫端因此把故障當成「無資料」，繼續跑完並回報成功。

2026-07-14 的事故即為此類：`daily_price_update.py` 的 TPEx 連線中斷後回傳空 dict，
整個上櫃市場（約 900 支）當日沒有寫入，工作卻回報「完成！」，
缺口三天後才被跨來源比對發現。

## 契約

- 回傳空清單 = 該股票確實沒有這項資料（API 回應 status 200 但 data 為空）
- 拋出 `FinMindError` = 抓取失敗，呼叫端必須讓工作失敗

呼叫端請搭配 `FailureTracker`：單支失敗不中斷整批（4 小時的下載不該因一次逾時全毀），
但結束時若有任何失敗，必須以 exit code 1 結束以觸發通知。

參見 CLAUDE.md「資料誠信原則」。
"""

import sys
import time
import requests

FINMIND_API = "https://api.finmindtrade.com/api/v4/data"

# TaiwanStockInfo 的市場別欄位叫 `type`，值為 twse / tpex / emerging。
# 早期程式碼取的 `market_category` 在這個資料集裡並不存在，
# fallback 讓 stocks.market 全表寫成「未知」而無人察覺（2026-08-03 發現）。
# 對照到 stocks.market 的正式值；此處只供「新股當日」使用，
# 隔日 daily_price_update.update_market() 會以交易所清單為準覆寫。
MARKET_BY_TYPE = {"twse": "TWSE", "tpex": "TPEx", "emerging": "Emerging"}


def roster_market(item: dict) -> str:
    """從 TaiwanStockInfo 的一列取出市場別；無法辨識時回「未知」而非猜測"""
    return MARKET_BY_TYPE.get(str(item.get("type", "")).strip().lower(), "未知")


class FinMindError(Exception):
    """FinMind 抓取失敗（與「無資料」不同，呼叫端必須讓工作失敗）"""


def fetch(dataset: str, stock_id: str | None, start_date: str | None,
          token: str, retries: int = 3, backoff: int = 10) -> list:
    """
    取得 FinMind 資料列。

    回傳空清單代表該股票確實沒有這項資料；
    連續 `retries` 次失敗則拋 FinMindError，絕不以空清單掩蓋故障。
    """
    params: dict = {"dataset": dataset, "token": token}
    if stock_id:
        params["data_id"] = stock_id
    if start_date:
        params["start_date"] = start_date

    last_error = None
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(FINMIND_API, params=params, timeout=30).json()
            if resp.get("status") == 200:
                return resp.get("data", [])
            last_error = f"API 回應 status={resp.get('status')}：{resp.get('msg', '未知')}"
        except Exception as e:
            last_error = f"請求例外：{e}"
        print(f"  ⚠️  {stock_id or dataset} 第 {attempt}/{retries} 次失敗：{last_error}")
        if attempt < retries:
            time.sleep(backoff)

    raise FinMindError(f"{dataset}/{stock_id} 連續 {retries} 次失敗：{last_error}")


class FailureTracker:
    """
    記錄整批作業中的個別失敗。

    單支股票失敗不中斷整批（否則 4 小時的下載會因一次逾時全毀），
    但收尾時必須誠實回報——有失敗就以 exit code 1 結束，讓排程寄出通知。
    """

    def __init__(self, label: str = "作業"):
        self.label = label
        self.failures: list[tuple[str, str]] = []

    def record(self, stock_id: str, error: Exception):
        self.failures.append((stock_id, str(error)))

    def finish(self):
        """有失敗就印出摘要並以 exit 1 結束；無失敗則正常返回"""
        if not self.failures:
            return
        print(f"\n❌ {self.label}有 {len(self.failures)} 支股票抓取失敗，資料不完整：")
        for sid, err in self.failures[:10]:
            print(f"  {sid}: {err[:100]}")
        if len(self.failures) > 10:
            print(f"  …另有 {len(self.failures) - 10} 支")
        print("\n以失敗結束，以免缺漏的資料被當成『該股票沒有資料』而無人知悉。")
        sys.exit(1)
