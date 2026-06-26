import { createClient } from '@supabase/supabase-js'

// 伺服器端專用（service_role key 絕對不能出現在瀏覽器）
export function getSupabase() {
  return createClient(
    process.env.SUPABASE_URL!,
    process.env.SUPABASE_KEY!
  )
}
