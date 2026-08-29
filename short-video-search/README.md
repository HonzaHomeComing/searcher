# Short Seek

Windowed desktop app for searching short-form videos across the web, with per-site blacklist toggles.

## Run

```bash
cd short-video-search
npm install
npm run dev
```

This opens an Electron window. Search by keyword, then use **Sources** to blacklist platforms (toggle on = blocked).

## How search works

Results are aggregated from:

- DuckDuckGo video search (short clips)
- YouTube Shorts via Innertube
- Site-scoped web results for TikTok, Instagram, Facebook, LinkedIn, Vimeo, and Dailymotion when available

Clicking a result opens it in your default browser.
