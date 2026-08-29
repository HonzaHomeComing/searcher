import { useId } from 'react'

interface SearchBarProps {
  value: string
  loading: boolean
  onChange: (value: string) => void
  onSubmit: () => void
}

export function SearchBar({ value, loading, onChange, onSubmit }: SearchBarProps) {
  const id = useId()

  return (
    <form
      className="search-form"
      onSubmit={(event) => {
        event.preventDefault()
        onSubmit()
      }}
    >
      <label className="sr-only" htmlFor={id}>
        Search short videos
      </label>
      <div className={`search-shell ${loading ? 'loading' : ''}`}>
        <svg className="search-icon" viewBox="0 0 24 24" aria-hidden>
          <path
            fill="currentColor"
            d="M15.5 14h-.79l-.28-.27A6.47 6.47 0 0 0 16 9.5 6.5 6.5 0 1 0 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14"
          />
        </svg>
        <input
          id={id}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder="Search short videos"
          autoComplete="off"
          spellCheck={false}
        />
        {value ? (
          <button
            type="button"
            className="clear-btn"
            aria-label="Clear search"
            onClick={() => onChange('')}
          >
            ×
          </button>
        ) : null}
        <button type="submit" className="go-btn" disabled={loading || !value.trim()}>
          {loading ? '…' : 'Search'}
        </button>
      </div>
    </form>
  )
}
