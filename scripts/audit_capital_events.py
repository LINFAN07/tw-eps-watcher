"""
未還原資本事件稽核（全歷史普查）

減資、面額分割、股份換發會讓股價一夜跳動數倍，但**不走除權除息公告**，
兩條還原路徑都接不到：交易所的 TWT49U／tpex_exright_daily 只收除權除息，
dividends 的自算公式也只涵蓋配息與配股。

後果有固定方向：歷史股價停在事件前的舊股數基準，估值帶整體位移。
減資使目標價偏低（誤判「昂貴」），分割／增資使目標價偏高（誤判「便宜」、
衝上排行榜）。實例 1472 三洋實業 2017-11-03 單週 +81.2%——台股漲跌幅上限
10%，一週最多 +61%，這個幅度不可能是市場波動，而該區間的 dividends 與
官方因子都是 0 筆。

## 為什麼不能只用價格斷崖

`validate_valuations.py` C 段有同型檢查，但只掃近 30 天，並自陳
「歷史存量需另行普查」——2016~2025 的股價已瘦身成週採樣（實測相鄰點
固定間隔 7 天），漲跌幅上限 10% 的門檻在週區間失去意義（理論上限變成
1.105^5 = 1.65），放寬門檻又會漏掉中等規模的減資。

本腳本改用三個條件交叉，缺一不可。這個判準是三次修正的結果，
前兩版都被抽驗推翻，過程寫在下面以免重蹈：

  A. 股本季變動超過門檻 → 定位「哪一季發生了資本事件」
     只用 A：727 筆。錯在沒排除 IPO 前後的股本暴增（峰源-KY +30305%），
     那段根本不在價格序列裡，帶內基準仍一致，對估值無害。故加上
     「事件必須切在價格序列中間」（PAD）。

  B. 同期還原後價格留下跳空 → 確認「這是價格會跳的那一類，且我們沒還原掉」
     A+B：249 筆。仍錯——週採樣下「一週 ±25%」在小型股太常見。
     4117 普生 2020 Q2 從 12.95 漲到 179.50（疫情生技行情），
     碰巧同季股本 +25%，就被判成資本事件。

  C. 價格比 × 股數比 ≈ 1 → 資本事件的**定義性特徵**
     減資 44% → 股數 ×0.56 → 價格必 ×1.79，兩者互為倒數。
     市場波動不滿足這個關係：實測真事件乘積 0.76~1.13，普生是 2.86。
     A+B+C：121 筆，抽驗 4 檔全部確認。

## 盲區（新增稽核規則先問「這條規則看不到什麼」）

1. 股本資料最早只到 2016-09（balance_sheet_quarterly），更早的事件查不到，
   而價格序列從 2016-07 起——前兩個月是盲區。
2. **最近一季的事件抓不到**：股本要等財報公布，天生落後一季。
   實例：7575、7689 在 2026-07 的疑似事件，對應季別 2026-09-30 的財報尚未出，
   本腳本完全看不到，是 `validate_valuations.py` C 段（掃近 30 天的價格斷崖）
   報出來的。兩者互補而非重疊——C 段即時但只看得到近 30 天，
   本腳本看得到全歷史但落後一季。**不可用其中一支取代另一支。**
3. 季度粒度：同一季內先減後增會互相抵銷而測不到。
4. 幅度小於門檻的資本事件測不到（門檻沿用 patch_capital_change_warning.py，
   兩支腳本對同一現象必須給同一答案）。
5. 不改變股數的價格重整測不到（C 條件不成立）。
6. `event_date` 是**我們觀測到跳空的交易日**，不是公司公告的除權基準日——
   週採樣下兩者可能差幾天。要精確日期須另查公開資訊觀測站。

用法：
  python scripts/audit_capital_events.py              # 寫入
  python scripts/audit_capital_events.py --dry-run    # 僅列出
"""

import os
import sys
import argparse
from collections import defaultdict
from datetime import date
from dotenv import load_dotenv
from supabase import create_client

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

from price_adjust import back_adjust
import ex_factors

supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

