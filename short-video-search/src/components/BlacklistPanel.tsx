import { PLATFORMS, type BlacklistState, type PlatformId } from '../shared/types'

interface BlacklistPanelProps {
  open: boolean
  blacklist: BlacklistState
  onToggle: (platform: PlatformId) => void
  onClose: () => void
}

export function BlacklistPanel({
  open,
  blacklist,
  onToggle,
  onClose,
}: BlacklistPanelProps) {
  if (!open) return null

  return (
    <aside className="blacklist-panel" aria-label="Site blacklist">
      <div className="panel-head">
        <div>
          <h2>Blacklist sites</h2>
          <p>Turn a toggle on to hide that site from results.</p>
        </div>
        <button type="button" className="icon-btn" onClick={onClose} aria-label="Close">
          ×
        </button>
      </div>

      <ul className="platform-list">
        {PLATFORMS.filter((platform) => platform.id !== 'other').map((platform) => {
          const blocked = blacklist[platform.id]
          return (
            <li key={platform.id}>
              <div className="platform-meta">
                <span
                  className="platform-dot"
                  style={{ background: platform.color }}
                  aria-hidden
                />
                <span>{platform.label}</span>
              </div>
              <label className="toggle">
                <input
                  type="checkbox"
                  checked={blocked}
                  onChange={() => onToggle(platform.id)}
                  aria-label={`Blacklist ${platform.label}`}
                />
                <span className="toggle-track" />
                <span className="toggle-label">{blocked ? 'Blocked' : 'Allowed'}</span>
              </label>
            </li>
          )
        })}
      </ul>
    </aside>
  )
}
