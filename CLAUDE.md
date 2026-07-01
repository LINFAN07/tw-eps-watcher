# CLAUDE.md — 台股估值查詢網站

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
| `monthly_revenue` | 月營收千元（P/S 用） | `(stock_id, year_month)` |
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
- **排程**：GitHub Actions
  - 每日收盤後：`daily_price_update.py`
  - 財報季：`quarterly_eps_update.py`
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

- **Supabase 分頁**：預設 1000 筆上限，所有查詢必須用 `range()` 分頁（參考 `_fetch_paged()`）
- **FinMind 欄位名稱不一致**：各資料集用 `--discover` 模式驗證後再寫入（尤其現金流量表）
- **時區**：前端一律用 `Asia/Taipei`，Python 腳本用 `datetime.today()` 即台北時間
- **listed_shares 單位**：千股（和 monthly_revenue 的千元單位抵消，得到元/股）
- **P/FCF 負值**：FCF 為負時跳過（不納入百分位計算，也不顯示目標價）
- **Next.js 15 params**：`params` 是 `Promise<{code: string}>`，必須 `await params`
