"""
backtest_valuation.py — 估值帶訊號回測

回答一個從未被驗證過的問題：「照這個網站的『便宜』訊號買，過去十年賺不賺？」

## 方法

每個月最後一個交易日，用**當時可得的資料**重算每支股票的歷史倍數百分位，
挑出當時被判定為「便宜」的股票，統計持有 6 / 12 / 24 個月的報酬，
與 0050（含息）同期報酬比較。

## 防 look-ahead 的三道關卡

1. **財報可用日 ≠ 財報季末**：2018-04-01 不可能知道 2018Q1 的 EPS。
   一律以申報期限（`available_date()`）為財報可用日。
2. **百分位只用當時之前的資料**：用 `expanding()` 累積計算，
   時點 T 的百分位只看得到 ≤ T 的倍數樣本，絕不用今日的帶回頭套歷史。
3. **還原價的常數等價性**：後向還原序列中，時點 T 之前的每一點都被
   「T 之後的所有股利」以**同一個因子** c(T) 縮放。訊號判斷是
   `price ≤ 基準值 × percentile(倍數序列)`，而倍數序列 = 價格 ÷ 基準值 也同乘 c(T)，
   兩邊的 c(T) 相消 → 判斷結果與 point-in-time 完全等價。
   故可安全地用單一條全期還原序列，同時算訊號與含息報酬。

## 已知偏誤（結果必然偏樂觀，不可略過）

- **倖存者偏差**：`stocks` 表已移除下市／停牌股（約 198 檔），
  回測母體只含活到今天的公司。用現有資料無法修復。
- **月採樣近似**：只取每月最後交易日，還原因子的「除息前收盤價」以
  前一個月末價近似（誤差約 factor 的 0.3%，對常數縮放的影響可忽略）。
- **無交易成本**：未計手續費、證交稅與流動性衝擊。
- **樣本期間**：資料自 2016-06 起，24 個月持有期的樣本輪次較少。
"""

import argparse
import json
import os
import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor
import pandas as pd
from dotenv import load_dotenv
from supabase import create_client

from price_adjust import back_adjust
from periodicity import report_window   # 季報／半年報的期數判定（四處共用）
from calculate_alt_valuations import decumulate  # 現金流去累計：與生產同一份實作，不另寫

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

CACHE_DIR  = os.path.join(os.path.dirname(__file__), "..", ".backtest_cache")
OUT_DIR    = os.path.join(os.path.dirname(__file__), "..", "backtest_results")

BENCHMARK  = "0050"          # 大盤基準（含息還原）
HORIZONS   = [6, 12, 24]     # 持有月數
MIN_SAMPLE = 24              # 建立百分位帶所需的最少月樣本數（2 年）
PCT_CHEAP  = 0.20            # 便宜 = 歷史倍數第 20 百分位
PE_MIN, PE_MAX = 3, 200      # 與 calculate_valuation.py 一致的倍數合理範圍
PB_MIN, PB_MAX = 0.1, 50     # 與 calculate_alt_valuations.py 一致
PS_MIN, PS_MAX     = 0.1, 200   # 與 calculate_alt_valuations.py 一致
PFCF_MIN, PFCF_MAX = 0.1, 200   # 同上


# ---------------------------------------------------------------- 資料抓取

def _paged(table: str, columns: str, order_col: str, eq: dict | None = None) -> pd.DataFrame:
    """分頁取回整表（Supabase 單次上限 1000 筆；必須 order 否則跨頁順序不保證）"""
    rows, offset = [], 0
    while True:
        q = supabase.table(table).select(columns)
        for col, val in (eq or {}).items():
            q = q.eq(col, val)
        data = q.order(order_col).range(offset, offset + 999).execute().data
        rows.extend(data)
        if len(data) < 1000:
            return pd.DataFrame(rows)
        offset += 1000


def _cached(name: str, loader) -> pd.DataFrame:
    """把抓下來的資料存成 CSV，避免反覆重跑時再打一次 Supabase"""
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, f"{name}.csv")
    if os.path.exists(path):
        print(f"  [快取] {name}")
        return pd.read_csv(path, dtype={"stock_id": str})
    df = loader()
    df.to_csv(path, index=False)
    return df


