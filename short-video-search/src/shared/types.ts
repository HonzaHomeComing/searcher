export type PlatformId =
  | 'youtube'
  | 'tiktok'
  | 'instagram'
  | 'facebook'
  | 'linkedin'
  | 'vimeo'
  | 'dailymotion'
  | 'other'

export interface PlatformInfo {
  id: PlatformId
  label: string
  domains: string[]
  color: string
}

export const PLATFORMS: PlatformInfo[] = [
  {
    id: 'youtube',
    label: 'YouTube',
    domains: ['youtube.com', 'youtu.be', 'm.youtube.com'],
    color: '#FF0000',
  },
  {
    id: 'tiktok',
    label: 'TikTok',
    domains: ['tiktok.com', 'vm.tiktok.com'],
    color: '#69C9D0',
  },
  {
    id: 'instagram',
    label: 'Instagram',
    domains: ['instagram.com'],
    color: '#E4405F',
  },
  {
    id: 'facebook',
    label: 'Facebook',
    domains: ['facebook.com', 'fb.watch', 'fb.com'],
    color: '#1877F2',
  },
  {
    id: 'linkedin',
    label: 'LinkedIn',
    domains: ['linkedin.com'],
    color: '#0A66C2',
  },
  {
    id: 'vimeo',
    label: 'Vimeo',
    domains: ['vimeo.com'],
    color: '#1AB7EA',
  },
  {
    id: 'dailymotion',
    label: 'Dailymotion',
    domains: ['dailymotion.com', 'dai.ly'],
    color: '#00AAFF',
  },
  {
    id: 'other',
    label: 'Other',
    domains: [],
    color: '#9AA0A6',
  },
]

export interface VideoResult {
  id: string
  title: string
  url: string
  thumbnail: string
  duration: string
  platform: PlatformId
  channel: string
  source: 'duckduckgo' | 'youtube'
}

export type BlacklistState = Record<PlatformId, boolean>

export const DEFAULT_BLACKLIST: BlacklistState = {
  youtube: false,
  tiktok: false,
  instagram: false,
  facebook: false,
  linkedin: false,
  vimeo: false,
  dailymotion: false,
  other: false,
}

export function detectPlatform(url: string, publishedOn?: string): PlatformId {
  try {
    const host = new URL(url).hostname.replace(/^www\./, '').toLowerCase()
    for (const platform of PLATFORMS) {
      if (platform.id === 'other') continue
      if (platform.domains.some((d) => host === d || host.endsWith(`.${d}`))) {
        return platform.id
      }
    }
  } catch {
    /* ignore */
  }

  const hint = (publishedOn || '').toLowerCase()
  for (const platform of PLATFORMS) {
    if (platform.id === 'other') continue
    if (hint.includes(platform.label.toLowerCase())) return platform.id
  }

  return 'other'
}

export function parseDurationSeconds(duration: string | undefined): number | null {
  if (!duration) return null
  const parts = duration
    .trim()
    .split(':')
    .map((p) => Number(p))
  if (parts.some((n) => Number.isNaN(n))) return null
  if (parts.length === 1) return parts[0]
  if (parts.length === 2) return parts[0] * 60 + parts[1]
  if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2]
  return null
}

/** Prefer short-form clips (under 3 minutes). */
export function isShortDuration(duration: string | undefined): boolean {
  const seconds = parseDurationSeconds(duration)
  if (seconds === null) return true
  return seconds > 0 && seconds <= 180
}
