/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL: string
  // Base URL of the exercise clips/posters; empty/unset falls back to the
  // backend's /static mount (see utils/media.ts).
  readonly VITE_MEDIA_BASE_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