def month_end_dates() -> list[str]:
    """以 2330 的交易日曆取得每月最後一個交易日（權值股不會整月停牌）"""
    df = _cached("calendar", lambda: _paged(
        "daily_prices", "date,stock_id", "date", {"stock_id": "2330"}))
    s = pd.to_datetime(df["date"])
    return s.groupby(s.dt.to_period("M")).max().dt.strftime("%Y-%m-%d").tolist()


def fetch_month_end_prices(dates: list[str], stock_ids: list[str]) -> pd.DataFrame:
    """
    只抓每月最後交易日的全市場收盤價（全量日價約 500 萬筆，抓不動也用不到）。

    必須「逐股票 + date in (...)」而非「逐日期抓全市場」：daily_prices 主鍵為
    (stock_id, date)，單以 date 過濾用不到索引，Supabase 會 statement timeout。
    """
    def fetch_one(sid: str) -> list[dict]:
        sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
        for attempt in range(3):
            try:
                return (sb.table("daily_prices").select("stock_id,date,close_price")
                        .eq("stock_id", sid).in_("date", dates).execute().data)
            except Exception as e:
                if attempt == 2:
                    raise RuntimeError(f"{sid} 抓取失敗: {e}") from e
                time.sleep(2 * (attempt + 1))

    def load():
        rows, done = [], 0
        with ThreadPoolExecutor(max_workers=8) as pool:
            for data in pool.map(fetch_one, stock_ids):
                rows.extend(data)
                done += 1
                if done % 200 == 0:
                    print(f"  [{done}/{len(stock_ids)}] 已抓 {len(rows)} 筆")
        return pd.DataFrame(rows)

    return _cached("month_end_prices", load)


def load_all() -> dict:
    print("讀取資料…")
    dates = month_end_dates()
    stocks = _cached("stocks", lambda: _paged("stocks", "stock_id,name,industry,market,listed_shares", "stock_id"))
    return {
        "dates":     dates,
        "prices":    fetch_month_end_prices(dates, stocks["stock_id"].tolist()),
        "stocks":    stocks,
        "eps":       _cached("eps",       lambda: _paged("eps_quarterly", "stock_id,quarter_end_date,eps", "stock_id")),
        "bvps":      _cached("bvps",      lambda: _paged("balance_sheet_quarterly",
                                                         "stock_id,quarter_end_date,book_value_per_share,shares_thousand", "stock_id")),
        "revenue":   _cached("revenue",   lambda: _paged("monthly_revenue", "stock_id,year_month,revenue", "stock_id")),
        "cashflows": _cached("cashflows", lambda: _paged("cash_flows_quarterly",
                                                         "stock_id,quarter_end_date,operating_cf,capex", "stock_id")),
        "dividends": _cached("dividends", lambda: _paged("dividends", "stock_id,ex_date,cash_dividend,stock_dividend", "stock_id")),
        "factors":   _cached("ex_factors", lambda: _paged("ex_right_factors", "stock_id,ex_date,prev_close,ref_price", "stock_id")),
    }


# ---------------------------------------------------------- 財報可用日對照

def available_date(quarter_end: pd.Timestamp) -> pd.Timestamp:
    """
    財報在市場上真正可得的日期＝主管機關的申報期限。
    Q1→5/15、Q2→8/14、Q3→11/14、Q4（年報）→次年 3/31。
    半年報公司（興櫃）6/30 的期限為 8/31，取兩者較晚者以策保守。
    直接拿季末日當可用日，等於讓回測偷看還沒公布的財報。
    """
    y, m = quarter_end.year, quarter_end.month
    return {3:  pd.Timestamp(y, 5, 15),
            6:  pd.Timestamp(y, 8, 31),
            9:  pd.Timestamp(y, 11, 14),
            12: pd.Timestamp(y + 1, 3, 31)}[m]


# ------------------------------------------------------------ 面板組裝