# 門檻沿用 patch_capital_change_warning.py：兩支腳本都在偵測股本變動，
# 用不同門檻會讓同一支股票在兩處得到不同判定（同 audit_external 與計算端
# 必須共用回看期數的道理）。
INCREASE_THRESHOLD = 0.25   # 增資／分割：略過配股等常態小幅變動
DECREASE_THRESHOLD = 0.15   # 減資：較罕見且訊號較強
EXPLAIN_TOLERANCE  = 0.5    # 配股可解釋的幅度容忍；面額非 10 元者會偏，寧可誤放不誤抓
PAD                = 20     # 事件前後各需這麼多價格點，才算切在估值帶中間
PRICE_JUMP         = 0.25   # 跳空初篩；單獨不足為證（見 B）
PRODUCT_TOLERANCE  = 0.30   # 價格比 × 股數比 偏離 1 的容忍度（見 C）


def paged(table: str, cols: str, *order_cols: str) -> list[dict]:
    """分頁讀取。務必帶 order——無排序的多次查詢 Postgres 不保證跨頁順序一致。"""
    out, start = [], 0
    while True:
        q = supabase.table(table).select(cols)
        for c in order_cols:
            q = q.order(c)
        rows = q.range(start, start + 999).execute().data
        out += rows
        if len(rows) < 1000:
            return out
        start += 1000


def fetch_prices(stock_ids: set[str]) -> dict[str, list[tuple[str, float]]]:
    """
    只取候選股的價格。全市場 117 萬列載進來要數分鐘，而達到股本變動門檻的
    候選通常只有數百支——先篩再載，實測快 5 倍。

    0 不是價格而是缺值（見 init_download._extract_price），排除。
    """
    out: dict[str, list[tuple[str, float]]] = {}
    ids = sorted(stock_ids)
    for i in range(0, len(ids), 50):
        chunk = ids[i:i + 50]
        start = 0
        while True:
            rows = (supabase.table("daily_prices").select("stock_id,date,close_price")
                    .in_("stock_id", chunk).order("stock_id").order("date")
                    .range(start, start + 999).execute().data)
            for r in rows:
                if r["close_price"] and float(r["close_price"]) > 0:
                    out.setdefault(r["stock_id"], []).append(
                        (r["date"], float(r["close_price"])))
            if len(rows) < 1000:
                break
            start += 1000
    return out


def fetch_dividends() -> dict[str, list[tuple[str, float, float]]]:
    """{股票: [(除權息日, 現金股利, 股票股利)]}。條件 A 與 back_adjust 都要用，讀一次共用。"""
    out: dict[str, list[tuple[str, float, float]]] = defaultdict(list)
    for r in paged("dividends", "stock_id,ex_date,cash_dividend,stock_dividend",
                   "stock_id", "ex_date"):
        out[r["stock_id"]].append((r["ex_date"], float(r["cash_dividend"] or 0),
                                   float(r["stock_dividend"] or 0)))
    return out


def candidates(divs: dict[str, list[tuple[str, float, float]]]
               ) -> tuple[list[tuple], dict[str, dict]]:
    """
    條件 A：股本季變動達門檻，且該季區間內沒有可解釋它的還原記錄。
    回傳 (候選事件, 股票名冊)。
    """
    stocks = {s["stock_id"]: s for s in
              paged("stocks", "stock_id,name,market,delisted_at", "stock_id")}

    shares: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for r in paged("balance_sheet_quarterly", "stock_id,quarter_end_date,shares_thousand",
                   "stock_id", "quarter_end_date"):
        if r["shares_thousand"] is not None:
            shares[r["stock_id"]].append((r["quarter_end_date"], int(r["shares_thousand"])))

    official: dict[str, list[str]] = defaultdict(list)
    for r in paged("ex_right_factors", "stock_id,ex_date", "stock_id", "ex_date"):
        official[r["stock_id"]].append(r["ex_date"])

    out = []
    for sid, seq in shares.items():
        s = stocks.get(sid)
        if not s or s["delisted_at"]:
            continue                       # 下市股價格凍結，估值本就不採用
        for (d0, n0), (d1, n1) in zip(seq, seq[1:]):
            if n0 <= 0:
                continue
            r = (n1 - n0) / n0
            if not (r >= INCREASE_THRESHOLD or r <= -DECREASE_THRESHOLD):
                continue
            if any(d0 < e <= d1 for e in official.get(sid, ())):
                continue                   # 官方因子已還原（涵蓋現增與部分減資）
            # 配股能解釋的股本增幅即配股率（股票股利 ÷ 面額 10）
            sd = sum(k for e, _, k in divs.get(sid, ()) if d0 < e <= d1 and k > 0)
            if r > 0 and sd > 0 and abs(r - sd / 10) <= max(EXPLAIN_TOLERANCE * abs(r), 0.05):
                continue
            out.append((sid, d0, d1, n0, n1, r))
    return out, stocks


