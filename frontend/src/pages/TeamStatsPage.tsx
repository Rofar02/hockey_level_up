import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import * as gameStatsApi from '../api/gameStats'
import { ApiError } from '../api/client'
import { BackLink } from '../components/ui/BackLink'
import { Button } from '../components/ui/Button'
import { EmptyState } from '../components/ui/EmptyState'
import { FormError } from '../components/ui/FormError'
import { IceGlowBackground } from '../components/ui/IceGlowBackground'
import { useAuth } from '../hooks/useAuth'
import type { TeamStatsRead, TeamStatsScope } from '../types/gameStats'
import { GAME_WORK_ON_LABELS } from '../types/trainingDiary'
import { parseIsoDate } from '../utils/date'

const COLUMNS = 'grid grid-cols-[28px_minmax(0,1fr)_30px_30px_30px_36px] items-center gap-1.5'

// The captain's table of the team's games (2026-10-08): each player's
// goals/assists/points/shots from their own reports on this team's games.
// "Хочет: ..." and the self-rating only where the player allowed it; who
// hasn't reported a played game yet, with a once-an-hour reminder push.
export function TeamStatsPage() {
  const { teamId } = useParams<{ teamId: string }>()
  const { accessToken } = useAuth()
  const [scope, setScope] = useState<TeamStatsScope>('season')
  const [stats, setStats] = useState<TeamStatsRead | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [remindState, setRemindState] = useState<string | null>(null)
  const [isReminding, setIsReminding] = useState(false)

  useEffect(() => {
    if (accessToken === null || teamId === undefined) {
      return
    }
    let cancelled = false
    setStats(null)
    gameStatsApi
      .getTeamStats(teamId, scope, accessToken)
      .then((result) => {
        if (!cancelled) {
          setStats(result)
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setLoadError(err instanceof ApiError ? err.message : 'Не удалось загрузить статистику.')
        }
      })
    return () => {
      cancelled = true
    }
  }, [accessToken, teamId, scope])

  async function remind() {
    if (accessToken === null || teamId === undefined) {
      return
    }
    setIsReminding(true)
    try {
      const result = await gameStatsApi.remindTeamReports(teamId, accessToken)
      setRemindState(result.reminded > 0 ? `Напомнили игрокам: ${result.reminded}` : 'Все уже заполнили')
    } catch (err) {
      setRemindState(err instanceof ApiError ? err.message : 'Не удалось отправить напоминание.')
    } finally {
      setIsReminding(false)
    }
  }

  const missing = stats?.players.filter((player) => player.missing_reports > 0).length ?? 0

  return (
    <div className="relative min-h-svh overflow-hidden">
      <IceGlowBackground />
      <div className="relative z-[1] mx-auto flex max-w-2xl flex-col gap-4 px-4 pb-[var(--bottom-nav-space)] pt-10">
        <div className="flex flex-col gap-2">
          <BackLink />
          <h1 className="font-display text-2xl font-semibold uppercase tracking-wide">Статистика</h1>
        </div>

        <div className="flex gap-2">
          {(
            [
              ['season', `Сезон ${stats?.season_label ?? ''}`],
              ['last_game', 'Последняя игра'],
            ] as [TeamStatsScope, string][]
          ).map(([value, label]) => (
            <button
              key={value}
              type="button"
              onClick={() => setScope(value)}
              aria-pressed={scope === value}
              className={`min-h-10 rounded-full border px-4 text-sm transition-colors ${
                scope === value
                  ? 'border-accent-ice bg-accent-ice/15 font-semibold text-accent-ice'
                  : 'border-white/10 text-text-secondary hover:text-text-primary'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
        {scope === 'last_game' && stats?.last_game_date && (
          <p className="-mt-2 text-xs text-text-secondary">
            Игра {parseIsoDate(stats.last_game_date).toLocaleDateString('ru-RU', { day: 'numeric', month: 'long' })}
          </p>
        )}

        <FormError message={loadError} />
        {stats === null && loadError === null && <p className="text-sm text-text-secondary">Загрузка...</p>}

        {stats !== null && stats.last_game_date === null && (
          <EmptyState icon="ti-trophy" title="Игр ещё не было" hint="Статистика появится после первой командной игры" />
        )}

        {stats !== null && stats.last_game_date !== null && (
          <>
            <div className={`${COLUMNS} px-3 text-[10px] uppercase tracking-wider text-text-secondary`}>
              <span>№</span>
              <span>Игрок</span>
              <span className="text-center">Г</span>
              <span className="text-center">П</span>
              <span className="text-center">О</span>
              <span className="text-center">Бр</span>
            </div>
            <div className="flex flex-col gap-1.5">
              {stats.players.map((player) => (
                <div key={player.user_id} className={`${COLUMNS} min-h-14 rounded-xl bg-dark-card px-3 py-1.5`}>
                  <span className="font-display text-sm font-semibold text-text-secondary">
                    {player.jersey_number ?? '—'}
                  </span>
                  <span className="min-w-0">
                    <span className="block truncate text-sm font-semibold">
                      {player.first_name} {player.last_name}
                    </span>
                    <span
                      className={`block truncate text-[11px] ${player.missing_reports > 0 ? 'text-accent-persimmon' : 'text-text-secondary'}`}
                    >
                      {player.missing_reports > 0
                        ? `не заполнил игр: ${player.missing_reports}`
                        : player.work_on !== null
                          ? `хочет: ${player.work_on.map((w) => GAME_WORK_ON_LABELS[w].toLowerCase()).join(', ')}`
                          : player.avg_self_rating !== null
                            ? `оценка себе ${player.avg_self_rating.toLocaleString('ru-RU')}`
                            : 'оценка скрыта'}
                    </span>
                  </span>
                  <span className="text-center font-display text-base font-semibold">{player.goals}</span>
                  <span className="text-center font-display text-base font-semibold">{player.assists}</span>
                  <span className="text-center font-display text-base font-semibold text-accent-ice">{player.points}</span>
                  <span className="text-center font-display text-base font-semibold">{player.shots}</span>
                </div>
              ))}
            </div>

            <div className="flex gap-2.5 rounded-xl bg-dark-card p-3 text-xs leading-relaxed text-text-secondary">
              <i className="ti ti-info-circle mt-0.5 text-sm" aria-hidden="true" />
              <p>
                Цифры игроки вносят сами после игры. Самооценку и «над чем поработать» видно, только если игрок
                разрешил.
              </p>
            </div>

            {missing > 0 && (
              <Button variant="neutral" onClick={() => void remind()} disabled={isReminding} className="w-full">
                Напомнить тем, кто не заполнил
              </Button>
            )}
            {remindState !== null && <p className="text-center text-sm text-text-secondary">{remindState}</p>}
          </>
        )}
      </div>
    </div>
  )
}
