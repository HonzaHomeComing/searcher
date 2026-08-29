import { app, BrowserWindow, ipcMain, shell } from 'electron'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import {
  DEFAULT_BLACKLIST,
  type BlacklistState,
  type PlatformId,
} from '../src/shared/types'
import { searchShortVideos } from './search'

// Cloud / container environments often lack a working sandbox user namespace.
app.commandLine.appendSwitch('no-sandbox')
app.commandLine.appendSwitch('disable-gpu-sandbox')

const __dirname = path.dirname(fileURLToPath(import.meta.url))

process.env.DIST = path.join(__dirname, '../dist')
process.env.VITE_PUBLIC = app.isPackaged
  ? process.env.DIST
  : path.join(__dirname, '../public')

let mainWindow: BrowserWindow | null = null

const settingsPath = () => path.join(app.getPath('userData'), 'settings.json')

function readBlacklist(): BlacklistState {
  try {
    const raw = fs.readFileSync(settingsPath(), 'utf8')
    const parsed = JSON.parse(raw) as { blacklist?: Partial<BlacklistState> }
    return { ...DEFAULT_BLACKLIST, ...parsed.blacklist }
  } catch {
    return { ...DEFAULT_BLACKLIST }
  }
}

function writeBlacklist(blacklist: BlacklistState) {
  fs.mkdirSync(path.dirname(settingsPath()), { recursive: true })
  fs.writeFileSync(settingsPath(), JSON.stringify({ blacklist }, null, 2), 'utf8')
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 860,
    minWidth: 900,
    minHeight: 640,
    title: 'Short Seek',
    backgroundColor: '#202124',
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(
        __dirname,
        fs.existsSync(path.join(__dirname, 'preload.mjs'))
          ? 'preload.mjs'
          : 'preload.js',
      ),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
  })

  if (process.env.VITE_DEV_SERVER_URL) {
    mainWindow.loadURL(process.env.VITE_DEV_SERVER_URL)
  } else {
    mainWindow.loadFile(path.join(process.env.DIST!, 'index.html'))
  }

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url)
    return { action: 'deny' }
  })
}

app.whenReady().then(() => {
  ipcMain.handle('search:videos', async (_event, query: string) => {
    const blacklist = readBlacklist()
    return searchShortVideos(query, blacklist)
  })

  ipcMain.handle('blacklist:get', () => readBlacklist())

  ipcMain.handle(
    'blacklist:set',
    (_event, platform: PlatformId, blocked: boolean) => {
      const next = readBlacklist()
      next[platform] = blocked
      writeBlacklist(next)
      return next
    },
  )

  ipcMain.handle('blacklist:set-all', (_event, blacklist: BlacklistState) => {
    writeBlacklist({ ...DEFAULT_BLACKLIST, ...blacklist })
    return readBlacklist()
  })

  ipcMain.handle('open:external', (_event, url: string) => {
    shell.openExternal(url)
  })

  createWindow()

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})
