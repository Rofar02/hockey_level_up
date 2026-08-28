const ACCENT_COLORS = {
  ice: '#D7EFFF',
  persimmon: '#FF5C34',
} as const

function formatSeconds(totalSeconds: number): string {
  return String(Math.max(0, Math.ceil(totalSeconds)))
}

// The one ring shared by TimerPlayer's work/rest states and SetLogger's
// between-set RestTimer (media-player redesign, 2026-08-28: "хочу чтобы это
// было прям как медиаплеер"). `interactive` is the whole point -- when
// true, the ring itself is the play/pause control (no separate button
// sibling below it); when false (a rest countdown), the ring is display
// only and whatever "Пропустить" affordance the caller needs renders
// outside this component, since skipping a rest isn't a play/pause action.
export function CountdownRing({
  size = 148,
  totalSeconds,
  remainingSeconds,
  label,
  accent,
  interactive = false,
  running = false,
  onToggle,
}: {
  size?: number
  totalSeconds: number
  remainingSeconds: number
  label: string
  accent: 'ice' | 'persimmon'
  interactive?: boolean
  running?: boolean
  onToggle?: () => void
}) {
  const strokeWidth = 10
  const radius = size / 2 - strokeWidth
  const circumference = 2 * Math.PI * radius
  const elapsed = totalSeconds - remainingSeconds
  const percent = totalSeconds > 0 ? Math.max(0, Math.min(1, elapsed / totalSeconds)) : 0
  const dashoffset = circumference * (1 - percent)
  const center = size / 2
  // Video-player convention (2026-08-28, "кнопку плей посередине, когда ее
  // нажимаем появляется таймер"): before the first tap, show only a big
  // centered play button, no digits -- `running` flips true the instant
  // onToggle fires (before any tick), so it alone (not a tick-dependent
  // comparison) is what tells "never started" apart from "paused mid-way",
  // which keeps showing digits + the small pause/play toggle as before.
  const notStarted = interactive && !running && remainingSeconds >= totalSeconds

  return (
    <div
      className="relative"
      style={{ width: size, height: size }}
      role={interactive ? 'button' : undefined}
      tabIndex={interactive ? 0 : undefined}
      aria-label={interactive ? (running ? 'Пауза' : 'Старт') : undefined}
      onClick={interactive ? onToggle : undefined}
      onKeyDown={
        interactive
          ? (event) => {
              if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault()
                onToggle?.()
              }
            }
          : undefined
      }
    >
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <circle cx={center} cy={center} r={radius} fill="none" stroke="rgba(255,255,255,0.1)" strokeWidth={strokeWidth} />
        <circle
          cx={center}
          cy={center}
          r={radius}
          fill="none"
          stroke={ACCENT_COLORS[accent]}
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={dashoffset}
          transform={`rotate(-90 ${center} ${center})`}
        />
      </svg>
      {notStarted ? (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
          <span
            className="flex h-14 w-14 items-center justify-center rounded-full bg-white/10"
            style={{ color: ACCENT_COLORS[accent] }}
          >
            <i className="ti ti-player-play text-3xl" aria-hidden="true" />
          </span>
        </div>
      ) : (
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center gap-1">
          <span className="font-display text-4xl font-semibold leading-none text-text-primary">
            {formatSeconds(remainingSeconds)}
          </span>
          <span className="text-[11px] uppercase tracking-wide text-text-secondary">{label}</span>
          {interactive && (
            <span
              className="mt-1 flex h-8 w-8 items-center justify-center rounded-full bg-white/10"
              style={{ color: ACCENT_COLORS[accent] }}
            >
              <i className={`ti ${running ? 'ti-player-pause' : 'ti-player-play'} text-base`} aria-hidden="true" />
            </span>
          )}
        </div>
      )}
    </div>
  )
}
