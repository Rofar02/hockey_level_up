const GLOW_GRADIENTS: Record<'ice' | 'persimmon', string> = {
  ice: 'radial-gradient(circle, rgba(215,239,255,0.12) 0%, rgba(215,239,255,0) 70%)',
  persimmon: 'radial-gradient(circle, rgba(255,92,52,0.18) 0%, rgba(255,92,52,0) 70%)',
}

const CORNER_CLASSES: Record<'top-right' | 'top-left', string> = {
  'top-right': '-right-8 -top-10',
  'top-left': '-left-8 -top-10',
}

// Soft radial glow in one corner of a card -- pulled out of TeamDetailPage's
// team-rating card (2026-08-28), which had this exact style inline. A
// smaller, in-palette stand-in for the rejected rink-photo texture: same
// "this card sits on ice" idea as IceGlowBackground's page-wide glow, just
// scoped to one card instead of the whole screen. The parent needs
// `relative overflow-hidden` for this to clip correctly.
export function CardGlow({
  corner = 'top-right',
  color = 'ice',
}: {
  corner?: 'top-right' | 'top-left'
  color?: 'ice' | 'persimmon'
}) {
  return (
    <div
      className={`pointer-events-none absolute ${CORNER_CLASSES[corner]} h-32 w-32 rounded-full`}
      style={{ background: GLOW_GRADIENTS[color] }}
      aria-hidden="true"
    />
  )
}
