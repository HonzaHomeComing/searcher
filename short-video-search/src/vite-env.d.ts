import type { ShortSeekApi } from '../electron/preload'

declare global {
  interface Window {
    shortSeek?: ShortSeekApi
  }
}

export {}
