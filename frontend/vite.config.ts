import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
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
