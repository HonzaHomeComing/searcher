import { useEffect, useMemo, useRef, useState, useTransition } from 'react'
import { getApi } from './api'
import { BlacklistPanel } from './components/BlacklistPanel'
import { SearchBar } from './components/SearchBar'
import { VideoGrid } from './components/VideoGrid'
import {
  DEFAULT_BLACKLIST,
  PLATFORMS,
  type BlacklistState,
  type VideoResult,
} from './shared/types'
import './App.css'

function App() {
  const api = useMemo(() => getApi(), [])
  const [query, setQuery] = useState('')
  const [videos, setVideos] = useState<VideoResult[]>([])
  const [errors, setErrors] = useState<string[]>([])
  const [blacklist, setBlacklist] = useState<BlacklistState>(DEFAULT_BLACKLIST)
  const [panelOpen, setPanelOpen] = useState(false)
  const [hasSearched, setHasSearched] = useState(false)
  const [isPending, startTransition] = useTransition()
  const [loading, setLoading] = useState(false)
  const requestId = useRef(0)

  useEffect(() => {
    let cancelled = false
    api.getBlacklist().then((state) => {
      if (!cancelled) setBlacklist(state)
    })
    return () => {
      cancelled = true
    }
  }, [api])

  const blockedCount = useMemo(
    () => Object.values(blacklist).filter(Boolean).length,
    [blacklist],
  )

  const visibleVideos = useMemo(
    () => videos.filter((video) => !blacklist[video.platform]),
    [videos, blacklist],
  )

  async function runSearch(nextQuery: string) {
    const trimmed = nextQuery.trim()
    if (!trimmed) return

    const id = ++requestId.current
    setLoading(true)
    setHasSearched(true)
    setErrors([])

    try {
      const result = await api.searchVideos(trimmed)
      if (id !== requestId.current) return
      startTransition(() => {
        setVideos(result.videos)
        setErrors(result.errors)
      })
    } catch (error) {
      if (id !== requestId.current) return
      setVideos([])
      setErrors([error instanceof Error ? error.message : 'Search failed'])
    } finally {
      if (id === requestId.current) setLoading(false)
    }
  }

  async function togglePlatform(platformId: (typeof PLATFORMS)[number]['id']) {
    const nextBlocked = !blacklist[platformId]
    const next = await api.setBlacklist(platformId, nextBlocked)
    setBlacklist(next)
  }

  return (
    <div className="app-shell">
      <div className="ambient ambient-a" aria-hidden />
      <div className="ambient ambient-b" aria-hidden />

      <header className="top-bar">
        <div className="brand-lockup">
          <span className="brand-mark" aria-hidden>
            ▶
          </span>
          <div>
            <p className="brand-name">Short Seek</p>
            <p className="brand-tag">Short videos from across the web</p>
          </div>
        </div>

        <button
          type="button"
          className={`sources-btn ${panelOpen ? 'active' : ''}`}
          onClick={() => setPanelOpen((open) => !open)}
        >
          Sources
          {blockedCount > 0 ? <span className="badge">{blockedCount}</span> : null}
        </button>
      </header>

      <main className="main-stage">
        <SearchBar
          value={query}
          loading={loading || isPending}
          onChange={setQuery}
          onSubmit={() => runSearch(query)}
        />

        <BlacklistPanel
          open={panelOpen}
          blacklist={blacklist}
          onToggle={togglePlatform}
          onClose={() => setPanelOpen(false)}
        />

        {loading ? (
          <div className="status-line" role="status">
            Searching short videos…
          </div>
        ) : null}

        {!loading && hasSearched && visibleVideos.length === 0 ? (
          <div className="empty-state">
            <h2>No short videos found</h2>
            <p>
              Try another keyword, or turn off a blacklist toggle in Sources so more sites
              can appear.
            </p>
          </div>
        ) : null}

        {!hasSearched && !loading ? (
          <div className="empty-state intro">
            <h2>Search short-form video</h2>
            <p>
              Type a keyword to pull vertical clips from YouTube, TikTok, Instagram, and
              more. Use Sources to blacklist sites with a toggle.
            </p>
          </div>
        ) : null}

        <VideoGrid videos={visibleVideos} api={api} />

        {errors.length > 0 ? (
          <p className="soft-errors">
            Some sources were unavailable: {errors.join(' · ')}
          </p>
        ) : null}
      </main>
    </div>
  )
}

export default App
