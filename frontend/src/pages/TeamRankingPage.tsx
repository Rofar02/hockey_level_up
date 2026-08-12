import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { BackLink } from '../components/ui/BackLink'
import { FormError } from '../components/ui/FormError'
import { IceGlowBackground } from '../components/ui/IceGlowBackground'
import * as teamsApi from '../api/teams'
import { ApiError } from '../api/client'
import { useAuth } from '../hooks/useAuth'
import type { TeamScoreRead } from '../types/team'

// Same icy top-border card convention as TeamsPage/TeamDetailPage/Leaderboard.
const CARD_CLASS = 'rounded-md border-t border-[rgba(215,239,255,0.35)] bg-dark-card'

function formatScore(value: number): string {
  return value.toLocaleString('ru-RU', { maximumFractionDigits: 1 })
}

export function TeamRankingPage() {
  const navigate = useNavigate()
  const { accessToken } = useAuth()

  const [rankings, setRankings] = useState<TeamScoreRead[] | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)

  useEffect(() => {
    if (accessToken === null) {
      return
    }
    let cancelled = false
    teamsApi
      .getTeamRankings(accessToken)
      .then((result) => {
        if (!cancelled) {
          setRankings(result)
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setLoadError(err instanceof ApiError ? err.message : 'Не удалось загрузить рейтинг команд.')
        }
      })
    return () => {
      cancelled = true
    }
  }, [accessToken])

  return (
    <div className="relative min-h-svh overflow-hidden">
      <IceGlowBackground />
      <div className="relative z-[1] mx-auto flex max-w-2xl flex-col gap-6 px-4 py-8">
        <div className="flex flex-col gap-2">
          <BackLink to="/teams" />
          <h1 className="text-xl font-semibold">Рейтинг команд</h1>
          <p className="text-sm text-[#8A94A6]">
            Сумма XP участников с бонусом за активность. Команды младше 8 человек в топ не попадают.
          </p>
        </div>

        <FormError message={loadError} />
        {rankings === null && loadError === null && (
          <p className="text-sm text-[#8A94A6]">Загрузка...</p>
        )}

        {rankings !== null && (
          <div className="flex flex-col gap-2">
            {rankings.map((team, index) => (
              <button
                key={team.team_id}
                type="button"
                onClick={() => navigate(`/teams/${team.team_id}`)}
                className={`flex w-full items-center gap-3 p-3 text-left transition-colors hover:border-white/20 ${CARD_CLASS}`}
              >
                <span className="w-8 shrink-0 text-center font-mono text-sm text-[#8A94A6]">
                  {index + 1}
                </span>
                <div className="flex min-w-0 flex-1 flex-col">
                  <span className="truncate text-sm font-medium text-[#F5F7FA]">{team.team_name}</span>
                  <span className="text-xs text-[#8A94A6]">
                    {team.member_count} участников · {team.avg_trainings_per_member_per_week.toFixed(1)}{' '}
                    трен./нед на чел.
                  </span>
                </div>
                <span className="shrink-0 font-mono text-sm font-bold text-accent-ice">
                  {formatScore(team.team_score)}
                </span>
              </button>
            ))}

            {rankings.length === 0 && (
              <p className="text-sm text-[#8A94A6]">
                Пока ни одна команда не набрала 8 участников для попадания в рейтинг.
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
