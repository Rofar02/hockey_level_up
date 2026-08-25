import { xpToNextLevel } from '../../utils/xpProgress'

// Shared between HomePage's character card and ProfilePage's name card --
// same sample-verified visuals from the RPG-redesign mockup canvas (2026-08-25
// session): a shimmer sweep on the fill, ice accent (XP is a "leveling"
// progress, distinct from the persimmon session-progress bar on
// TrainingSessionPage).
export function XpBar({ level, xp }: { level: number; xp: number }) {
  const xpNext = xpToNextLevel(level)
  const percent = xpNext > 0 ? Math.max(0, Math.min(100, (xp / xpNext) * 100)) : 0

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-baseline justify-between">
        <span className="text-[10px] uppercase tracking-wide text-[#8A96AB]">Опыт</span>
        <span className="font-mono text-xs text-[#8A96AB]">
          {xp}
          <span className="text-[#5c667a]"> / {xpNext}</span>
        </span>
      </div>
      <div className="relative h-2 w-full overflow-hidden rounded-full bg-white/10">
        <div
          className="absolute inset-y-0 left-0 overflow-hidden rounded-full bg-accent-ice"
          style={{ width: `${percent}%` }}
        >
          <div className="animate-shimmer absolute inset-y-0 w-[40%] bg-gradient-to-r from-transparent via-dark-bg/30 to-transparent" />
        </div>
      </div>
    </div>
  )
}
