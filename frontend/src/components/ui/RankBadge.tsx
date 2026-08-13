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
    return <span className="w-8 shrink-0 text-center font-mono text-sm text-[#8A94A6]">{rank}</span>
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
