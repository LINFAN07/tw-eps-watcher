'use client'
import { useWatchlist } from '@/hooks/useWatchlist'

export default function WatchlistButton({ code }: { code: string }) {
  const { toggle, isWatched } = useWatchlist()
  const watched = isWatched(code)

  return (
    <button
      onClick={() => toggle(code)}
      className={`text-sm px-3 py-1 rounded-full border transition-colors ${
        watched
          ? 'bg-yellow-50 border-yellow-300 text-yellow-700 hover:bg-yellow-100'
          : 'bg-gray-50 border-gray-200 text-gray-500 hover:bg-gray-100'
      }`}
    >
      {watched ? '★ 已加入自選' : '☆ 加入自選'}
    </button>
  )
}
