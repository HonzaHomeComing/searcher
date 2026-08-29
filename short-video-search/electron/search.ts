import { SafeSearchType, search, searchVideos } from 'duck-duck-scrape'
import { Innertube } from 'youtubei.js'
import {
  type BlacklistState,
  type PlatformId,
  type VideoResult,
  detectPlatform,
  isShortDuration,
} from '../src/shared/types'

const PLATFORM_SITE_QUERIES: Partial<Record<PlatformId, string>> = {
  tiktok: 'site:tiktok.com/video',
  instagram: 'site:instagram.com/reel',
  facebook: 'site:facebook.com/reel OR site:fb.watch',
  linkedin: 'site:linkedin.com',
  vimeo: 'site:vimeo.com',
  dailymotion: 'site:dailymotion.com',
}

let youtubeClient: Innertube | null = null

async function getYouTube(): Promise<Innertube> {
  if (!youtubeClient) {
    youtubeClient = await Innertube.create()
  }
  return youtubeClient
}

function makeId(url: string, title: string): string {
  return Buffer.from(`${url}::${title}`).toString('base64url').slice(0, 32)
}

function dedupe(videos: VideoResult[]): VideoResult[] {
  const seen = new Set<string>()
  const out: VideoResult[] = []
  for (const video of videos) {
    const key = video.url.replace(/[?#].*$/, '').toLowerCase()
    if (seen.has(key)) continue
    seen.add(key)
    out.push(video)
  }
  return out
}

async function searchDuckDuckGoVideos(query: string): Promise<VideoResult[]> {
  const response = await searchVideos(`${query} shorts`, {
    safeSearch: SafeSearchType.OFF,
  })

  return (response.results || [])
    .filter((item) => isShortDuration(item.duration))
    .map((item) => {
      const platform = detectPlatform(item.url, item.publishedOn)
      return {
        id: makeId(item.url, item.title),
        title: item.title || 'Untitled video',
        url: item.url,
        thumbnail: item.image || '',
        duration: item.duration || '',
        platform,
        channel: item.publisher || item.publishedOn || platform,
        source: 'duckduckgo' as const,
      }
    })
}

async function searchYouTubeShorts(query: string): Promise<VideoResult[]> {
  const yt = await getYouTube()
  const results = await yt.search(
    `${query} #shorts`,
    { type: 'video', duration: 'short' } as unknown as Parameters<Innertube['search']>[1],
  )

  const out: VideoResult[] = []

  for (const item of results.results || []) {
    if (!item || item.type !== 'Video') continue
    const video = item as {
      id?: string
      title?: { text?: string }
      author?: { name?: string }
      duration?: { text?: string }
      thumbnails?: Array<{ url?: string }>
    }

    const id = video.id || ''
    if (!id) continue
    const duration = video.duration?.text || ''
    if (!isShortDuration(duration)) continue

    const thumb =
      video.thumbnails?.[video.thumbnails.length - 1]?.url ||
      video.thumbnails?.[0]?.url ||
      `https://i.ytimg.com/vi/${id}/hqdefault.jpg`

    out.push({
      id: `yt-${id}`,
      title: video.title?.text || 'Untitled video',
      url: `https://www.youtube.com/shorts/${id}`,
      thumbnail: thumb,
      duration,
      platform: 'youtube',
      channel: video.author?.name || 'YouTube',
      source: 'youtube',
    })
  }

  return out
}

async function searchPlatformPages(
  query: string,
  blacklist: BlacklistState,
): Promise<VideoResult[]> {
  const targets = (Object.entries(PLATFORM_SITE_QUERIES) as [PlatformId, string][]).filter(
    ([platform]) => !blacklist[platform],
  )

  const settled = await Promise.allSettled(
    targets.map(async ([platform, siteQuery]) => {
      const response = await search(`${query} ${siteQuery}`, {
        safeSearch: SafeSearchType.OFF,
      })
      const videos: VideoResult[] = []
      for (const item of response.results || []) {
        const detected = detectPlatform(item.url)
        if (detected !== platform && detected !== 'other') continue
        videos.push({
          id: makeId(item.url, item.title || ''),
          title: item.title || 'Untitled video',
          url: item.url,
          thumbnail: item.icon || '',
          duration: '',
          platform,
          channel: item.hostname || platform,
          source: 'duckduckgo',
        })
        if (videos.length >= 8) break
      }
      return videos
    }),
  )

  return settled.flatMap((result) => (result.status === 'fulfilled' ? result.value : []))
}

export async function searchShortVideos(
  query: string,
  blacklist: BlacklistState,
): Promise<{ videos: VideoResult[]; errors: string[] }> {
  const trimmed = query.trim()
  if (!trimmed) return { videos: [], errors: [] }

  const errors: string[] = []
  const buckets = await Promise.allSettled([
    searchDuckDuckGoVideos(trimmed),
    blacklist.youtube ? Promise.resolve([]) : searchYouTubeShorts(trimmed),
    searchPlatformPages(trimmed, blacklist),
  ])

  const collected: VideoResult[] = []
  const labels = ['DuckDuckGo videos', 'YouTube Shorts', 'Platform pages']

  buckets.forEach((result, index) => {
    if (result.status === 'fulfilled') {
      collected.push(...result.value)
    } else {
      const message =
        result.reason instanceof Error ? result.reason.message : String(result.reason)
      errors.push(`${labels[index]}: ${message}`)
    }
  })

  const filtered = dedupe(collected).filter((video) => !blacklist[video.platform])

  // Prefer results that look like short-form clips, then keep a stable mix.
  filtered.sort((a, b) => {
    const aScore = (a.duration ? 2 : 0) + (a.thumbnail ? 1 : 0)
    const bScore = (b.duration ? 2 : 0) + (b.thumbnail ? 1 : 0)
    return bScore - aScore
  })

  return { videos: filtered.slice(0, 48), errors }
}
