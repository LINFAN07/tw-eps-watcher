# TODO — 台股估值查詢網站

## 已完成 ✅

### 資料庫

- [x] 在 Supabase 建立專案
- [x] 建立 `stocks` 資料表（股票名冊）
- [x] 建立 `eps_quarterly` 資料表（季度 EPS）
- [x] 建立 `daily_prices` 資料表（日收盤價）
- [x] 建立 `valuations` 資料表（預算估值結果）

### 初始資料下載

- [x] 從 FinMind 下載全市場股票名冊
- [x] 下載近 10 年歷史 EPS
- [x] 下載近 10 年歷史股價
- [x] 納入興櫃股票（透過 TPEX ESB API，約 354 檔）
- [x] 清除下市、停牌股票（移除 198 檔）

### 估值計算

- [x] 計算每檔股票的 TTM EPS
- [x] 計算歷史 P/E 分布（20/50/80 百分位數）
- [x] 產生便宜價 / 合理價 / 昂貴價
- [x] 判斷目前狀態並寫入 `valuations` 表
- [x] 計算 5 年標準化 EPS（`compute_normalized_eps`），避免極端 EPS 扭曲估值
- [x] 對上市 / 上櫃 / 興櫃三類股票完成批次估值

### 異常值偵測警告系統

- [x] **低 EPS 警告**（`patch_low_eps_warning.py`）：TTM EPS 遠低於標準化 EPS 時，標記估值可能過高
- [x] **獲利高峰警告**（`patch_peak_eps_warning.py`）：TTM EPS 遠高於歷史均值時，標記目前股價可能受益於高峰獲利
- [x] 批次回填 585 檔股票的警告欄位
- [x] 一次性收益偵測（IQR 異常值法），標記非經常性暴利季度

### 前端網站

- [x] 建立 Next.js 專案
- [x] 實作搜尋框（支援股票代碼與公司名稱）
- [x] 實作估值狀態卡片（便宜 / 合理 / 昂貴），含警告旗標
- [x] 實作 P/E 河流圖（股價走勢 + 三條估值帶），支援 Recharts 3.x
- [x] 便宜股排行榜（過濾零股價、過濾有警告標記的股票）
- [x] ValuationCard 對虧損股顯示「標準化 EPS 計算」的目前本益比
- [x] 部署到 Vercel

### 自動化排程

- [x] `daily_price_update.py`：每日收盤後透過 TWSE OpenAPI + TPEX ESB API 更新股價
- [x] 兩層架構：每日快速更新 + 每季重算估值
- [x] 設定 GitHub Actions 排程

---

## 待辦 📋

### 資料品質

- [x] 調查興櫃股票的 EPS 缺漏情況（ESB API 僅提供股價，EPS 仍需 FinMind）
  - **結論**：FinMind **有**興櫃股 EPS，但頻率為**半年報**（6/30、12/31），而非季報（3/31、6/30、9/30、12/31）。原本 `rolling(4)` 會將 2 年資料誤算為 TTM，已修正為自動偵測半年報並改用 `rolling(2)`（`_eps_window()` helper）。上市/上櫃季報不受影響。
- [x] 確認季度 EPS 更新排程在財報季正確觸發
  - **發現並修復 Bug**：Q3 申報期為 10/1～11/14，但原 cron `0 7 1-14 10 1-5` 只跑 10/1～10/14，漏掉 10/15～10/31（17天）。已修正為 `0 7 * 10 1-5`（整個10月均執行）。Q1/Q2/Q4 排程驗證正確無誤。

### 公司品質指標

- [x] **ROE（股東報酬率）**：TTM EPS ÷ 每股淨值，直接在 ValuationCard 底部顯示（≥15% 綠色優質、8–15% 橘色普通、<8% 紅色偏低）
- [x] **負債比**：從 FinMind `TaiwanStockBalanceSheet` 下載 `TotalAssets` + `Liabilities`，計算後顯示於品質指標列（金融業閾值不同）
- [x] **營業利益率**：`income_statement_quarterly.operating_income` ÷ TTM 月營收，1471 支股票已計算完成，寫入 `valuations.operating_margin`

### 估值模型改善

- [x] 評估是否需要針對銀行 / 金融股採用不同估值方法（本淨比而非本益比）→ 已實作產業自動推薦邏輯
- [x] 長期：考慮加入殖利率估值帶（股息殖利率河流圖）
  - **實作**：殖利率百分位（20/50/80）存入 `valuations` 表，ValuationCard 新增「殖利率」第五個 Tab，顯示便宜/合理/昂貴價與對應殖利率門檻
- [x] **業外收支偵測（賣祖產警告）**：下載損益表 `TaiwanStockFinancialStatements`，比對「營業利益」vs「稅後淨利」。若（稅後淨利 − 營業利益）/ 稅後淨利 > 30%，寫入 `valuations.nonop_warning`；前端顯示橘色警告橫幅，P/E 排行榜自動排除（309 支股票受影響）

### 前端改善

- [x] ValuationCard 顯示哪幾季 EPS 組成 TTM（讓使用者看懂來源）
- [x] 排行榜加入篩選條件（產業別）
- [x] 行動裝置版面優化

### 維運

- [ ] 監控排程失敗的通知機制（Email 或 Telegram）
- [ ] 定期驗證估值計算結果是否合理（抽樣比對）

---

## 功能規劃 🗺️

### 短期（現有資料庫即可實作）

