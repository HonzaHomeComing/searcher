import type { ShortSeekApi } from '../../electron/preload'
import type { VideoResult } from '../shared/types'
import { VideoCard } from './VideoCard'

interface VideoGridProps {
  videos: VideoResult[]
  api: ShortSeekApi
}

export function VideoGrid({ videos, api }: VideoGridProps) {
  if (videos.length === 0) return null

  return (
    <section className="video-grid" aria-label="Short video results">
      {videos.map((video, index) => (
        <VideoCard key={video.id} video={video} index={index} api={api} />
      ))}
    </section>
  )
}