def confirm(cands: list[tuple], prices: dict, divs: dict) -> list[dict]:
    """
    條件 B + C：同期還原後價格留下【與股數變動互為倒數】的跳空。

    用還原後序列而非原價：正常的除權息已被 back_adjust 消除，
    留下來的跳空才是「沒有任何路徑接得到」的那一類。
    """
    adj_cache: dict[str, tuple[list[str], list[float]]] = {}
    confirmed = []
    for sid, d0, d1, n0, n1, r in cands:
        px = prices.get(sid)
        if not px:
            continue
        if sid not in adj_cache:
            dates = [d for d, _ in px]
            closes = [p for _, p in px]
            adj_cache[sid] = (dates, back_adjust(
                dates, closes, divs.get(sid, []), ex_factors.for_stock(supabase, sid)))
        dates, adj = adj_cache[sid]

        # 事件須切在估值帶中間：落在頭尾時帶內基準仍一致，對估值無害
        before = sum(1 for d in dates if d <= d1)
        if before < PAD or len(dates) - before < PAD:
            continue

        share_ratio = n1 / n0
        best = None
        for i in range(1, len(dates)):
            if not (d0 < dates[i] <= d1) or adj[i - 1] <= 0:
                continue
            price_ratio = adj[i] / adj[i - 1]
            if abs(price_ratio - 1) < PRICE_JUMP:
                continue
            product = price_ratio * share_ratio
            if abs(product - 1) <= PRODUCT_TOLERANCE and (
                    best is None or abs(product - 1) < abs(best["product"] - 1)):
                best = {"stock_id": sid, "event_date": dates[i], "quarter_end": d1,
                        "share_ratio": round(share_ratio, 6),
                        "price_ratio": round(price_ratio, 6),
                        "product": round(product, 4)}
        if best:
            confirmed.append(best)
    return confirmed


def run(dry_run: bool = False):
    print("=== 未還原資本事件稽核（全歷史）===")
    divs = fetch_dividends()
    cands, stocks = candidates(divs)
    print(f"  條件 A（股本變動且無還原記錄）：{len(cands)} 筆候選")

    prices = fetch_prices({c[0] for c in cands})
    print(f"  載入候選股價格：{len(prices)} 支")

    events = confirm(cands, prices, divs)
    print(f"  條件 B+C（價格反比跳動）確認：{len(events)} 筆，"
          f"涉及 {len({e['stock_id'] for e in events})} 支\n")

    MKT = {"TWSE": "上市", "TPEx": "上櫃", "Emerging": "興櫃"}
    agg: dict[str, set] = defaultdict(set)
    for e in events:
        agg[MKT.get(stocks[e["stock_id"]]["market"], "未知")].add(e["stock_id"])
    for m in ("上市", "上櫃", "興櫃", "未知"):
        if m in agg:
            print(f"  {m}：{len(agg[m])} 支")

    print(f"\n  幅度最大的 10 筆：")
    for e in sorted(events, key=lambda x: -abs(x["price_ratio"] - 1))[:10]:
        s = stocks[e["stock_id"]]
        print(f"    {e['stock_id']} {s['name']:<10} {e['event_date']}  "
              f"股數 ×{e['share_ratio']:.3f}  價格 ×{e['price_ratio']:.3f}  "
              f"乘積 {e['product']:.2f}")

    if dry_run:
        print("\n（--dry-run，未寫入）")
        return

    today = date.today().isoformat()
    rows = [{**e, "detected_at": today} for e in events]
    for i in range(0, len(rows), 500):
        supabase.table("unadjusted_capital_events").upsert(rows[i:i + 500]).execute()
    print(f"\n已寫入 unadjusted_capital_events：{len(rows)} 筆")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="僅列出，不寫入")
    run(**vars(ap.parse_args()))