def adjusted_price_matrix(prices: pd.DataFrame, dividends: pd.DataFrame,
                          factors: pd.DataFrame, dates: list[str]) -> pd.DataFrame:
    """
    月末還原價矩陣（列＝月末日、欄＝股票）。
    還原用真實除息日與股利，但基準收盤價以月末價近似（見檔頭「月採樣近似」）。

    有交易所公告的還原因子就優先用——自算公式涵蓋不了現金增資與減資。
    官方因子是「公告參考價 ÷ 公告前收盤價」，不受月末近似影響，比自算更準。
    """
    # 配股必須一起帶：只還原現金股利會在配股日留下數十個百分點的假跌幅，
    # 使回測的歷史倍數偏低（見 price_adjust.py 模組說明）
    div = dividends.fillna({"cash_dividend": 0, "stock_dividend": 0})
    ex_map = {sid: list(zip(g["ex_date"], g["cash_dividend"], g["stock_dividend"]))
              for sid, g in div.groupby("stock_id")}

    f = factors[pd.to_numeric(factors["prev_close"], errors="coerce") > 0].copy()
    f["factor"] = pd.to_numeric(f["ref_price"]) / pd.to_numeric(f["prev_close"])
    official_map = {sid: dict(zip(g["ex_date"], g["factor"]))
                    for sid, g in f.groupby("stock_id")}

    wide = prices.pivot_table(index="date", columns="stock_id", values="close_price")
    wide = wide.reindex(dates)          # 對齊完整月曆，缺月留 NaN（停牌）

    adj = {}
    for sid in wide.columns:
        s = wide[sid].dropna()
        if s.empty:
            continue
        adj[sid] = pd.Series(
            back_adjust(s.index.tolist(), s.tolist(), ex_map.get(sid, []),
                        official_map.get(sid)), index=s.index)
    return pd.DataFrame(adj).reindex(dates)


def share_factor_table(bvps: pd.DataFrame) -> pd.DataFrame:
    """
    每支股票各季的股數因子 = 當季股數 ÷ 該股最新股數。

    與 calculate_valuation.share_factors 同一套邏輯，兩邊必須一致：
    EPS 與每股淨值都是各季用當時股數申報的，配股後股數變多、數值變小，
    財報不追溯調整；而股價已除權還原到最新股數基準，分母不換算就會壓低倍數。
    2026-07-22 實測 1436 的 P/E 因此被壓低 43%。
    """
    df = bvps.copy()
    df["quarter_end_date"] = pd.to_datetime(df["quarter_end_date"])
    df["shares_thousand"] = pd.to_numeric(df["shares_thousand"], errors="coerce")
    df = df.dropna(subset=["shares_thousand"]).sort_values(["stock_id", "quarter_end_date"])
    df = df[df["shares_thousand"] > 0]
    latest = df.groupby("stock_id")["shares_thousand"].last()
    df["factor"] = df["shares_thousand"] / df["stock_id"].map(latest)
    return df[["stock_id", "quarter_end_date", "factor"]]


def fundamental_matrix(fund: pd.DataFrame, value_col: str, dates: list[str],
                       ttm_window: int | None,
                       factors: pd.DataFrame | None = None) -> pd.DataFrame:
    """
    把季頻基本面攤成月末面板：每個月末取「當時已公布」的最新一筆。
    ttm_window 不為 None 時先做滾動加總（EPS 需 TTM，每股淨值是存量不需要）。

    factors 給定時，先把每季數值換算到該股的最新股數基準，再滾動加總——
    順序不可顛倒，每季 EPS 要對應自己那一季的股數。
    """
    df = fund.copy()
    df["quarter_end_date"] = pd.to_datetime(df["quarter_end_date"])
    df[value_col] = pd.to_numeric(df[value_col], errors="coerce")
    df = df.dropna(subset=[value_col]).sort_values(["stock_id", "quarter_end_date"])

    if factors is not None and not factors.empty:
        # 股本季度與財報季度未必逐一對齊（興櫃為半年報），故以 merge_asof 向前對應；
        # 對應不到者維持原值（因子 1），不猜、不外插
        # merge_asof 要求左右兩表都依 on 鍵全域排序（by 分組不豁免此規則）
        df = pd.merge_asof(
            df.sort_values("quarter_end_date"), factors.sort_values("quarter_end_date"),
            on="quarter_end_date", by="stock_id", direction="backward",
        )
        df[value_col] = df[value_col] * df["factor"].fillna(1.0)
        df = df.sort_values(["stock_id", "quarter_end_date"])

    if ttm_window is not None:
        # 興櫃為半年報（月份只有 6、12），4 期會誤把 2 年當 TTM，改用 2 期。
        # 2026-07-22：原本這裡看「全部歷史」的月份集合，一筆陳年 3/31 就會把
        # 半年報公司誤判成季報——那正是當天在生產路徑修掉的缺陷，回測卻漏改。
        # 回測是所有旗標門檻（pb_reliable 2 倍、pe_deep_discount 3 倍、帶寬分位）
        # 的依據，用錯 TTM 等於門檻建在污染的樣本上。改用共用判定。
        def ttm(g):
            w = report_window(g["quarter_end_date"])
            return g[value_col].rolling(w, min_periods=w).sum()
        df["value"] = df.groupby("stock_id", group_keys=False).apply(ttm)
    else:
        df["value"] = df[value_col]

    df = df.dropna(subset=["value"])
    df["avail"] = df["quarter_end_date"].map(available_date)

    # 每個月末取最後一筆 avail ≤ 月末的值 → forward fill
    panel = (df.pivot_table(index="avail", columns="stock_id", values="value", aggfunc="last")
               .sort_index())
    return _align_to_month_ends(panel, dates)


