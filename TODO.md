# TODO — 台股估值查詢網站

## 第一步：建立資料庫
- [ ] 在 Supabase 建立專案
- [ ] 建立 `stocks` 資料表（股票名冊）
- [ ] 建立 `eps_quarterly` 資料表（季度 EPS）
- [ ] 建立 `daily_prices` 資料表（日收盤價）
- [ ] 建立 `valuations` 資料表（預算估值結果）

## 第二步：初始資料下載（一次性）
- [ ] 撰寫 `init_download.py`：從 FinMind 下載全市場股票名冊
- [ ] 撰寫 `init_download.py`：下載近 10 年歷史 EPS（約 3 小時）
- [ ] 撰寫 `init_download.py`：下載近 10 年歷史股價（約 3 小時）
- [ ] 執行初始下載，確認資料寫入 Supabase

## 第三步：估值計算
- [ ] 撰寫 `calculate_valuation.py`：計算每檔股票的 TTM EPS
- [ ] 撰寫 `calculate_valuation.py`：計算歷史 P/E 分布（20/50/80 百分位數）
- [ ] 撰寫 `calculate_valuation.py`：產生便宜價 / 合理價 / 昂貴價
- [ ] 撰寫 `calculate_valuation.py`：判斷目前狀態並寫入 `valuations` 表
- [ ] 對已知股票（如 2330）手動驗證計算結果是否合理

## 第四步：前端網站
- [ ] 建立專案（Next.js 或純 HTML）
- [ ] 實作搜尋框（支援股票代碼與公司名稱）
- [ ] 實作估值狀態卡片（便宜 / 合理 / 昂貴）
- [ ] 實作 P/E 河流圖（股價走勢 + 三條估值帶）
- [ ] 部署到 Vercel

## 第五步：自動化排程（GitHub Actions）
- [ ] 撰寫 `daily_price_update.py`：每日收盤後透過 TWSE OpenAPI 更新股價
- [ ] 撰寫 `quarterly_eps_update.py`：財報季期間偵測並更新 EPS
- [ ] 設定 `.github/workflows/daily_update.yml`（每日排程）
- [ ] 設定 `.github/workflows/quarterly_eps.yml`（財報季排程）
- [ ] 設定 GitHub Secrets（FINMIND_TOKEN、SUPABASE_KEY）
- [ ] 驗證排程正常運作

## 已完成
- [x] 系統架構規劃
- [x] 資料表設計
- [x] 估值方法確認（P/E 河流圖）


自動將估值便宜的股價列出
顯示個股的領域等、 最後更新時間