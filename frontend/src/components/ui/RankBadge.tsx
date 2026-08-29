// Conventional medal colors, not the app's usual ice/persimmon accent pair
// -- scoped deliberately tight (only this podium circle) rather than
// proposed as new brand colors. A leaderboard rank is exactly the kind of
// content where gold/silver/bronze is immediately legible in a way a third
// invented brand accent wouldn't be.
const MEDAL_COLORS: Record<number, string> = {
  1: '#FFC94A',
  2: '#C7CFDB',
  3: '#D3915B',
}

// Podium (top 3) gets a conventional medal color instead of a plain gray
// number -- see MEDAL_COLORS above for why those specific colors are an
// exception to the app's usual ice/persimmon-only palette.
export function RankBadge({ rank }: { rank: number }) {
  const medalColor = MEDAL_COLORS[rank]
  if (medalColor === undefined) {
    // Same circle shape as the medal ranks below, just unlit (icy outline,
    // no fill) -- a bare number floating next to a row read as disconnected
    // from the podium's medal circles above it (hockey design pass,
    // 2026-08-30); the shape now carries through past rank 3, only the
    // color stops.
    return (
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-white/10 font-mono text-sm text-[#8A94A6]">
        {rank}
      </div>
    )
  }
  return (
    <div
      className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full font-mono text-sm font-bold text-dark-bg"
      style={{ backgroundColor: medalColor }}
    >
      {rank === 1 ? <i className="ti ti-trophy text-base" aria-hidden="true" /> : rank}
    </div>
  )
}
