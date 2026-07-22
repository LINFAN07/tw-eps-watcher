"""
資產負債表下載腳本（P/B 估值原始資料）
從 FinMind TaiwanStockBalanceSheet 下載每股淨值（BookValuePerShare），
寫入 Supabase balance_sheet_quarterly 表。

執行前請先在 Supabase SQL Editor 執行 schema.sql 中的替代估值模型擴充語句。

用法：
  python scripts/download_balance_sheet.py            # 全量下載
  python scripts/download_balance_sheet.py --skip-file done.txt   # 斷點續傳
  python scripts/download_balance_sheet.py --discover # 印出欄位類型後退出（驗證用）
"""

import os
import re
import sys
import time
from datetime import datetime, timedelta
from dotenv import load_dotenv
import requests
from supabase import create_client
import finmind_client as fm

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

FINMIND_TOKEN = os.getenv("FINMIND_TOKEN")
SUPABASE_URL  = os.getenv("SUPABASE_URL")
SUPABASE_KEY  = os.getenv("SUPABASE_KEY")
FINMIND_API   = "https://api.finmindtrade.com/api/v4/data"
START_DATE    = (datetime.today() - timedelta(days=365 * 10)).strftime("%Y-%m-%d")
CALL_INTERVAL = 6.5  # FinMind 免費版速率限制（秒）

# FinMind 沒有直接的 BookValuePerShare 欄位
# 用 EquityAttributableToOwnersOfParent（母公司股東權益, 元）
# 和 CapitalStock（股本, 元）計算：
#   股數 = 股本 / 面額     →     BVPS = 面額 × 股東權益 / 股本
#
# 面額不可假設為 10 元。台灣多數股票面額 10 元，但 KY 股與部分公司不是
# （4763 材料-KY 為 1 元、6919 康霈 0.5 元、6531 愛普 5 元）。
# 2026-07-22 事故：原本硬編面額 10，1,079 檔上市公司有 253 檔（23%）
# 每股淨值與交易所官方申報值不符，比值恰為面額比（0.1／0.05／0.5）。
# 連帶 shares_thousand 與 listed_shares 一起錯，污染 P/B、P/S、P/FCF
# 與股數還原因子——4763 的 P/B 合理價因此高估 22 倍（現價 50.3 → 1,129.78）。
# 面額改由交易所公司基本資料取得（見 fetch_par_values）。

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# 公司基本資料，三市場各一個整批端點（秒級，含面額與官方已發行股數）
PROFILE_ENDPOINTS = [
    ("上市", "https://openapi.twse.com.tw/v1/opendata/t187ap03_L", True),
    ("上櫃", "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O", False),
    ("興櫃", "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_R", False),
]
DEFAULT_PAR = 10.0


def _num(text: str) -> float | None:
    """從「新台幣                 10.0000元」這類字串取出數字"""
    m = re.search(r"(\d+(?:\.\d+)?)", str(text or "").replace(",", ""))
    return float(m.group(1)) if m else None


def fetch_par_values() -> tuple[dict[str, float], dict[str, int]]:
    """
    向交易所取得每支股票的普通股面額與官方已發行股數。

    回傳 ({股票代號: 面額}, {股票代號: 已發行股數（千股）})。
    官方股數優先於「股本 ÷ 面額」的推算值——推算會受特別股、庫藏股影響。
    任一端點失敗即拋例外：面額拿不到就整批算錯，不可用預設值蒙混過去。
    """
    pars: dict[str, float] = {}
    shares: dict[str, int] = {}
    for label, url, verify in PROFILE_ENDPOINTS:
        resp = requests.get(url, timeout=60, verify=verify)
        rows = resp.json()
        if not isinstance(rows, list) or not rows:
            raise RuntimeError(f"{label}公司基本資料回應異常：{url}")
        for r in rows:
            sid = (r.get("公司代號") or r.get("SecuritiesCompanyCode") or "").strip()
            par = _num(r.get("普通股每股面額") or r.get("ParValueOfCommonStock"))
            issued = _num(r.get("已發行普通股數或TDR原股發行股數") or r.get("IssueShares"))
            if not sid:
                continue
            if par and par > 0:
                pars[sid] = par
            if issued and issued > 0:
                shares[sid] = int(issued / 1000)      # 股 → 千股
        print(f"  {label}：{len(rows)} 家")
    print(f"  面額 {len(pars)} 家、官方股數 {len(shares)} 家；"
          f"非 10 元面額 {sum(1 for v in pars.values() if v != DEFAULT_PAR)} 家")
    return pars, shares


