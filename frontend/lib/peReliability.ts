// P/E 可靠性判斷（推薦模型與排行榜共用的單一真相來源）
//
// 權威來源是資料庫的生成欄位 valuations.pe_reliable（見 schema.sql）：
// DB 依 warning / nonop_warning 自動算出，無跨語言字串耦合、無需重算腳本。
//
// 何謂「P/E 失真」：
//   - warning 含「EPS 長期偏低」：獲利太小，P/E 倍數失去意義
//   - warning 含「顯著高於長期均值」：獲利高峰，TTM EPS 灌水使 P/E 假性偏低
//   - nonop_warning：本業以外的一次性收益撐高 EPS
// 命中任一項，P/E 就不應被推薦為主模型，也不應據以進入便宜排行榜。

// 舊版字串比對——僅作為 pe_reliable 欄位尚未布署時的暫時退路（migration 完成後永不觸發）。
const PE_UNRELIABLE_WARNINGS = ['EPS 長期偏低', '顯著高於長期均值']

export function isPeUnreliable(v: {
  pe_reliable?: boolean | null
  warning?: string | null
  nonop_warning?: string | null
}): boolean {
  // 權威：DB 生成欄位。存在即以它為準。
  if (v.pe_reliable != null) return !v.pe_reliable
  // 退路：欄位缺席（migration 未套用）時才用字串比對，避免部署順序造成破圖。
  if (v.nonop_warning) return true
  return PE_UNRELIABLE_WARNINGS.some(kw => (v.warning ?? '').includes(kw))
}