def _align_to_month_ends(panel: pd.DataFrame, dates: list[str]) -> pd.DataFrame:
    """把任意日期索引的面板 forward-fill 對齊到回測月末（列＝dates、欄不變）"""
    idx = pd.to_datetime(dates)
    return panel.reindex(panel.index.union(idx)).ffill().reindex(idx).set_axis(dates)


def per_share(total_panel: pd.DataFrame, shares_divisor: pd.Series) -> pd.DataFrame:
    """
    把「總額」面板（元）換算成「每股」面板（元/股），除數為當前股數（千股×1000）。

    為何用當前股數這個常數，而非逐期股數：便宜訊號＝price ≤ base×分位(price/base)，
    分子的 base 與序列裡的 base 共用同一個常數除數，相消後訊號與除數無關；
    它只決定倍數是否落在 [MIN, MAX] 界內。這與 calculate_alt_valuations 的 P/S、
    P/FCF 定義一致（那裡也用 listed_shares 常數），營收與現金流是「總額」而非
    每股申報值，故不套用 share_factor（那是給 EPS／每股淨值這類每股值用的）。
    """
    return total_panel.div(shares_divisor)


def revenue_ttm_ps_matrix(revenue: pd.DataFrame, shares_divisor: pd.Series,
                          dates: list[str]) -> pd.DataFrame:
    """
    月營收攤成「月末 TTM 每股營收」面板（P/S 的基準值），列＝月末、欄＝股票。

    定義同 calculate_alt_valuations.calculate_ps：
    每股營收 = 最近 12 個月營收(元) ÷ (listed_shares 千股 × 1000)。

    防 look-ahead：某月營收於次月 10 日前才公告，站在月末只能用到上上月為止。
    故 TTM(至月 M) 的可用日設為「M+1 月的月末交易日」，對齊回測抽樣點——
    直接拿當月營收會偷看到尚未公布的數字。
    """
    df = revenue.copy()
    df["revenue"] = pd.to_numeric(df["revenue"], errors="coerce")
    df = df.dropna(subset=["revenue"])
    df["ym"] = pd.PeriodIndex(df["year_month"].astype(str).str[:7], freq="M")

    wide = df.pivot_table(index="ym", columns="stock_id", values="revenue", aggfunc="last")
    # 補齊連續月份，缺月留 NaN（rolling min_periods=12 會自動略過期數不足處）
    wide = wide.reindex(pd.period_range(wide.index.min(), wide.index.max(), freq="M"))
    rps = per_share(wide.rolling(12, min_periods=12).sum(), shares_divisor)

    # 可用日 = 次月的月末交易日：M→M+1 是單射，直接改寫索引即可（不必 stack 往返）。
    # 對應不到月末交易日者（如序列尾端）→ NaT，剔除。
    date_of_month = {pd.Period(d, freq="M"): d for d in dates}
    rps.index = pd.to_datetime([date_of_month.get(m + 1) for m in rps.index])
    rps = rps[rps.index.notna()]
    return _align_to_month_ends(rps, dates)


