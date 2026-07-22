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
# 台股的慣用面額。僅供「這家公司是不是非典型面額」的比較基準，
# 【不可】拿來當取不到面額時的替代值——那是把缺值變成數字（見 main 的 no_par）。
DEFAULT_PAR = 10.0

# 允許多少比例的股票因取不到面額而跳過。超過即視為來源異常並 exit 1：
# 正常只有已下市、剛掛牌等零星個案，整批取不到必是端點欄名變更。
MAX_NO_PAR_RATE = 0.15


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
    fin_capital_by_date: dict[str, float] = {}

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
        elif type_str == "CapitalStock":
            capital_by_date[date_str] = val
        # ⚠️ 不可改用 OrdinaryShare 當分母（2026-07-23 回退）
        #
        # 曾經改過：理由是 CapitalStock 含特別股，拿它當分母等於把特別股
        # 當普通股。用 1101 台泥驗證通過——OrdinaryShare 75,231,817,000
        # ÷ 10 ÷ 1000 ＝ 7,523,181 千股，與交易所公告的已發行普通股數分毫不差。
        #
        # 但那只證明了台泥。全量落地後比對前後值，943 檔的每股淨值變動 >0.5%，
        # 其中絕大多數面額是 10 元（面額根本不是原因）：
        #   6829 千附精密 CapitalStock 109,000,000 vs OrdinaryShare 1,000,000
        #   7769 鴻勁     CapitalStock 1,600,000,000 vs OrdinaryShare 469,538,000
        # 1.09 億股本的公司，普通股股本不可能只有 100 萬——FinMind 的
        # OrdinaryShare 欄位語意不一致，對不同公司代表不同東西。
        #
        # 特別股造成的偏差（台泥約 2.7%）遠小於這個欄位帶來的錯誤，
        # 故維持 CapitalStock。若日後要處理特別股，需要能明確辨識
        # 特別股金額的來源，而不是賭某個欄位的語意。
        #
        # 教訓：單一案例驗證通過，只證明那個案例。
        elif type_str == "TotalAssets":
            assets_by_date[date_str] = val
        elif type_str == "Liabilities":          # FinMind 欄位名稱（非 TotalLiabilities）
            liab_by_date[date_str] = val
        # ── 金控／保險／證券期貨業採用不同會計科目分類，
        #    沒有 EquityAttributableToOwnersOfParent，
        #    需改由「總權益 − 非控制權益」推算母公司權益。
        #    需改由「總權益 − 非控制權益」為母公司權益、以普通股股本為股本。
        elif type_str == "Equity":
            fin_equity_by_date[date_str] = val
        elif type_str == "NoncontrollingInterests":
            fin_nci_by_date[date_str] = val
        elif type_str == "OrdinaryShare":
            # 僅供金融業在缺 CapitalStock 時補位（下方 setdefault 保證不覆蓋一般業）。
            # 這個欄位的語意不可靠（見上方回退說明），故只當最後退路。
            fin_capital_by_date[date_str] = val

    # 金融業補位：一般業欄位缺漏時，以「總權益 − 非控制權益」為母公司權益。
    # setdefault 確保一般業既有值不被覆蓋。
    for date_str, fin_equity in fin_equity_by_date.items():
        parent_equity = fin_equity - fin_nci_by_date.get(date_str, 0.0)
        if parent_equity > 0:
            equity_by_date.setdefault(date_str, parent_equity)
        fin_cap = fin_capital_by_date.get(date_str)
        if fin_cap and fin_cap > 0:
            capital_by_date.setdefault(date_str, fin_cap)

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
            # 一併存下這一季用的面額。沒有它，事後分不出「淨值算錯」與
            # 「面額用錯」，也無法只重算面額變更後的季度（見 sql/patch_par_value_column.sql）
            "par_value":            par,
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
    no_par: list[str] = []
    for i, sid in enumerate(stock_ids, 1):
        par = pars.get(sid)
        if par is None:
            # 取不到面額就跳過，不用預設值頂替——BVPS = 面額 × 權益 / 股本，
            # 面額若是假設的，寫進去的淨值答不出「這是誰給的」（資料誠信第 3 條）。
            # 這不是理論風險：TPEx 端點只要改欄名或該欄留空，上櫃／興櫃就會整批
            # 落回預設值，而 KY 股（面額 1 元／0.5 元的主力）多在上櫃／興櫃——
            # 2026-07-22 那次事故會完整重演，且這次不會有任何跡象。
            no_par.append(sid)
            print(f"[{i}/{total}] {sid}: 跳過（取不到面額）")
            continue
        try:
            written = download_stock_bvps(sid, par, official_shares.get(sid))
        except fm.FinMindError as e:
            tracker.record(sid, e)
            written = 0
        label   = f"寫入 {written} 筆" if written > 0 else "無資料"
        print(f"[{i}/{total}] {sid}: {label}")
        written_total += written
        time.sleep(CALL_INTERVAL)

    print(f"\n✅ 完成，共寫入 {written_total} 筆每股淨值資料")
    if no_par:
        rate = len(no_par) / max(total, 1)
        print(f"⚠️  {len(no_par)} 支取不到面額而跳過（{rate:.1%}）：{no_par[:10]}")
        # 面額涵蓋率是「TPEx 欄名漂移」唯一看得見的訊號。正常只有已下市、
        # 剛掛牌等零星個案；一旦某個市場整批取不到，這個比例會暴增。
        if rate > MAX_NO_PAR_RATE:
            print(f"❌ 面額涵蓋率過低（跳過 {rate:.1%} > 門檻 {MAX_NO_PAR_RATE:.0%}），"
                  f"多半是交易所端點欄名變更——請先確認 fetch_par_values 再重跑")
            sys.exit(1)
    tracker.finish()   # 有任何抓取失敗就以 exit 1 結束，觸發通知


if __name__ == "__main__":
    main()
