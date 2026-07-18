# CLAUDE.md — 台股估值查詢網站

## 資料誠信原則（最高優先，違反視同嚴重缺陷）

> **寫進資料庫的每一個數字，都必須追溯得到來源明確提供的值。**
> 判斷標準：對任何一個寫入的數字，都要能回答「這是誰給的？哪一天的？」——答不出來就不要寫。

這不是理想，是這個專案付出過代價換來的規則。以下四條各自對應一次真實事故：

### 1. 不得用系統時間當作資料日期

一律使用來源自己回報的日期欄位（`Date`、`資料年月`、`年度`+`季別`）。

交易所的資料日期未必等於今天——休市、來源延遲都會造成落差。
**2026-07-17 事故**：`daily_price_update.py` 以 `date.today()` 蓋章，
而 `openapi.twse.com.tw` 是 T-1 批次檔，導致上市股價整批位移一個交易日，
且颱風休市的 7/10 被寫入 1,090 筆不存在的價格。

### 2. 不得以另一個指標頂替

同一個欄位必須始終是同一個東西，否則歷史序列的基準不一致，百分位帶會失真。

**案例**：興櫃原本「`LatestPrice` 抓不到就用 `Average`」，等於把加權均價存進
`close_price`。沒有成交就是沒有價格，該跳過而非填補。

### 3. 不得把「缺值」變成數字

缺資料就寫 `null` 或跳過，不要用 `0`、前一期的值、或任何推估值填補。

**案例**：`calculate_alt_valuations` 的 `latest_fcf_ps` 曾沿用「最後一個為正的季度」，
使近期 FCF 轉負的公司用過期現金流算出目標價，且畫面上毫無提示。

### 4. 模型不適用時要主動寫回 null

計算失敗時「跳過不寫」會讓上次的舊值永久殘留，且再也沒有機制修正它。
參見 `calculate_valuation.run()` 與 `calculate_alt_valuations.cleared()`。

### 5. 抓取失敗必須讓工作失敗，不得吞掉錯誤後回報成功

「來源故障」與「該筆確實沒有資料」是兩件事，程式碼必須能區分：
故障要重試，重試仍失敗就拋例外，並讓整個工作以 exit code 1 結束以觸發通知。
**絕不可** catch 之後回傳空清單——那會讓呼叫端把故障當成「無資料」，
繼續跑完並回報成功。

**2026-07-14 事故**：`daily_price_update.py` 的 TPEx 連線中斷（IncompleteRead），
fetch 吞掉例外回傳空 dict，整個上櫃市場（約 900 支）當日沒寫入，
工作卻回報「完成！」，缺口三天後才被跨來源比對發現。

實作：
- FinMind 呼叫一律經 `finmind_client.fetch()`（失敗會拋 `FinMindError`），
  搭配 `FailureTracker`：單支失敗不中斷整批（4 小時的下載不該因一次逾時全毀），
  但收尾 `tracker.finish()` 若有任何失敗就 exit 1。
- 交易所呼叫一律經 `daily_price_update.get_json()`（失敗拋 `FetchError`）；
  任一市場失敗，整個工作以 exit 1 結束。

### 驗證資料正確性的方法

`scripts/validate_valuations.py` **只檢查內部一致性**，抓不到「資料是舊的」、
「單位錯了」、「日期位移」——這些錯誤的數字彼此自洽，規則全部通過。

**唯一可靠的方法是跨來源比對**：用 FinMind 驗證 TWSE、用交易所公告值驗證自算值、
用已知的真實世界數字（如台積電年報）驗證推算結果。
2026-07-17 的現金流累計 bug 與股價位移 bug，都是靠跨來源比對才發現的。

---

## 專案架構概覽

台灣股票市場估值查詢系統，支援 P/E、P/B、P/S、P/FCF 四種估值模型，資料來自 FinMind 免費 API，儲存於 Supabase。

