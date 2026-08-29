import type { Plugin } from 'vite'
import { searchShortVideos } from './electron/search'
import { DEFAULT_BLACKLIST, type BlacklistState } from './src/shared/types'

/**
 * Dev-only HTTP search endpoint so the UI can be exercised in a normal browser
 * when Electron preload is unavailable.
 */
export function searchApiPlugin(): Plugin {
  return {
    name: 'short-seek-search-api',
    configureServer(server) {
      server.middlewares.use(async (req, res, next) => {
        if (!req.url?.startsWith('/api/search')) return next()

        try {
          const url = new URL(req.url, 'http://localhost')
          const query = url.searchParams.get('q') || ''
          const result = await searchShortVideos(query, { ...DEFAULT_BLACKLIST } as BlacklistState)
          res.setHeader('Content-Type', 'application/json')
          res.end(JSON.stringify(result))
        } catch (error) {
          res.statusCode = 500
          res.setHeader('Content-Type', 'application/json')
          res.end(
            JSON.stringify({
              videos: [],
              errors: [error instanceof Error ? error.message : String(error)],
            }),
          )
        }
      })
    },
  }
}
