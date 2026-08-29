import type { ShortSeekApi } from '../electron/preload'
import {
  DEFAULT_BLACKLIST,
  type BlacklistState,
  type PlatformId,
  type VideoResult,
  detectPlatform,
  isShortDuration,
} from './shared/types'

const STORAGE_KEY = 'short-seek-blacklist'

function readBrowserBlacklist(): BlacklistState {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return { ...DEFAULT_BLACKLIST }
    return { ...DEFAULT_BLACKLIST, ...(JSON.parse(raw) as Partial<BlacklistState>) }
  } catch {
    return { ...DEFAULT_BLACKLIST }
  }
}

function writeBrowserBlacklist(blacklist: BlacklistState) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(blacklist))
}

async function browserSearch(query: string): Promise<{ videos: VideoResult[]; errors: string[] }> {
  const response = await fetch(`/api/search?q=${encodeURIComponent(query)}`)
  if (!response.ok) {
    const text = await response.text()
    throw new Error(text || `Search failed (${response.status})`)
  }
  const data = (await response.json()) as { videos: VideoResult[]; errors: string[] }
  const blacklist = readBrowserBlacklist()
  return {
    videos: (data.videos || []).filter((video) => !blacklist[video.platform]),
    errors: data.errors || [],
  }
}

/** Browser fallback used when the Vite page is opened outside Electron. */
export const browserApi: ShortSeekApi = {
  searchVideos: browserSearch,
  getBlacklist: async () => readBrowserBlacklist(),
  setBlacklist: async (platform: PlatformId, blocked: boolean) => {
    const next = readBrowserBlacklist()
    next[platform] = blocked
    writeBrowserBlacklist(next)
    return next
  },
  setAllBlacklist: async (blacklist: BlacklistState) => {
    const next = { ...DEFAULT_BLACKLIST, ...blacklist }
    writeBrowserBlacklist(next)
    return next
  },
  openExternal: async (url: string) => {
    window.open(url, '_blank', 'noopener,noreferrer')
  },
}

export function getApi(): ShortSeekApi {
  return window.shortSeek ?? browserApi
}

export function normalizeVideo(raw: {
  id?: string
  title?: string
  url: string
  thumbnail?: string
  duration?: string
  platform?: PlatformId
  channel?: string
  source?: 'duckduckgo' | 'youtube'
  publishedOn?: string
}): VideoResult | null {
  if (!raw.url) return null
  if (raw.duration && !isShortDuration(raw.duration)) return null
  return {
    id: raw.id || raw.url,
    title: raw.title || 'Untitled video',
    url: raw.url,
    thumbnail: raw.thumbnail || '',
    duration: raw.duration || '',
    platform: raw.platform || detectPlatform(raw.url, raw.publishedOn),
    channel: raw.channel || 'Unknown',
    source: raw.source || 'duckduckgo',
  }
}
