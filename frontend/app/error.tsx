'use client'

// 首頁錯誤邊界：資料查詢故障時顯示明確錯誤與重試，而非靜默空白或整頁崩潰。
// 對應 CheapLeaderboard 等 Server Component 拋出的查詢錯誤——「故障」與「查無資料」
// 必須讓使用者看得出差別。錯誤邊界於請求時渲染、不進 ISR 快取，故每次請求都會重試。
export default function Error({ reset }: { error: Error; reset: () => void }) {
  return (
    <main className="max-w-4xl mx-auto px-4 py-16 text-center">
      <p className="text-gray-700 font-medium mb-2">資料暫時無法載入</p>
      <p className="text-gray-400 text-sm mb-6">來源服務可能短暫異常，請稍後重試。</p>
      <button
        onClick={reset}
        className="text-sm px-4 py-2 rounded-full bg-gray-800 text-white hover:bg-gray-700 transition-colors"
      >
        重試
      </button>
    </main>
  )
}
