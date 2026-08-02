export function ProgressBar({ value, max }: { value: number; max: number }) {
  const percent = max > 0 ? Math.max(0, Math.min(100, (value / max) * 100)) : 100

  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-white/10">
      <div className="h-full rounded-full bg-accent-ice" style={{ width: `${percent}%` }} />
    </div>
  )
}
