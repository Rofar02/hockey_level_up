const ACCENT_STROKE = {
  ice: '#D7EFFF',
  persimmon: '#FF5C34',
} as const

// A faceoff-circle stand-in for ProgressBar wherever progress reads as
// "closing in on a target" rather than "filling a container" -- skill
// milestone thresholds, specifically (hockey design pass, 2026-08-28: see
// SkillsNearMilestoneCard). Four short hash marks around the ring echo the
// real circle's own markings; ProgressBar itself is untouched and still
// covers every continuous/linear case (training-block phase, XP).
export function FaceoffProgressRing({
  value,
  max,
  accent = 'ice',
  size = 56,
  centerValue,
}: {
  value: number
  max: number
  accent?: keyof typeof ACCENT_STROKE
  size?: number
  // What to print in the middle -- caller's choice (percent, points
  // remaining, a checkmark glyph at 100%) rather than this component
  // guessing which framing fits the caller's copy.
  centerValue: string
}) {
  const percent = max > 0 ? Math.max(0, Math.min(100, (value / max) * 100)) : 100
  const strokeWidth = size * 0.09
  const radius = size / 2 - strokeWidth
  const circumference = 2 * Math.PI * radius
  const dashoffset = circumference * (1 - percent / 100)
  const center = size / 2
  const hashLength = size * 0.09
  const hashInset = strokeWidth * 1.8

  const hashMarks = [0, 90, 180, 270].map((angleDeg) => {
    const angle = (angleDeg * Math.PI) / 180
    const x1 = center + Math.sin(angle) * (radius + hashInset)
    const y1 = center - Math.cos(angle) * (radius + hashInset)
    const x2 = center + Math.sin(angle) * (radius + hashInset + hashLength)
    const y2 = center - Math.cos(angle) * (radius + hashInset + hashLength)
    return { angleDeg, x1, y1, x2, y2 }
  })

  return (
    <div className="relative shrink-0" style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="overflow-visible">
        {hashMarks.map((hash) => (
          <line
            key={hash.angleDeg}
            x1={hash.x1}
            y1={hash.y1}
            x2={hash.x2}
            y2={hash.y2}
            stroke="rgba(255,255,255,0.15)"
            strokeWidth={strokeWidth * 0.6}
            strokeLinecap="round"
          />
        ))}
        <circle cx={center} cy={center} r={radius} fill="none" stroke="rgba(255,255,255,0.1)" strokeWidth={strokeWidth} />
        <circle
          cx={center}
          cy={center}
          r={radius}
          fill="none"
          stroke={ACCENT_STROKE[accent]}
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={dashoffset}
          transform={`rotate(-90 ${center} ${center})`}
        />
      </svg>
      <div className="absolute inset-0 flex items-center justify-center">
        <span
          className="font-display font-semibold leading-none text-[#F2F5F8]"
          style={{ fontSize: size * 0.28 }}
        >
          {centerValue}
        </span>
      </div>
    </div>
  )
}
