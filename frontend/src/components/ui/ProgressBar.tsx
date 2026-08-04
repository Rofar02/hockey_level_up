const ACCENT_FILL = {
  ice: 'bg-accent-ice',
  persimmon: 'bg-accent-persimmon',
} as const

export function ProgressBar({
  value,
  max,
  accent = 'ice',
}: {
  value: number
  max: number
  accent?: keyof typeof ACCENT_FILL
}) {
  const percent = max > 0 ? Math.max(0, Math.min(100, (value / max) * 100)) : 100

  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-white/10">
      <div className={`h-full rounded-full ${ACCENT_FILL[accent]}`} style={{ width: `${percent}%` }} />
    </div>
  )
}
