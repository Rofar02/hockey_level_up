import { Component } from 'react'
import type { ErrorInfo, ReactNode } from 'react'
import { isChunkLoadError, reloadForStaleChunk } from '../utils/staleChunkReload'

// Last line of defence around the routes: without it any render error --
// most often a page chunk that vanished in a deploy -- unmounted the whole
// tree and left a blank screen with no way out but a manual reload.
export class AppErrorBoundary extends Component<{ children: ReactNode }, { error: unknown }> {
  state: { error: unknown } = { error: null }

  static getDerivedStateFromError(error: unknown) {
    return { error }
  }

  componentDidCatch(error: unknown, info: ErrorInfo) {
    if (isChunkLoadError(error) && reloadForStaleChunk()) {
      return
    }
    console.error('Unhandled render error', error, info.componentStack)
  }

  render() {
    if (this.state.error === null) {
      return this.props.children
    }
    return (
      <div className="flex min-h-svh flex-col items-center justify-center gap-4 bg-dark-bg px-6 text-center">
        <img src="/images/logo.webp" alt="" className="w-full max-w-[140px] opacity-80" />
        <h1 className="text-lg font-semibold text-text-primary">Не удалось открыть экран</h1>
        <p className="max-w-xs text-sm text-text-secondary">
          Скорее всего, приложение обновилось. Обновите страницу — всё сохранено.
        </p>
        <button
          type="button"
          onClick={() => window.location.reload()}
          className="rounded bg-accent-persimmon px-5 py-2.5 font-medium text-dark-bg transition-colors hover:bg-accent-persimmon/90"
        >
          Обновить
        </button>
      </div>
    )
  }
}
