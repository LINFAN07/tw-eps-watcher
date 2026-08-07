// 由 scripts/audit_oos_persistence.py 產生，請勿手動編輯。重跑會覆寫此檔。
// persists = 三個切點的 Spearman 都 ≥ 0.3（切點 2021／2022／2023）。
// 手寫的措辭在 backtest.ts；那裡會比對本檔，不一致時退回保守警語。

export const OOS_PERSISTENCE = {
  pe: { persists: false, spearman: [0.08, 0.22, -0.04] },
  pb: { persists: false, spearman: [0.18, 0.24, 0.35] },
  ps: { persists: true, spearman: [0.41, 0.55, 0.55] },
  pfcf: { persists: false, spearman: [0.46, 0.24, -0.21] },
} as const
