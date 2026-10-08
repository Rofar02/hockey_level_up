import { useEffect, useState } from 'react'
import { FullScreenOverlay } from './ui/FullScreenOverlay'
import { useNavigate } from 'react-router-dom'
import * as authApi from '../api/auth'
import * as progressApi from '../api/progress'
import { useSuppressCoachmarks } from '../hooks/useSuppressCoachmarks'
import { TARGET_STAT_LABELS } from '../types/exercise'
import type { TargetStat } from '../types/exercise'
import type { TrainingStreakRead } from '../types/progress'
import { Button } from './ui/Button'
import { CardGlow } from './ui/CardGlow'
import { IceGlowBackground } from './ui/IceGlowBackground'
import { ShieldIcon } from './ui/ShieldIcon'
import { StatIcon } from './ui/StatIcon'

function formatGain(value: number): string {
  return `+${value.toLocaleString('ru-RU', { maximumFractionDigits: 1 })}`
}

// What the report after an ice day or a game earned (2026-10-08) -- the
// same "you did it" moment as the end of an off-ice workout
// (TrainingSessionPage's SessionCompleteModal), but the stats come from the
// report, not from exercises. The report form itself shows no numbers on
// purpose: the reward is a surprise after saving, not a price list.
export function ReportRewardScreen({
  kind,
  statRewards,
  xpReward,
  focusDone = false,
  levelBefore,
  accessToken,
}: {
  kind: 'on_ice' | 'game'
  statRewards: Partial<Record<TargetStat, number>>
  xpReward: number
  focusDone?: boolean
  levelBefore: number | null
  accessToken: string
}) {
  const navigate = useNavigate()
  const [streak, setStreak] = useState<TrainingStreakRead | null>(null)
  const [levelAfter, setLevelAfter] = useState<number | null>(null)
  useSuppressCoachmarks(true)

  useEffect(() => {
    let cancelled = false
    // Best-effort extras -- the reward itself is already on screen.
    Promise.all([progressApi.getMyStreak(accessToken), authApi.getCurrentUser(accessToken)])
      .then(([streakResult, user]) => {
        if (!cancelled) {
          setStreak(streakResult)
          setLevelAfter(user.level)
        }
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [accessToken])

  const leveledUp = levelBefore !== null && levelAfter !== null && levelAfter > levelBefore
  const stats = (Object.entries(statRewards) as [TargetStat, number][]).sort((a, b) => b[1] - a[1])

  return (
    <FullScreenOverlay className="flex flex-col overflow-y-auto bg-dark-bg">
      <IceGlowBackground />
      <div className="relative z-[1] mx-auto flex w-full max-w-sm flex-1 flex-col items-center gap-6 px-5 pb-[calc(1.5rem+env(safe-area-inset-bottom))] pt-[calc(3.5rem+env(safe-area-inset-top))]">
        <div className="flex h-20 w-20 items-center justify-center rounded-full border-2 border-accent-ice bg-accent-ice/10">
          <i className={`ti ${kind === 'game' ? 'ti-trophy' : 'ti-ice-skating'} text-4xl text-accent-ice`} aria-hidden="true" />
        </div>
        <div className="flex flex-col items-center gap-1 text-center">
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-accent-persimmon">
            {kind === 'game' ? 'Игра закрыта' : 'Лёд закрыт'}
          </p>
          <h1 className="text-2xl font-semibold text-text-primary">Молодец, так держать</h1>
          <p className="mt-2 font-display text-4xl font-bold text-text-primary">+{xpReward} XP</p>
        </div>

        {focusDone && (
          <div className="flex w-full items-center gap-2.5 rounded-xl border border-accent-persimmon/35 bg-accent-persimmon/10 px-4 py-3 text-sm">
            <i className="ti ti-target-arrow text-lg text-accent-persimmon" aria-hidden="true" />
            <span>
              <b className="font-semibold text-text-primary">Фокус дня засчитан</b>{' '}
              <span className="text-[#B7C2D4]">— бонус к его стату</span>
            </span>
          </div>
        )}

        <div className="flex w-full flex-col gap-2">
          {stats.map(([stat, gain]) => (
            <div key={stat} className="flex items-center gap-3 rounded-xl bg-dark-card px-4 py-3">
              <StatIcon stat={stat} size={18} className="text-accent-ice" />
              <span className="flex-1 text-sm text-text-primary">{TARGET_STAT_LABELS[stat]}</span>
              <span className="font-display text-lg font-semibold text-accent-persimmon">{formatGain(gain)}</span>
            </div>
          ))}
        </div>

        {streak !== null && streak.current_streak > 0 && (
          <p className="flex items-center gap-1.5 text-sm text-text-secondary">
            <i className="ti ti-flame text-accent-persimmon" aria-hidden="true" />
            Серия: {streak.current_streak} дн. подряд
          </p>
        )}

        {leveledUp && (
          <div className="relative w-full overflow-hidden rounded-md border border-accent-persimmon/40 bg-accent-persimmon/10 p-5 text-center">
            <CardGlow color="persimmon" />
            <div className="relative flex flex-col items-center gap-1">
              <ShieldIcon size={28} className="text-accent-persimmon" />
              <p className="text-sm font-medium text-accent-persimmon">Новый уровень!</p>
              <p className="font-display text-3xl font-bold text-accent-persimmon">{levelAfter}</p>
            </div>
          </div>
        )}

        <div className="mt-auto flex w-full flex-col gap-2 pt-4">
          <Button onClick={() => navigate('/', { replace: true })} className="w-full">
            Отлично
          </Button>
          <button
            type="button"
            onClick={() => navigate('/diary', { replace: true })}
            className="min-h-11 text-sm text-text-secondary transition-colors hover:text-text-primary"
          >
            Все записи дневника
          </button>
        </div>
      </div>
    </FullScreenOverlay>
  )
}
