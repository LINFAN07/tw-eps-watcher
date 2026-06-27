'use client'
import { useState, useEffect, useCallback } from 'react'

const STORAGE_KEY = 'tw_watchlist'

export function useWatchlist() {
  const [codes, setCodes] = useState<string[]>([])

  // 初始化時從 localStorage 讀取（避免 SSR hydration 不一致）
  useEffect(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY)
      if (stored) setCodes(JSON.parse(stored))
    } catch {
      // localStorage 不可用時靜默略過
    }
  }, [])

  const toggle = useCallback((code: string) => {
    setCodes(prev => {
      const next = prev.includes(code)
        ? prev.filter(c => c !== code)
        : [...prev, code]
      try { localStorage.setItem(STORAGE_KEY, JSON.stringify(next)) } catch { }
      return next
    })
  }, [])

  const isWatched = useCallback((code: string) => codes.includes(code), [codes])

  return { codes, toggle, isWatched }
}
