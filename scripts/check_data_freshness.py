"""
check_data_freshness.py — 資料新鮮度看門狗（每日執行）

## 為什麼需要它（既有防線的兩個洞）

1. 靜默凍結：排程只有 `if: failure()` 會寄信。「工作沒失敗但資料沒往前推」
   （來源回空、被過濾光、寫入 0 筆卻 exit 0）不會有任何警報，網站會把陳舊資料
   當成最新持續呈現。
2. cron 沒響：GitHub 對私有 repo 60 天無 commit 會停用排程，尖峰也可能丟棄
   schedule 事件。整條更新無聲停擺時，`if: failure()` 一封信都不會寄——因為它根本沒跑。

本看門狗以「獨立排程」每日執行，回答一個問題：**我方資料有跟上真實市場嗎？**

## CNY-proof：不靠日曆猜休市

判斷「股價是否落後」不用「距今幾天」這種日曆門檻——那會在農曆年連假整批誤報。
改為拿參考股（2330 台積電）從 FinMind 取得**市場真正的最新交易日**，與我方最新
股價日期比對：只要對得上就是新鮮，無論放幾天連假。這正是 CLAUDE.md 強調的跨來源比對。

## 死人開關（配合 healthchecks.io）

資料確認新鮮時，對 `HEALTHCHECK_URL` 送一個 ping。若某天看門狗根本沒被 GitHub 觸發
（cron 被停用/丟棄），ping 就會停，由 healthchecks.io 從外部寄信通知——補上
「GitHub 自己死掉時，GitHub 的失敗通知也一起死掉」這個盲區。未設定該 secret 則略過。

發現落後時以 exit code 1 結束，觸發 workflow 的失敗 Email。
"""

import os
import sys
import requests
from datetime import date, datetime, timezone, timedelta
from dotenv import load_dotenv
from supabase import create_client

sys.path.insert(0, os.path.dirname(__file__))
from finmind_client import fetch, FinMindError  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

supabase        = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
FINMIND_TOKEN   = os.getenv("FINMIND_TOKEN")
HEALTHCHECK_URL = os.getenv("HEALTHCHECK_URL")

# 參考股：全市場最活躍、幾乎不可能無成交，用來取得「市場真正的最新交易日」
REFERENCE_STOCK = "2330"
# 估值現價更新的容許落後（日曆天）：涵蓋週末 + 一天緩衝
VALUATION_MAX_LAG_DAYS = 4
# Supabase 免費層資料庫上限 500 MB；達 90% 視為緊急（exit 1），80% 僅提醒
FREE_TIER_DB_MB = 500


def latest_date(table: str, col: str) -> str | None:
    """取某表某欄的最大值（小表適用，如 valuations 一股一列）"""
    resp = (supabase.table(table).select(col)
            .order(col, desc=True).limit(1).execute())
    return resp.data[0][col] if resp.data else None


def latest_date_for_stock(table: str, col: str, stock_id: str) -> str | None:
    """
    取單一股票在某表的最新日期。

    大表（daily_prices 數百萬列）直接對 date 排序會逾時——主鍵是
    (stock_id, date)，單以 date 排序用不到索引。加上 stock_id 等值條件後
    命中主鍵、瞬間回覆。以參考股（2330）當探針即足以判斷心跳是否前進。
    """
    resp = (supabase.table(table).select(col)
            .eq("stock_id", stock_id)
            .order(col, desc=True).limit(1).execute())
    return resp.data[0][col] if resp.data else None


def market_latest_trading_day() -> str | None:
    """
    以參考股向 FinMind 取得市場最新交易日。

    FinMind 故障時回傳 None（看門狗不因對照來源暫時不可用就硬性失敗——
    那不是我方資料的問題），呼叫端會退回日曆門檻並印出說明。
    """
    start = (date.today() - timedelta(days=10)).strftime("%Y-%m-%d")
    try:
        rows = fetch("TaiwanStockPrice", REFERENCE_STOCK, start, FINMIND_TOKEN)
    except FinMindError as e:
        print(f"  ⚠️  無法取得市場最新交易日（FinMind）：{e}")
        return None
    dates = [r["date"] for r in rows if r.get("close") and float(r["close"]) > 0]
    return max(dates) if dates else None