def finmind_get(dataset: str, stock_id: str | None, start_date: str | None) -> list:
    """委派給共用客戶端：抓取失敗會拋 FinMindError，不以空清單掩蓋故障"""
    return fm.fetch(dataset, stock_id, start_date, FINMIND_TOKEN)


def fetch_all_stock_ids() -> list[str]:
    all_ids: list[str] = []
    offset = 0
    while True:
        resp = supabase.table("stocks").select("stock_id").range(offset, offset + 999).execute()
        batch = [r["stock_id"] for r in (resp.data or [])]
        all_ids.extend(batch)
        if len(batch) < 1000:
            break
        offset += 1000
    return all_ids


def download_stock_bvps(stock_id: str, par: float, official_shares: int | None = None) -> int:
    """下載單支股票的每股淨值與負債比，回傳寫入筆數

    同一次 API 呼叫同時計算：
      BVPS = 10 × EquityAttributableToOwnersOfParent / CapitalStock
      負債比 = TotalLiabilities / TotalAssets × 100
    """
    raw = finmind_get("TaiwanStockBalanceSheet", stock_id, START_DATE)
    if not raw:
        return 0

    # 依日期收集所需欄位
    equity_by_date:  dict[str, float] = {}
    capital_by_date: dict[str, float] = {}
    assets_by_date:  dict[str, float] = {}
    liab_by_date:    dict[str, float] = {}
    # 金融業專用（欄位分類與一般業不同）
    fin_equity_by_date:  dict[str, float] = {}
    fin_nci_by_date:     dict[str, float] = {}

    for r in raw:
        date_str = r.get("date", "").strip()
        type_str = r.get("type", "")
        value    = r.get("value")
        if not date_str or value is None:
            continue
        try:
            val = float(value)
        except (TypeError, ValueError):
            continue
        if type_str == "EquityAttributableToOwnersOfParent":
            equity_by_date[date_str] = val
        elif type_str == "OrdinaryShare":
            # 普通股股本。優先於 CapitalStock（總股本，含特別股）——
            # 拿總股本當分母等於把特別股當普通股，會稀釋每股淨值。
            # 驗證：1101 台泥 OrdinaryShare 75,231,817,000 ÷ 面額 10 ÷ 1000
            # ＝ 7,523,181 千股，與交易所公告的已發行普通股數分毫不差；
            # 用 CapitalStock 則得 7,723,181 千股（多算了 20 億元特別股）。
            capital_by_date[date_str] = val
        elif type_str == "CapitalStock":
            # 只在沒有 OrdinaryShare 時退而求其次（多數公司兩者相同）
            capital_by_date.setdefault(date_str, val)
        elif type_str == "TotalAssets":
            assets_by_date[date_str] = val
        elif type_str == "Liabilities":          # FinMind 欄位名稱（非 TotalLiabilities）
            liab_by_date[date_str] = val
        # ── 金控／保險／證券期貨業採用不同會計科目分類，
        #    沒有 EquityAttributableToOwnersOfParent，
        #    需改由「總權益 − 非控制權益」推算母公司權益。
        #    股本不必另行補位——上面的 OrdinaryShare 分支金融業同樣適用。
        elif type_str == "Equity":
            fin_equity_by_date[date_str] = val
        elif type_str == "NoncontrollingInterests":
            fin_nci_by_date[date_str] = val

    # 金融業補位：一般業欄位缺漏時，以「總權益 − 非控制權益」為母公司權益。
    # setdefault 確保一般業既有值不被覆蓋。
    for date_str, fin_equity in fin_equity_by_date.items():
        parent_equity = fin_equity - fin_nci_by_date.get(date_str, 0.0)
        if parent_equity > 0:
            equity_by_date.setdefault(date_str, parent_equity)

    rows = []
    for date_str, equity in equity_by_date.items():
        capital = capital_by_date.get(date_str)
        if not capital or capital <= 0:
            continue
        bvps = par * equity / capital
        if bvps <= 0:
            continue

        # 計算負債比（同季有資料才填，否則留 None）
        total_assets = assets_by_date.get(date_str)
        total_liab   = liab_by_date.get(date_str)
        debt_ratio = None
        if total_assets and total_assets > 0 and total_liab is not None:
            debt_ratio = round(total_liab / total_assets * 100, 2)

        # 逐季流通股數（千股）= 股本元 / 面額 / 1000。
        # 保存歷史股本，供 patch_capital_change_warning.py 偵測減資/增資；
        # 過去只留最新一筆到 stocks.listed_shares，歷史全被丟棄。
        shares_thousand = int(capital / par / 1000)

        rows.append({
            "stock_id":             stock_id,
            "quarter_end_date":     date_str,
            "book_value_per_share": round(bvps, 4),
            "debt_ratio":           debt_ratio,
            "shares_thousand":      shares_thousand if shares_thousand > 0 else None,
        })

    if not rows:
        return 0

    # 更新 stocks.listed_shares（千股）。優先用交易所公告的已發行普通股數，
    # 它排除了庫藏股與特別股；「股本 ÷ 面額」只是取不到官方值時的退路。
    if official_shares or capital_by_date:
        listed_shares = official_shares or int(
            capital_by_date[max(capital_by_date.keys())] / par / 1000)
        if listed_shares > 0:
            for attempt in range(3):
                try:
                    supabase.table("stocks").update({"listed_shares": listed_shares}).eq("stock_id", stock_id).execute()
                    break
                except Exception as e:
                    if attempt < 2:
                        time.sleep(5)
                    else:
                        print(f"  ⚠️  listed_shares 更新失敗: {e}")

    # 加入重試，避免 Supabase 瞬斷導致整支腳本崩潰
    for attempt in range(3):
        try:
            supabase.table("balance_sheet_quarterly").upsert(
                rows, on_conflict="stock_id,quarter_end_date"
            ).execute()
            return len(rows)
        except Exception as e:
            if attempt < 2:
                print(f"  ⚠️  Supabase 寫入失敗（第 {attempt + 1} 次），10 秒後重試: {e}")
                time.sleep(10)
            else:
                print(f"  ❌  Supabase 寫入失敗（已重試 3 次），跳過: {e}")
                return 0


