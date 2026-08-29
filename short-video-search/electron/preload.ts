import { contextBridge, ipcRenderer } from 'electron'
import type { BlacklistState, PlatformId, VideoResult } from '../src/shared/types'

export interface SearchResponse {
  videos: VideoResult[]
  errors: string[]
}

const api = {
  searchVideos: (query: string): Promise<SearchResponse> =>
    ipcRenderer.invoke('search:videos', query),
  getBlacklist: (): Promise<BlacklistState> => ipcRenderer.invoke('blacklist:get'),
  setBlacklist: (platform: PlatformId, blocked: boolean): Promise<BlacklistState> =>
    ipcRenderer.invoke('blacklist:set', platform, blocked),
  setAllBlacklist: (blacklist: BlacklistState): Promise<BlacklistState> =>
    ipcRenderer.invoke('blacklist:set-all', blacklist),
  openExternal: (url: string): Promise<void> => ipcRenderer.invoke('open:external', url),
}

contextBridge.exposeInMainWorld('shortSeek', api)

export type ShortSeekApi = typeof api
