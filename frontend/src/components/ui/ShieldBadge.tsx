interface ShieldBadgeProps {
  value: number | string
  label: string
  accentColor: 'ice' | 'persimmon'
}

const ACCENT_CLASSES: Record<ShieldBadgeProps['accentColor'], { stroke: string; text: string }> = {
  ice: { stroke: 'stroke-accent-ice', text: 'text-accent-ice' },
  persimmon: { stroke: 'stroke-accent-persimmon', text: 'text-accent-persimmon' },
}

// Fixed shield shape (pointed top, straight sides, pointed bottom) scaled to
// whatever size the wrapping div is given -- the SVG only draws the outline,
// the value is a real HTML overlay so it gets normal font rendering instead
// of fighting SVG <text> baseline alignment.
export function ShieldBadge({ value, label, accentColor }: ShieldBadgeProps) {
  const { stroke, text } = ACCENT_CLASSES[accentColor]

  return (
    <div className="flex flex-col items-center">
      <div className="relative aspect-[56/64] w-[90px]">
        <svg viewBox="0 0 56 64" className="absolute inset-0 h-full w-full" aria-hidden="true">
          <path
            d="M28 2 L52 10 L52 34 Q52 52 28 62 Q4 52 4 34 L4 10 Z"
            className={`fill-dark-card ${stroke}`}
            strokeWidth={2}
          />
        </svg>
        <div className="absolute left-1/2 top-[36%] -translate-x-1/2 -translate-y-1/2">
          <span className={`font-mono text-2xl font-bold leading-none ${text}`}>{value}</span>
        </div>
      </div>
      <span className="mt-1 text-[10px] uppercase tracking-wide text-text-secondary">{label}</span>
    </div>
  )
}