- [x] **TTM 季度明細**：ValuationCard 顯示組成 TTM 的 4 季 EPS 明細（代碼：Q1/25 等）
- [x] **EPS 趨勢標記**：比對近一年 TTM vs 前一年 TTM，顯示「↑ 年增 X%」或「↓ 年減 X%」
- [x] **自選股清單（Watchlist）**：用 localStorage 儲存追蹤股票，首頁顯示自選股估值狀態

### 中期（需小量新資料或計算）

- [x] **市場溫度計**：統計全市場便宜/合理/昂貴股比例，顯示市場溫度與中位數 P/E
- [x] **殖利率河流圖**：殖利率百分位估值帶，適合配息股評估（需先執行 download_dividends.py）
- [x] **產業別排行榜**：在現有便宜股排行榜加上產業篩選（半導體、金融、傳產等）

### 長期（影響力大，實作較複雜）

- [ ] **到價通知**：使用者設定目標價，跌入便宜區間時寄送 Email 或 Telegram 通知
- [ ] **金融股 P/B 估值**：已移至下方「替代估值模型 > P/B」區塊統一規劃

---

## 替代估值模型 📐

> 當 P/E 模型不適用（TTM EPS ≤ 0.5 且長期均值也偏低）時，依企業型態切換的備用估值框架。
> 資料來源均為 FinMind，無需額外付費。

### P/B 股價淨值比（優先實作）

- [x] **資料下載**：`scripts/download_balance_sheet.py`，從 FinMind `TaiwanStockBalanceSheet` 抓取每股淨值
- [x] **估值計算**：`scripts/calculate_alt_valuations.py`，計算歷史 P/B 20/50/80 百分位
- [x] **ValuationCard 顯示**：P/B 便宜/合理/昂貴價與目前 P/B 狀態顯示於估值卡片
- [x] **P/B 河流圖**：`/api/chart/pb/[code]` + `AltRiverChart` 元件，在詳情頁顯示 P/B 帶狀圖
- [x] **適用對象標記**：資產型公司（地產、金融、傳產）優先顯示 P/B，其他股票作為補充參考

### P/S 股價營收比

- [x] **資料下載**：`scripts/download_monthly_revenue.py`，抓取月營收 + 更新流通股數
- [x] **估值計算**：`scripts/calculate_alt_valuations.py`，計算 TTM 每股營收與 P/S 歷史百分位
- [x] **ValuationCard 顯示**：P/S 便宜/合理/昂貴價顯示於估值卡片
- [x] **P/S 河流圖**：`/api/chart/ps/[code]` + `AltRiverChart` 元件，在詳情頁顯示 P/S 帶狀圖
- [x] **適用對象標記**：有營收但長期虧損的成長股、新創類股

### P/FCF 自由現金流比

- [x] **資料下載**：`scripts/download_cash_flows.py`，抓取營業現金流與資本支出
- [x] **估值計算**：`scripts/calculate_alt_valuations.py`，計算 TTM FCF per share 與 P/FCF 百分位
- [x] **ValuationCard 顯示**：P/FCF 便宜/合理/昂貴價顯示於估值卡片
- [x] **P/FCF 河流圖**：`/api/chart/pfcf/[code]` + `AltRiverChart` 元件，TTM FCF per share 滾動計算，詳情頁顯示 P/FCF 帶狀圖

### 估值模型整合

- [x] **模型選擇器**：股票詳情頁提供切換標籤（P/E / P/B / P/S / P/FCF），依產業自動推薦，支援手動切換
- [x] **排行榜擴充**：便宜股排行榜新增 P/E / P/B / P/S / P/FCF 四模型 Tab，各顯示對應便宜股與數量
- [x] **模型標注**：ValuationCard 顯示各模型名稱（P/B、P/S、P/FCF）與計算基準，避免誤解

---

## 排行榜數字陷阱防護 🛡️

> 目標：讓使用者即使關掉品質篩選，仍能一眼識別陷阱股，不誤判「折價大 = 低估」。

### 優先度 1 — 虧損股行背景標紅

- [x] 排行榜列表中，偵測「利益率 < 0 或 ROE < 0」的股票，整行顯示淡紅背景（`bg-red-50`）
- [x] 搭配小字提示「⚠️ 目前虧損，歷史估值帶可能失真」，防止使用者接刀

### 優先度 2 — 潛力黑馬徽章

- [x] 在排行榜公司名旁，對「利益率 ≥ 10% 但 ROE < 15%」且股價便宜的股票，加上 `🔍 潛力黑馬` 徽章
- [x] 滑鼠 hover 顯示提示文案：「本業獲利強勁，但資金效率尚未完全釋放（帳上現金充沛或處於擴產期）。一旦提高配息或產能放量，ROE 有望爆發。屬進階型潛在價值股，需留意等待時間成本。」

### 優先度 3 — KY 股警示標籤

- [x] 偵測股票代號後綴含 `-KY`（或公司名稱含 `-KY`），在公司名旁顯示 `⚠️ KY` 橘色標籤
- [x] 若同時符合「利益率高但 ROE 偏低」（即符合潛力黑馬條件），加強提示：「KY 股帳上現金難以驗證，請留意海外資產真實性」

### 優先度 4 — 頂級優質徽章

- [x] 對「ROE ≥ 15% 且利益率 ≥ 10%」的股票，在排行榜加上 `⭐ 頂級優質` 綠色徽章
- [x] 多模型共識 Tab 中的頂級優質股額外置頂顯示





 