def main():
    import argparse
    parser = argparse.ArgumentParser(description="下載台股每股淨值（P/B 估值原始資料）")
    parser.add_argument("--skip-file", help="已處理股票代碼清單（每行一個），跳過這些股票")
    parser.add_argument("--discover", action="store_true",
                        help="用 2330 試跑，印出所有可用 type 欄位後退出（用來驗證欄位名稱）")
    args = parser.parse_args()

    if args.discover:
        raw = finmind_get("TaiwanStockBalanceSheet", "2330", "2024-01-01")
        types = sorted({r["type"] for r in raw if "type" in r})
        print(f"TaiwanStockBalanceSheet 可用的 type 值（共 {len(types)} 種）：")
        for t in types:
            sample = next((r["value"] for r in raw if r.get("type") == t), "—")
            print(f"  {t}: {sample}")
        return

    skip: set[str] = set()
    if args.skip_file:
        with open(args.skip_file, encoding="utf-8") as f:
            skip = {line.strip() for line in f if line.strip()}
        print(f"跳過清單：{len(skip)} 支已處理股票")

    print("取得各股面額（每股淨值與股數的換算基準）…")
    pars, official_shares = fetch_par_values()

    all_ids    = fetch_all_stock_ids()
    stock_ids  = [s for s in all_ids if s not in skip]
    total      = len(stock_ids)
    print(f"開始下載資產負債表（每股淨值），共 {total} 支股票，起始日 {START_DATE}")

    tracker = fm.FailureTracker("資產負債表下載")
    written_total = 0
    for i, sid in enumerate(stock_ids, 1):
        try:
            # 取不到面額者（多為已下市，交易所名單已無該公司）沿用 10 元。
            # 這是退路不是猜測：面額非 10 元的公司佔比低，且下市股不進排行榜。
            written = download_stock_bvps(sid, pars.get(sid, DEFAULT_PAR),
                                          official_shares.get(sid))
        except fm.FinMindError as e:
            tracker.record(sid, e)
            written = 0
        label   = f"寫入 {written} 筆" if written > 0 else "無資料"
        print(f"[{i}/{total}] {sid}: {label}")
        written_total += written
        time.sleep(CALL_INTERVAL)

    print(f"\n✅ 完成，共寫入 {written_total} 筆每股淨值資料")
    tracker.finish()   # 有任何抓取失敗就以 exit 1 結束，觸發通知


if __name__ == "__main__":
    main()