```
tw-eps-watcher/
├── scripts/           # Python 後端腳本（資料下載 + 估值計算）
├── frontend/          # Next.js 15 前端（Tailwind + Recharts）
├── schema.sql         # 完整資料庫 Schema（含 ALTER TABLE 擴充語句）
├── .env               # SUPABASE_URL / SUPABASE_KEY / FINMIND_TOKEN
└── TODO.md            # 功能開發進度
```

---

## 資料庫結構（Supabase PostgreSQL）

| 資料表 | 用途 | 主鍵 |
|--------|------|------|
| `stocks` | 股票名冊（含 `listed_shares` 千股） | `stock_id` |
| `eps_quarterly` | 季度 EPS | `(stock_id, quarter_end_date)` |
| `daily_prices` | 日收盤價 | `(stock_id, date)` |
| `valuations` | 預算估值結果（P/E + P/B + P/S + P/FCF） | `stock_id` |
| `dividends` | 現金股利（殖利率圖用） | `(stock_id, ex_date)` |
| `balance_sheet_quarterly` | 每股淨值（P/B 用） | `(stock_id, quarter_end_date)` |
| `monthly_revenue` | 月營收（單位：**元**，P/S 用） | `(stock_id, year_month)` |
| `cash_flows_quarterly` | 營業現金流 + 資本支出（P/FCF 用） | `(stock_id, quarter_end_date)` |

### valuations 欄位分組

- **P/E**：`ttm_eps`, `cheap_pe/fair_pe/expensive_pe`, `cheap/fair/expensive_price`, `status`, `normalized_eps`, `warning`
- **P/B**：`pb_book_value`, `pb_cheap/fair/expensive_pb`, `pb_cheap/fair/expensive_price`, `pb_status`
- **P/S**：`ps_revenue_per_share`, `ps_cheap/fair/expensive_ps`, `ps_cheap/fair/expensive_price`, `ps_status`
- **P/FCF**：`pfcf_per_share`, `pfcf_cheap/fair/expensive_pfcf`, `pfcf_cheap/fair/expensive_price`, `pfcf_status`

---

## Python 腳本（scripts/）

### 資料下載（需執行一次，之後定期更新）

| 腳本 | 資料來源 | 目標資料表 |
|------|---------|-----------|
| `init_download.py` | FinMind | stocks / eps_quarterly / daily_prices |
| `download_dividends.py` | FinMind `TaiwanStockDividend` | dividends |
| `download_balance_sheet.py` | FinMind `TaiwanStockBalanceSheet` | balance_sheet_quarterly |
| `download_monthly_revenue.py` | FinMind `TaiwanStockMonthRevenue` + `TaiwanStockInfo` | monthly_revenue + stocks.listed_shares |
| `download_cash_flows.py` | FinMind `TaiwanStockCashFlowsStatement` | cash_flows_quarterly |

所有下載腳本支援 `--skip-file <file>` 斷點續傳，以及 `--discover` 模式（印出 FinMind 欄位名稱後退出）。

### 估值計算

| 腳本 | 說明 |
|------|------|
| `calculate_valuation.py` | P/E 估值（TTM EPS × 歷史 P/E 百分位），寫入 valuations |
| `calculate_alt_valuations.py` | P/B / P/S / P/FCF 三種替代模型，更新 valuations 的對應欄位 |
| `daily_price_update.py` | 每日收盤後更新 daily_prices 與 valuations.current_price |
| `quarterly_eps_update.py` | 財報季更新 eps_quarterly，重算 P/E 估值 |

### FinMind 速率限制

免費版每次呼叫後需等 **6.5 秒**（`CALL_INTERVAL = 6.5`）。
全市場約 2,000 支股票，下載一個資料集約需 **3.5~4 小時**。

---

## 估值模型邏輯

所有模型的核心邏輯相同：
1. 建立歷史「倍數」序列（P/E、P/B、P/S、P/FCF）
2. 計算第 20/50/80 百分位 → 便宜/合理/昂貴倍數
3. `目標價 = 當前基準值 × 倍數百分位`

