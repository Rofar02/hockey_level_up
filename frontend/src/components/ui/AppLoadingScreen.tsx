// Shared splash for the few genuine "whole app is loading" moments (auth
// restore in the route guards, a lazy route chunk still downloading) -- NOT
// meant for the many inline section-level "Загрузка..." spinners scattered
// through individual pages, which stay as plain text on purpose (a pulsing
// logo on every list/modal load would be noisy, not a branding moment).
export function AppLoadingScreen() {
  return (
    <div
      className="flex min-h-svh flex-col items-center justify-center bg-dark-bg"
      role="status"
    >
      <img
        src="/images/logo.webp"
        alt=""
        className="w-full max-w-[180px] animate-pulse opacity-80"
      />
      <span className="sr-only">Загрузка...</span>
    </div>
  )
}
