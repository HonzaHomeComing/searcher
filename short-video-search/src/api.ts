import type { ShortSeekApi } from '../electron/preload'
import {
  DEFAULT_BLACKLIST,
  type BlacklistState,
  type PlatformId,
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

async function browserSearch(query: string) {
  const response = await fetch(`/api/search?q=${encodeURIComponent(query)}`)
  if (!response.ok) {
    const text = await response.text()
    throw new Error(text || `Search failed (${response.status})`)
  }
  const data = (await response.json()) as Awaited<ReturnType<ShortSeekApi['searchVideos']>>
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