| 模型 | 基準值 | 倍數限制 |
|------|--------|---------|
| P/E  | TTM EPS（元/股） | 3–200 |
| P/B  | 最新每股淨值（元/股） | 0.1–50 |
| P/S  | TTM 每股營收（元÷(千股×1000)=元/股） | 0.1–200 |
| P/FCF | TTM FCF per share（元÷(千股×1000)=元/股） | 0.1–200 |

### P/E 特殊情況處理

```
TTM EPS ≤ 0.5 且 5年均值 ≤ 0.5  → 顯示「EPS 長期偏低」警告，P/E 不適用
TTM EPS << 5年均值（< 30%）      → 改用 5 年標準化 EPS 計算目標價
TTM EPS >> 5年均值（> 3 倍）     → 顯示「獲利高峰」警告
```

---

## 前端架構（frontend/，Next.js 15）

### API 路由（app/api/）

| 路由 | 回傳 |
|------|------|
| `/api/search?q=` | 股票代碼/名稱搜尋結果（前 8 筆） |
| `/api/market-stats` | 全市場便宜/合理/昂貴比例、中位 P/E |
| `/api/watchlist?codes=` | 自選股估值資料 |
| `/api/chart/[code]` | P/E 河流圖資料（月採樣，Point[]） |
| `/api/chart/pb/[code]` | P/B 河流圖資料 |
| `/api/chart/ps/[code]` | P/S 河流圖資料 |
| `/api/yield-chart/[code]` | 殖利率河流圖資料 |

所有 chart API 回傳格式相同：
```typescript
{ chartData: { date, price, cheap, fair, expensive }[], valuation: {...} }
```

### 關鍵元件（components/）

| 元件 | 說明 |
|------|------|
| `ValuationCard` | 主估值卡片，含 P/E + P/B + P/S + P/FCF 四區塊 |
| `PERiverChart` | P/E 河流圖（Recharts） |
| `AltRiverChart` | 通用替代估值河流圖，props: `code` + `model: 'pb' \| 'ps'` |
| `YieldRiverChart` | 殖利率河流圖 |
| `CheapLeaderboard` | 便宜股排行榜（Server Component + 客戶端篩選） |
| `MarketThermometer` | 市場溫度計（全市場估值分布） |
| `WatchlistButton/Panel` | 自選股（localStorage） |

### 股票詳情頁區塊順序（app/stock/[code]/page.tsx）

1. 返回連結 + 股票標頭
2. ValuationCard（P/E + 替代模型估值數字）
3. P/E 河流圖（10 年）
4. 殖利率河流圖（10 年）
5. P/B 河流圖（有資料時才顯示）
6. P/S 河流圖（有資料時才顯示）

---

## 部署與排程

- **前端**：Vercel，自動部署 main 分支
- **排程**：GitHub Actions（私有 repo，免費額度 **2,000 分鐘／月**，設計時須試算）

| Workflow | 時機 | 內容 | 耗時 |
|----------|------|------|------|
| `daily_update.yml` | 交易日 14:30 | 股價 + 各模型狀態 | ~1 分 |
| `monthly_fundamentals.yml` | 每月 11 日 | 月營收（OpenAPI）+ 重算 | ~2 小時 |
| `quarterly_eps.yml` | 財報季每週一 | EPS（FinMind）+ 重算 P/E | 遞減，首次 ~4.2 小時 |
| `quarterly_fundamentals.yml` | 財報季 2 次 | 淨值（OpenAPI）+ 現金流（FinMind）+ 重算 | ~6.5 小時 |
| `dividends_update.yml` | 7 月／9 月各一次 | 股利（FinMind）+ 重算 | ~6.5 小時 |
| `weekly_validate.yml` | 每週一 09:00 | 估值一致性抽驗 | ~2 分 |

### 資料來源選擇原則

**優先用 TWSE／TPEx OpenAPI 的整批端點**，只在沒有對應端點時才用 FinMind：

- FinMind 免費版每次呼叫需間隔 6.5 秒 → 全市場一輪約 **4.2 小時**
- OpenAPI 整批端點一次回傳全市場 → **數秒**

