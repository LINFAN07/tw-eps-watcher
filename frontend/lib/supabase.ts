import { createClient, SupabaseClient } from '@supabase/supabase-js'

// 伺服器端專用（service_role key 絕對不能出現在瀏覽器）
// 模組層級 singleton，避免每次請求重複建立連線
let _client: SupabaseClient | null = null

export function getSupabase(): SupabaseClient {
  if (_client) return _client
  const url = process.env.SUPABASE_URL
  const key = process.env.SUPABASE_KEY
  // 啟動期即驗證，讓環境變數設錯能在第一次呼叫時立刻拋出明確錯誤
  if (!url || !key) throw new Error('缺少環境變數：SUPABASE_URL 或 SUPABASE_KEY 未設定')
  _client = createClient(url, key)
  return _client
}