def fcf_ttm_ps_matrix(cashflows: pd.DataFrame, shares_divisor: pd.Series,
                      dates: list[str]) -> pd.DataFrame:
    """
    現金流量表攤成「月末 TTM 每股自由現金流」面板（P/FCF 的基準值）。

    定義同 calculate_alt_valuations.calculate_pfcf：
      1. 現金流量表為年度累計，先用生產同一份 decumulate() 還原單季（缺前一季者剔除）
      2. FCF = 營業現金流 + 資本支出（capex 為負，加法即扣除）
      3. 經 fundamental_matrix 依申報期限做 TTM（半年報公司在步驟 1 已全被剔除，
         實務上 w 恆為 4；行為與生產一致）
      4. 換算每股（常數股數，理由見 per_share）

    負 TTM FCF 的月份：base ≤ 0 會被 cheap_mask 的 base>0 濾除，等同「負 FCF 不納入」。
    """
    cf = cashflows.copy()
    cf["quarter_end_date"] = cf["quarter_end_date"].astype(str)
    cf["operating_cf"] = pd.to_numeric(cf["operating_cf"], errors="coerce")
    cf["capex"]        = pd.to_numeric(cf["capex"],        errors="coerce")
    cf = cf.dropna(subset=["operating_cf", "capex"])
    cf = cf.groupby("stock_id", group_keys=False).apply(
        lambda g: decumulate(g, ("operating_cf", "capex")))
    cf["fcf"] = cf["operating_cf"] + cf["capex"]

    fcf_ttm = fundamental_matrix(cf, "fcf", dates, ttm_window=4)   # TTM 總額（元）
    return per_share(fcf_ttm, shares_divisor)


# ------------------------------------------------------------ 回測核心

def forward_returns(adj: pd.DataFrame, h: int, mask: pd.DataFrame | None = None) -> pd.DataFrame:
    """
    每個 (月末, 股票) 持有 h 個月的含息報酬長表，附同期 0050 報酬。
    還原價相除即含息總報酬。mask 給定時只保留訊號成立的格子。
    """
    fwd = adj.shift(-h) / adj - 1.0
    s = fwd.stack()
    if mask is not None:
        # pandas 3.0 的 stack() 不再丟棄 NaN，必須顯式只留 True，
        # 否則會把整個母體當成訊號（各模型跑出一模一樣的數字即為此症狀）
        sel = mask.stack().fillna(False).astype(bool)
        s = s[sel.reindex(s.index, fill_value=False)]
    df = s.reset_index()
    df.columns = ["date", "stock_id", "ret"]
    df["bench"] = df["date"].map(fwd[BENCHMARK])
    df["horizon"] = h
    return df.dropna()