| 資料 | 來源 | 端點 |
|------|------|------|
| 股價 | TWSE/TPEx OpenAPI | 3 次呼叫（上市／上櫃／興櫃） |
| 月營收 | TWSE/TPEx OpenAPI | `t187ap05_L`／`mopsfin_t187ap05_O`／`t187ap05_R` |
| 每股淨值、負債比 | TWSE/TPEx OpenAPI | `t187ap07_*`（依市場 × 行業別，約 16 個端點） |
| EPS | FinMind | 損益表 OpenAPI 疑為累計揭露，未驗證前不改用 |
| 現金流量表 | FinMind | 無整批 OpenAPI 端點 |
| 股利 | FinMind | 無整批 OpenAPI 端點 |
- **手動執行順序**（新環境初始化）：
  1. 在 Supabase 執行 `schema.sql`
  2. `python scripts/init_download.py`
  3. `python scripts/backfill_industry.py`
  4. `python scripts/download_dividends.py`
  5. `python scripts/download_balance_sheet.py`
  6. `python scripts/download_monthly_revenue.py`
  7. `python scripts/download_cash_flows.py`
  8. `python scripts/calculate_valuation.py`
  9. `python scripts/calculate_alt_valuations.py`

---

## 常見陷阱

- **Supabase 分頁**：預設 1000 筆上限，所有查詢必須用 `range()` 分頁（參考 `_fetch_paged()`）。
  分頁時務必加 `order()`：無排序的多次查詢，Postgres 不保證跨頁順序一致，會重複或遺漏。
- **FinMind 欄位名稱不一致**：各資料集用 `--discover` 模式驗證後再寫入（尤其現金流量表）
- **時區**：前端一律用 `Asia/Taipei`，Python 腳本用 `datetime.today()` 即台北時間
- **listed_shares 單位**：千股。每股數值一律為 `元 ÷ (listed_shares × 1000)`
- **現金流量表是「年度累計」**：台灣財報的現金流量表逐季累加、每年 Q1 重置
  （台積電 2025：0.63→1.12→1.55→2.27 兆）。算 TTM 前**必須先還原單季**
  （`calculate_alt_valuations.decumulate()`），直接加總會高估約 2.5 倍。
  **EPS 與損益表則是單季值**，不可一併處理——FinMind 兩者行為不同。
- **金融股財報格式不同**：金控／保險／證券期貨業的會計科目與一般業不同
  （無 `EquityAttributableToOwnersOfParent`、`CapitalStock`），
  交易所 OpenAPI 亦分行業別提供端點（`_ci` 一般業／`_fh` 金控／`_ins` 保險…）。
  只抓 `_ci` 會漏掉全部金控股。
- **P/FCF 負值**：FCF 為負時跳過（不納入百分位計算，也不顯示目標價）
- **Next.js 15 params**：`params` 是 `Promise<{code: string}>`，必須 `await params`
- **民國年一律先 +1911 轉西元** 再組日期。交易所 OpenAPI 的 `年度`/`Year` 是民國
  （115），直接組成 `f"{115}-03-31"` 會寫出公元 115 年的日期。
  屬「不得寫錯誤日期」原則的一環。**2026-07 事故**：`backfill_eps_from_income.py`
  漏轉，寫入 1121 筆 `0115-03-31` 髒資料。
- **交易所 OpenAPI 欄名 TWSE 中文、TPEx 英文**：TWSE 用 `年度`/`季別`/`公司代號`，
  TPEx（上櫃、興櫃）用 `Year`/`Season`/`SecuritiesCompanyCode`。只比對中文欄名，
  上櫃/興櫃會整批被跳過（884 家收 0 筆）。跨市場處理務必兩種欄名都取。
- **不可只查單一來源就斷定「補不了」**：金控 Q1 EPS 先誤判「FinMind 沒有 → 資料限制」，
  實際 TWSE 綜合損益表 OpenAPI 有官方基本每股盈餘。呼應「跨來源比對」原則。
