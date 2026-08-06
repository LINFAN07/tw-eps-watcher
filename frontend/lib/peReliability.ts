// P/E 可靠性判斷（推薦模型與排行榜共用的單一真相來源）
//
// 權威來源是資料庫的生成欄位 valuations.pe_reliable（見 schema.sql）：
// DB 依 warning / nonop_warning 自動算出，無跨語言字串耦合、無需重算腳本。
//
// 何謂「P/E 失真」：
//   - warning 含「EPS 長期偏低」：獲利太小，P/E 倍數失去意義
//   - warning 含「顯著高於長期均值」：獲利高峰，TTM EPS 灌水使 P/E 假性偏低
//   - warning 含「遠低於常態水準」：目標價改由常態化 EPS 推算，等於賭獲利回到歷史水準。
//     回測顯示這類訊號 12 個月報酬中位數與隨機挑股相同（3.74% vs 3.65%），
//     獲利谷底那半更差（0.95%），故不列入推薦。
//   - nonop_warning：本業以外的一次性收益撐高 EPS
//   - pe_deep_discount：便宜價超過現價 3 倍。這通常不是跌得便宜，是歷史倍數
//     已經不適用了——公司基本面劇變，早年的高倍數對現在沒有參考價值。
//     回測（持有 12 個月，逐月中位數的中位。重跑：scripts/backtest_discount_bands.py）：
//
//       2026-08-06 重新校準（修 TTM 視窗後）  全期    >2021   >2022   >2023
//         折價 2~3 倍（151 檔獨立股票）       −2.51%  +2.56   +7.28   −9.86
//         折價 >3 倍 （ 40 檔獨立股票）       −6.30%  −4.99  −10.20  −12.21
//
//     門檻維持 3 倍：只有 >3 倍那一格在三個切點的後段都為負。2~3 倍組全期雖
//     為負，後段卻毫無型態，且切點換位置結論就翻面——不足以據此收緊門檻。
//     （舊註解記載的 +1.00% / −5.71% 是修 TTM 前的校準，已不適用。）
//     門檻 3 倍高於 P/B 的 2 倍（見 pb_reliable）：EPS 波動大，
//     2 倍折價還可能是景氣循環的谷底，淨值是存量、失真則是結構性的。
//     已知限制：這個效果集中在近年，早年的分段是正的——門檻建立在近期樣本上。
// 命中任一項，P/E 就不應被推薦為主模型，也不應據以進入便宜排行榜。
//
// 為什麼折價門檻獨立成一個欄位，而不併進 pe_reliable：
// pe_reliable 是既有生成欄位，加條件必須 DROP 後重建，期間排行榜與推薦
// 模型都查不到它、網站會短暫報錯。純新增零風險，代價只是判斷散在兩個欄位。

// 舊版字串比對——僅作為 pe_reliable 欄位尚未布署時的暫時退路（migration 完成後永不觸發）。
const PE_UNRELIABLE_WARNINGS = ['EPS 長期偏低', '顯著高於長期均值', '遠低於常態水準']

export function isPeUnreliable(v: {
  pe_reliable?: boolean | null
  pe_deep_discount?: boolean | null
  warning?: string | null
  nonop_warning?: string | null
}): boolean {
  // 折價過深：與 pe_reliable 各自獨立，任一命中即不可靠
  if (v.pe_deep_discount) return true
  // 權威：DB 生成欄位。存在即以它為準。
  if (v.pe_reliable != null) return !v.pe_reliable
  // 退路：欄位缺席（migration 未套用）時才用字串比對，避免部署順序造成破圖。
  if (v.nonop_warning) return true
  return PE_UNRELIABLE_WARNINGS.some(kw => (v.warning ?? '').includes(kw))
}