def cheap_mask(adj: pd.DataFrame, base: pd.DataFrame,
               lo: float, hi: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    「便宜」訊號的布林面板（列＝月末、欄＝股票），以及每格的折價倍數。

    base = 估值基準值面板（P/E 用 TTM EPS，P/B 用每股淨值）。
    折價倍數 = 便宜價 ÷ 現價。訊號成立時必 ≥1，數字越大代表現價離便宜價越遠。

    為什麼要記錄它：這個比值極大時，多半不是「跌得很便宜」而是
    「歷史倍數已經不適用了」——公司基本面劇變，早年的高倍數對現在毫無參考價值。
    2026-07-22 實測 4763 材料-KY：淨值 10 年成長 8 倍、股價腰斬，
    歷史 P/B 從 39 倍掉到 2.3 倍，目標價因此算出 830 元（現價 50.3）。
    """
    base = base.reindex(columns=adj.columns).where(base > 0)
    mult = (adj / base).where(lambda m: (m >= lo) & (m <= hi))

    # expanding：時點 T 的百分位只用 ≤T 的樣本，這是本回測不作弊的關鍵
    cheap_mult = mult.expanding(min_periods=MIN_SAMPLE).quantile(PCT_CHEAP)
    cheap_price = base * cheap_mult
    return (adj <= cheap_price) & mult.notna(), cheap_price / adj


def backtest(model: str, adj: pd.DataFrame, base: pd.DataFrame,
             lo: float, hi: float) -> pd.DataFrame:
    """回傳每一筆「便宜訊號 → 未來報酬」的長表"""
    is_cheap, discount = cheap_mask(adj, base, lo, hi)
    df = pd.concat([forward_returns(adj, h, is_cheap) for h in HORIZONS], ignore_index=True)
    df["model"] = model
    # 折價倍數逐格對應回長表，供事後分析「深度折價是機會還是模型失效」
    df["discount"] = pd.MultiIndex.from_arrays(
        [df["date"], df["stock_id"]]).map(discount.stack())
    return df


def universe_returns(adj: pd.DataFrame) -> pd.DataFrame:
    """全市場等權報酬，作為「隨便買一支」的對照組"""
    return pd.concat([forward_returns(adj, h) for h in HORIZONS], ignore_index=True)


def summarize(df: pd.DataFrame, label: str) -> pd.DataFrame:
    g = df.groupby("horizon")
    return pd.DataFrame({
        "組別":        label,
        "樣本數":      g.size(),
        "報酬中位數":  (g["ret"].median() * 100).round(2),
        "報酬平均":    (g["ret"].mean() * 100).round(2),
        "0050同期中位": (g["bench"].median() * 100).round(2),
        "勝率%":       (g.apply(lambda x: (x["ret"] > x["bench"]).mean()) * 100).round(1),
        "正報酬率%":   (g.apply(lambda x: (x["ret"] > 0).mean()) * 100).round(1),
    }).reset_index()


def export_frontend(overall: pd.DataFrame, by_ind: pd.DataFrame, dates: list[str]) -> None:
    """
    產生前端用的統計資料檔。回測結果是靜態的（重跑才會變），
    走檔案而非資料庫：不佔 Supabase 免費層容量，也不需要新排程。
    """
    def rows(df):
        return ",\n".join("  " + json.dumps(r, ensure_ascii=False) for r in df.to_dict("records"))

    ov = overall.rename(columns={
        "組別": "group", "樣本數": "n", "報酬中位數": "median", "報酬平均": "mean",
        "0050同期中位": "bench", "勝率%": "winRate", "正報酬率%": "positiveRate"})
    bi = by_ind.rename(columns={
        "樣本數": "n", "報酬中位數": "median", "勝過0050": "winRate",
        "同業母體": "peer", "超額": "excess"})

    ts = f"""// 由 scripts/backtest_valuation.py 產生，請勿手動編輯。
// 重跑回測後此檔會被覆寫；判讀邏輯寫在 lib/backtest.ts。

export interface OverallRow {{
  horizon: number; group: string; n: number
  median: number; mean: number; bench: number; winRate: number; positiveRate: number
}}

export interface IndustryRow {{
  model: string; industry: string; n: number
  median: number; winRate: number; peer: number; excess: number
}}

/** 回測期間取自資料本身的第一與最後一個月末交易日 */
export const BACKTEST_PERIOD = {{ from: '{dates[0]}', to: '{dates[-1]}', months: {len(dates)} }}

/** 持有 12 個月的分產業結果；其餘持有期見 OVERALL */
export const INDUSTRY_HORIZON = 12

export const OVERALL: OverallRow[] = [
{rows(ov)}
]

export const BY_INDUSTRY: IndustryRow[] = [
{rows(bi)}
]
"""
    path = os.path.join(os.path.dirname(__file__), "..", "frontend", "lib", "backtestStats.ts")
    with open(path, "w", encoding="utf-8") as f:
        f.write(ts)
    print(f"前端統計檔已更新：{os.path.normpath(path)}")


def main():
    ap = argparse.ArgumentParser(description="估值訊號回測")
    ap.add_argument("--refresh", action="store_true",
                    help="清掉 .backtest_cache 重新抓取。任何會改變原始資料的修正"
                         "（欄位新增、數值 patch、還原邏輯變更）之後都必須加這個參數")
    args = ap.parse_args()

    if args.refresh and os.path.isdir(CACHE_DIR):
        # 快取只看檔案在不在，不看內容是否過期——資料修正後不清就會拿舊值算，
        # 而且結果看起來完全正常。2026-07-22 因此踩過一次（schema 加欄位後沒清）。
        shutil.rmtree(CACHE_DIR)
        print(f"已清除快取 {CACHE_DIR}")

    data = load_all()
    dates = data["dates"]

    print("組裝面板…")
    adj = adjusted_price_matrix(data["prices"], data["dividends"], data["factors"], dates)
    # 分母也要換算到最新股數基準，否則與「已除權還原的股價」基準不一致
    factors = share_factor_table(data["bvps"])
    eps_ttm = fundamental_matrix(data["eps"],  "eps",                  dates, 4,    factors)
    bvps    = fundamental_matrix(data["bvps"], "book_value_per_share", dates, None, factors)

    # P/S、P/FCF 的每股基準用當前股數（常數）換算，見 per_share 說明
    shares = pd.to_numeric(data["stocks"].set_index("stock_id")["listed_shares"], errors="coerce")
    shares_divisor = (shares * 1000).where(shares > 0)
    ps_base   = revenue_ttm_ps_matrix(data["revenue"],   shares_divisor, dates)
    pfcf_base = fcf_ttm_ps_matrix(data["cashflows"], shares_divisor, dates)

    print(f"  月數 {len(dates)}（{dates[0]} ~ {dates[-1]}）、股票 {adj.shape[1]} 支")

    print("回測中…")
    pe   = backtest("P/E",   adj, eps_ttm,   PE_MIN,   PE_MAX)
    pb   = backtest("P/B",   adj, bvps,      PB_MIN,   PB_MAX)
    ps   = backtest("P/S",   adj, ps_base,   PS_MIN,   PS_MAX)
    pfcf = backtest("P/FCF", adj, pfcf_base, PFCF_MIN, PFCF_MAX)
    uni = universe_returns(adj)

    models = [("P/E 便宜", pe), ("P/B 便宜", pb), ("P/S 便宜", ps), ("P/FCF 便宜", pfcf)]
    parts = [summarize(uni, "全市場等權（對照）")]
    for name, df in models:
        if not df.empty:
            parts.append(summarize(df, name))
    overall = pd.concat(parts, ignore_index=True)

    industry = data["stocks"].set_index("stock_id")["industry"]
    signals = pd.concat([d for _, d in models if not d.empty], ignore_index=True)
    signals["industry"] = signals["stock_id"].map(industry)
    uni["industry"] = uni["stock_id"].map(industry)

    # 同產業母體中位數＝對照組。少了它，「半導體便宜股報酬高」無法區分
    # 是訊號有效還是整個半導體都在漲——這種比較會把產業 beta 誤讀成選股能力。
    ind_base = (uni[uni["horizon"] == 12].groupby("industry")["ret"].median() * 100)

    g12 = signals[signals["horizon"] == 12].assign(贏=lambda d: d["ret"] > d["bench"])
    by_ind = (g12.groupby(["model", "industry"])
                 .agg(樣本數=("ret", "size"),
                      報酬中位數=("ret", lambda s: s.median() * 100),
                      勝過0050=("贏", lambda s: s.mean() * 100))
                 .reset_index())
    by_ind["同業母體"] = by_ind["industry"].map(ind_base)
    by_ind["超額"] = by_ind["報酬中位數"] - by_ind["同業母體"]
    by_ind = (by_ind[by_ind["樣本數"] >= 30]
              .round(2)
              .sort_values(["model", "超額"], ascending=[True, False]))

    os.makedirs(OUT_DIR, exist_ok=True)
    overall.to_csv(os.path.join(OUT_DIR, "overall.csv"), index=False, encoding="utf-8-sig")
    by_ind.to_csv(os.path.join(OUT_DIR, "by_industry.csv"), index=False, encoding="utf-8-sig")
    signals.to_csv(os.path.join(OUT_DIR, "signals.csv"), index=False, encoding="utf-8-sig")
    # 全市場母體也存檔：by_industry 的「同業母體」欄是用它算的，
    # 少了它就無法在事後用一致的定義重做分析——例如檢驗產業標籤能不能外推
    # （用前半期定義、後半期驗證），那需要逐期重算母體中位數。
    uni.to_csv(os.path.join(OUT_DIR, "universe.csv"), index=False, encoding="utf-8-sig")
    export_frontend(overall, by_ind, dates)

    pd.set_option("display.unicode.east_asian_width", True, "display.width", 200)
    print("\n=== 整體結果（報酬單位 %）===")
    print(overall.to_string(index=False))
    print("\n=== 分產業（持有 12 個月，樣本 ≥30）===")
    print(by_ind.to_string(index=False))
    print(f"\n結果已寫入 {OUT_DIR}")
    print("提醒：母體不含已下市股票，結果偏樂觀；未計交易成本。")


if __name__ == "__main__":
    main()
