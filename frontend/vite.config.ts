import { defineConfig, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'

// One id per build: baked into the JS (__APP_BUILD_ID__) and published as
// /version.json, so a long-lived tab can tell it's behind the server (see
// src/utils/appUpdate.ts). Computed once so both always match.
const APP_BUILD_ID = process.env.APP_BUILD_ID || String(Date.now())

function versionFile(): Plugin {
  return {
    name: 'icelevel-version-file',
    apply: 'build',
    generateBundle() {
      this.emitFile({
        type: 'asset',
        fileName: 'version.json',
        source: JSON.stringify({ build: APP_BUILD_ID }),
      })
    },
  }
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), versionFile()],
  define: {
    __APP_BUILD_ID__: JSON.stringify(APP_BUILD_ID),
  },
  server: {
    // 0.0.0.0 listens on every network interface, not just loopback -- lets
    // a phone on the same Wi-Fi reach the dev server via the PC's LAN IP.
    host: '0.0.0.0',
    watch: {
      // Docker Desktop on Windows doesn't reliably propagate native
      // filesystem change events (inotify) from a host bind mount into the
      // Linux container -- chokidar's default watcher silently never fires,
      // so edits on the host never trigger HMR. Polling instead of waiting
      // for those events is the standard workaround.
      usePolling: true,
    },
  },
})
