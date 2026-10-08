import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import * as gameStatsApi from '../api/gameStats'
import { ApiError } from '../api/client'
import { BackLink } from '../components/ui/BackLink'
import { EmptyState } from '../components/ui/EmptyState'
import { FormError } from '../components/ui/FormError'
import { IceGlowBackground } from '../components/ui/IceGlowBackground'
import { useAuth } from '../hooks/useAuth'
import type { SeasonRead } from '../types/gameStats'
import type { GameResult } from '../types/trainingDiary'
import { parseIsoDate } from '../utils/date'

const RESULT_LETTERS: Record<GameResult, { letter: string; className: string }> = {
  win: { letter: 'В', className: 'bg-accent-ice/15 text-accent-ice' },
  draw: { letter: 'Н', className: 'bg-white/10 text-[#B7C2D4]' },
  loss: { letter: 'П', className: 'bg-accent-persimmon/15 text-accent-persimmon' },
}

function plural(count: number, one: string, few: string, many: string): string {
  const mod10 = count % 10
  const mod100 = count % 100
  if (mod10 === 1 && mod100 !== 11) {
    return one
  }
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) {
    return few
  }
  return many
}

// The player's season (2026-10-08): games, goals, assists, points and shots
// from their own game reports, the self-rating trend (only theirs to see)
// and the latest games, each opening its report.
export function SeasonPage() {
  const { accessToken } = useAuth()
  const navigate = useNavigate()
  const [season, setSeason] = useState<SeasonRead | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)

  useEffect(() => {
    if (accessToken === null) {
      return
    }
    gameStatsApi
      .getMySeason(accessToken)
      .then(setSeason)
      .catch((err: unknown) => setLoadError(err instanceof ApiError ? err.message : 'Не удалось загрузить сезон.'))
  }, [accessToken])

  const ratings = season?.recent_games.filter((game) => game.self_rating !== null) ?? []

  return (
    <div className="relative min-h-svh overflow-hidden">
      <IceGlowBackground />
      <div className="relative z-[1] mx-auto flex max-w-2xl flex-col gap-5 px-4 pb-[var(--bottom-nav-space)] pt-10">
        <div className="flex flex-col gap-2">
          <BackLink />
          <div className="flex items-baseline justify-between gap-3">
            <h1 className="font-display text-2xl font-semibold uppercase tracking-wide">
              Сезон {season?.label ?? ''}
            </h1>
            {season !== null && (
              <span className="text-sm text-text-secondary">
                {season.games} {plural(season.games, 'игра', 'игры', 'игр')}
              </span>
            )}
          </div>
        </div>

        <FormError message={loadError} />
        {season === null && loadError === null && <p className="text-sm text-text-secondary">Загрузка...</p>}

        {season !== null && season.games === 0 && (
          <EmptyState
            icon="ti-trophy"
            title="Пока ни одной игры"
            hint="После игры отметьте результат в отчёте «Как сыграли?» — здесь появится ваш сезон"
          />
        )}

        {season !== null && season.games > 0 && (
          <>
            <section className="grid grid-cols-4 rounded-2xl border border-accent-ice/20 bg-dark-card">
              {[
                ['Голы', season.goals],
                ['Передачи', season.assists],
                ['Очки', season.points],
                ['Броски', season.shots],
              ].map(([label, value], index) => (
                <div key={label} className="flex flex-col items-center gap-1 py-3">
                  <span
                    className={`font-display text-3xl font-semibold leading-none ${index === 2 ? 'text-accent-ice' : 'text-text-primary'}`}
                  >
                    {value}
                  </span>
                  <span className="text-[10px] uppercase tracking-wider text-text-secondary">{label}</span>
                </div>
              ))}
            </section>
            <p className="-mt-2 text-center text-xs text-text-secondary">
              Победы {season.wins} · ничьи {season.draws} · поражения {season.losses}
            </p>

            {ratings.length > 0 && (
              <section className="rounded-2xl bg-dark-card p-4">
                <div className="flex items-baseline justify-between">
                  <h2 className="text-sm font-semibold">Самооценка по играм</h2>
                  <span className="flex items-center gap-1 text-xs text-text-secondary">
                    <i className="ti ti-lock" aria-hidden="true" />
                    видно только вам
                  </span>
                </div>
                <div className="mt-3 flex h-20 items-end gap-1.5 overflow-hidden" aria-hidden="true">
                  {ratings.map((game, index) => (
                    <span
                      key={game.day_plan_id}
                      className={`w-5 shrink-0 rounded-t ${index === ratings.length - 1 ? 'bg-accent-ice' : 'bg-accent-ice/35'}`}
                      style={{ height: `${((game.self_rating ?? 0) / 5) * 100}%` }}
                    />
                  ))}
                </div>
                <p className="mt-2 text-xs text-text-secondary">
                  Средняя {season.avg_self_rating?.toLocaleString('ru-RU')} из 5
                </p>
              </section>
            )}

            <section className="flex flex-col gap-2">
              <h2 className="text-xs font-semibold uppercase tracking-wider text-text-secondary">Последние игры</h2>
              {[...season.recent_games].reverse().map((game) => (
                <button
                  key={game.day_plan_id}
                  type="button"
                  onClick={() => navigate(`/training/${game.day_plan_id}/diary`)}
                  className="flex min-h-14 items-center gap-3 rounded-xl bg-dark-card px-4 py-2 text-left transition-colors hover:bg-white/[0.04]"
                >
                  <span
                    className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg font-display text-sm font-semibold ${RESULT_LETTERS[game.result].className}`}
                  >
                    {RESULT_LETTERS[game.result].letter}
                  </span>
                  <span className="flex min-w-0 flex-1 flex-col">
                    <span className="text-sm font-semibold">
                      {parseIsoDate(game.date).toLocaleDateString('ru-RU', { weekday: 'short', day: 'numeric', month: 'short' })}
                    </span>
                    <span className="text-xs text-text-secondary">
                      {game.goals === null
                        ? 'без статистики'
                        : `голы ${game.goals} · передачи ${game.assists ?? 0} · броски ${game.shots ?? 0}`}
                    </span>
                  </span>
                  <i className="ti ti-chevron-right text-text-secondary" aria-hidden="true" />
                </button>
              ))}
            </section>
          </>
        )}
      </div>
    </div>
  )
}