def check_db_size() -> list[str]:
    """
    以 pg_database_size 檢查資料庫用量（免 Management API token）。

    需先在 Supabase 執行 schema.sql 末段的 db_size_mb() 函式；尚未部署時
    優雅略過（印出提示），不影響其他檢查。回傳緊急層級的問題清單。
    """
    try:
        resp = supabase.rpc("db_size_mb").execute()
        mb = resp.data[0] if isinstance(resp.data, list) else resp.data
        mb = float(mb)
    except Exception as e:
        print(f"\n資料庫容量：略過（{e}）"
              "\n  提示：在 Supabase 執行 schema.sql 末段的 db_size_mb() 函式即可啟用")
        return []

    pct = mb / FREE_TIER_DB_MB * 100
    print(f"\n資料庫容量：{mb:.0f} MB / {FREE_TIER_DB_MB} MB（{pct:.0f}%）")
    # 免費層超過 500MB 會被鎖成唯讀（所有排程停擺），故達 96% 即寄緊急信、
    # 留約 20MB（數月成長）緩衝反應。85%~96% 只在日誌提醒，避免長期高水位天天寄信。
    if pct >= 96:
        return [f"資料庫已用 {mb:.0f} MB（{pct:.0f}%），逼近免費層 {FREE_TIER_DB_MB} MB 上限，"
                "超過會被鎖唯讀。處理方式：執行 scripts/thin_daily_prices.py 週採樣瘦身。"
                "切勿 VACUUM FULL——它需要約等於表大小（約 252MB）的暫存空間，"
                "在容量吃緊時必定失敗，還會把僅剩的空間吃光。"]
    if pct >= 85:
        # 2026-07-21 起此數字可能失真：週採樣瘦身刪了 368 萬列，但 Postgres 的
        # DELETE 不把空間歸還磁碟，pg_database_size 因此停在高檔。
        # 真正該看的是「還在不在增長」——不增長就代表新資料正在重用 free space。
        print(f"  ⚠️  已達 {pct:.0f}%（達 96% 會寄信示警）")
        print("      註：瘦身後此數字不會下降，高水位未必等於真實壓力；"
              "請看它是否仍在【增長】——停止增長即代表正在重用已釋出的空間。")
    return []


def ping_healthcheck():
    """資料新鮮時對外部死人開關報平安；未設定或失敗都不影響主結果"""
    if not HEALTHCHECK_URL:
        return
    try:
        requests.get(HEALTHCHECK_URL, timeout=10)
        print("  ✓ 已 ping healthchecks.io（死人開關）")
    except Exception as e:
        print(f"  ⚠️  healthchecks ping 失敗（不影響資料判斷）：{e}")


def main():
    print(f"=== 資料新鮮度檢查：{date.today()} ===\n")
    problems = []

    # 1. 股價：以參考股 2330 為探針，與市場真正的最新交易日比對（CNY-proof）
    #    2330 幾乎每個交易日都有成交，且每日排程採全市場「全成功或全失敗」，
    #    故 2330 有跟上 ≈ 整批心跳有前進。走主鍵查詢，大表也不會逾時。
    our_price_date = latest_date_for_stock("daily_prices", "date", REFERENCE_STOCK)
    market_date    = market_latest_trading_day()
    print(f"我方最新股價日期：{our_price_date}（{REFERENCE_STOCK}）")
    print(f"市場最新交易日　：{market_date or '（FinMind 不可用，改用日曆門檻）'}")

    if market_date:
        if our_price_date is None or our_price_date < market_date:
            problems.append(
                f"股價落後市場：我方 {our_price_date}，市場已到 {market_date}")
    else:
        # FinMind 不可用時的後備：純日曆門檻（連假期間可能誤報，僅為保底）
        if our_price_date:
            lag = (date.today() - date.fromisoformat(our_price_date)).days
            if lag > VALUATION_MAX_LAG_DAYS + 1:
                problems.append(f"股價已 {lag} 天未更新（後備日曆門檻）")

    # 2. 估值現價更新時間（updated_at）：每日排程若靜默停擺，這裡會露餡
    updated_at = latest_date("valuations", "updated_at")
    print(f"\n估值最後更新　　：{updated_at}")
    if updated_at:
        ts  = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
        lag = (datetime.now(timezone.utc) - ts).days
        if lag > VALUATION_MAX_LAG_DAYS:
            problems.append(f"估值 {lag} 天未更新（updated_at={updated_at}）")
    else:
        problems.append("valuations 表無任何 updated_at")

    # 3. 慢速表：僅供參考，不觸發失敗（財報/月營收本就數週至數月才更新一次，
    #    硬性門檻會在淡季誤報）。列出來讓人一眼看出是否明顯過期。
    #    同樣以 2330 為探針走主鍵查詢，避免大表全域排序逾時。
    print("\n慢速表最新資料期別（參考股 2330，僅供參考）：")
    for table, col in (("eps_quarterly", "quarter_end_date"),
                       ("balance_sheet_quarterly", "quarter_end_date"),
                       ("cash_flows_quarterly", "quarter_end_date"),
                       ("monthly_revenue", "year_month")):
        print(f"  {table:<26}: {latest_date_for_stock(table, col, REFERENCE_STOCK)}")

    # 4. 資料庫容量（防休眠已由「本工作每日查詢 Supabase」天然達成，無需額外程式）
    problems += check_db_size()

    # 結果
    print()
    if problems:
        print("❌ 資料新鮮度異常：")
        for p in problems:
            print(f"  - {p}")
        print("\n以 exit 1 結束並寄送通知。（不 ping 死人開關，讓外部也一併察覺。）")
        sys.exit(1)

    print("✅ 資料新鮮，已跟上市場。")
    ping_healthcheck()


if __name__ == "__main__":
    main()
