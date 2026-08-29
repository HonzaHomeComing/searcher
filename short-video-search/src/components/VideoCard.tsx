import type { ShortSeekApi } from '../../electron/preload'
import { PLATFORMS, type VideoResult } from '../shared/types'

interface VideoCardProps {
  video: VideoResult
  index: number
  api: ShortSeekApi
}

export function VideoCard({ video, index, api }: VideoCardProps) {
  const platform = PLATFORMS.find((item) => item.id === video.platform) || PLATFORMS.at(-1)!

  return (
    <article className="video-card" style={{ animationDelay: `${Math.min(index, 12) * 40}ms` }}>
      <button
        type="button"
        className="thumb-btn"
        onClick={() => api.openExternal(video.url)}
        aria-label={`Open ${video.title}`}
      >
        {video.thumbnail ? (
          <img src={video.thumbnail} alt="" loading="lazy" referrerPolicy="no-referrer" />
        ) : (
          <div className="thumb-fallback" style={{ background: platform.color }}>
            {platform.label.slice(0, 1)}
          </div>
        )}
        {video.duration ? <span className="duration">{video.duration}</span> : null}
        <span className="play-hint" aria-hidden>
          ▶
        </span>
      </button>

      <div className="card-meta">
        <div className="source-line">
          <span className="platform-dot" style={{ background: platform.color }} />
          <span className="source-text">
            {platform.label}
            <span className="dot-sep">·</span>
            {video.channel}
          </span>
        </div>
        <h3 className="card-title">{video.title}</h3>
      </div>
    </article>
  )
}
