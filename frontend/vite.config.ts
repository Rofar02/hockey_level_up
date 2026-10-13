import { defineConfig, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

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
  plugins: [
    react(),
    versionFile(),
    // Б0 (2026-10-13): the service worker -- src/sw.ts, built to /sw.js with
    // the precache list injected. Registered by hand in src/push.ts (no
    // auto-registration, no auto-update: utils/appUpdate.ts decides when a
    // new version may take over). public/manifest.webmanifest stays as is.
    VitePWA({
      strategies: 'injectManifest',
      srcDir: 'src',
      filename: 'sw.ts',
      injectRegister: false,
      manifest: false,
      injectManifest: {
        // woff2 only (every browser we support reads it; the .woff twins
        // are never fetched), and only the Latin + Cyrillic font subsets --
        // the CSS loads the others by unicode-range, they'd never be used.
        globPatterns: ['**/*.{js,css,html,woff2,svg,png,webp,ico,webmanifest}'],
        globIgnores: [
          '**/version.json',
          'media/**',
          'assets/*-greek-*',
          'assets/*-greek-ext-*',
          'assets/*-vietnamese-*',
          'assets/*-latin-ext-*',
          'assets/*-cyrillic-ext-*',
        ],
        // The biggest chunks (charts, muscle maps) are over workbox's 2 MB default.
        maximumFileSizeToCacheInBytes: 5 * 1024 * 1024,
      },
      devOptions: {
        enabled: true,
        type: 'module',
      },
    }),
  ],
  define: {
    __APP_BUILD_ID__: JSON.stringify(APP_BUILD_ID),
  },
  // `vite preview` of a production build, same-origin like prod (build with
  // VITE_API_BASE_URL=/api): lets e2e check the service worker offline.
  preview: {
    proxy: {
      '/api': { target: 'http://localhost:8000', rewrite: (path) => path.replace(/^\/api/, '') },
    },
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
