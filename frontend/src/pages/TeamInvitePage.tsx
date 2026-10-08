import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import * as teamsApi from '../api/teams'
import { API_BASE_URL, ApiError } from '../api/client'
import { Button } from '../components/ui/Button'
import { FormError } from '../components/ui/FormError'
import { IceGlowBackground } from '../components/ui/IceGlowBackground'
import { useAuth } from '../hooks/useAuth'
import type { TeamInvitePreviewRead } from '../types/team'
import { savePendingTeamCode, teamJoinErrorText } from '../utils/pendingFriendInvite'

// /t/:code -- a team's invite link (2026-10-08). Open to anyone: the team
// and one button. "Вступить" is the usual join request the captain
// approves; without an account the code waits until there is one
// (PendingFriendInvite sends it).
export function TeamInvitePage() {
  const { code = '' } = useParams<{ code: string }>()
  const navigate = useNavigate()
  const { isAuthenticated, isInitializing, accessToken } = useAuth()
  const [team, setTeam] = useState<TeamInvitePreviewRead | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [isSending, setIsSending] = useState(false)
  const [sent, setSent] = useState(false)
  const [sendError, setSendError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    teamsApi
      .getTeamInvite(code)
      .then((found) => !cancelled && setTeam(found))
      .catch((err: unknown) => {
        if (!cancelled) {
          setLoadError(err instanceof ApiError ? err.message : 'Не удалось открыть приглашение.')
        }
      })
    return () => {
      cancelled = true
    }
  }, [code])

  async function join() {
    if (accessToken === null) {
      return
    }
    setSendError(null)
    setIsSending(true)
    try {
      await teamsApi.joinTeam({ code }, accessToken)
      setSent(true)
    } catch (err) {
      setSendError(err instanceof ApiError ? teamJoinErrorText(err.message) : 'Не удалось отправить заявку.')
    } finally {
      setIsSending(false)
    }
  }

  function goWithAccount(path: '/register' | '/login') {
    savePendingTeamCode(code)
    navigate(path)
  }

  return (
    <div className="relative min-h-svh overflow-hidden">
      <IceGlowBackground />
      <div className="relative z-[1] mx-auto flex min-h-svh max-w-md flex-col items-center gap-5 px-4 pb-8 pt-10">
        <span className="font-display text-[15px] font-bold uppercase tracking-[2px] text-accent-ice">IceLevel</span>
        <FormError message={loadError} />
        {team === null && loadError === null && <p className="text-sm text-text-secondary">Загрузка...</p>}

        {team !== null && (
          <>
            <div className="mt-6 flex flex-col items-center gap-4 text-center">
              <span className="flex h-28 w-28 items-center justify-center overflow-hidden rounded-full border-2 border-accent-ice/40 bg-dark-card text-accent-ice shadow-[0_0_40px_rgba(215,239,255,0.15)]">
                {team.logo_url !== null ? (
                  <img src={`${API_BASE_URL}${team.logo_url}`} alt="" className="h-full w-full object-cover" />
                ) : (
                  <i className="ti ti-shield text-5xl" aria-hidden="true" />
                )}
              </span>
              <p className="text-sm text-text-secondary">Тебя зовут в команду</p>
              <h1 className="text-balance font-display text-3xl font-bold uppercase tracking-wide">{team.name}</h1>
              <p className="text-sm text-text-secondary">
                Капитан {team.captain_first_name} {team.captain_last_name} · {team.member_count} участн.
              </p>
            </div>

            <ul className="flex w-full flex-col gap-2 rounded-2xl bg-dark-card p-4 text-[13px] leading-relaxed text-text-secondary">
              <li className="flex gap-2.5">
                <i className="ti ti-calendar-event mt-0.5 text-accent-ice" aria-hidden="true" />
                Тренировки и игры команды встают в твой план сами
              </li>
              <li className="flex gap-2.5">
                <i className="ti ti-chalkboard mt-0.5 text-accent-ice" aria-hidden="true" />
                Схемы и планы тренера — на интерактивной доске
              </li>
              <li className="flex gap-2.5">
                <i className="ti ti-trophy mt-0.5 text-accent-ice" aria-hidden="true" />
                Общий рейтинг и статистика сезона
              </li>
            </ul>

            <div className="mt-auto flex w-full flex-col gap-2.5">
              {isInitializing ? null : isAuthenticated ? (
                sent ? (
                  <>
                    <p className="text-center text-sm text-accent-ice">
                      Заявка отправлена — капитан увидит её и примет
                    </p>
                    <Link to="/team" className="text-center text-sm font-medium text-text-secondary">
                      К команде
                    </Link>
                  </>
                ) : (
                  <>
                    <Button type="button" onClick={() => void join()} isLoading={isSending} className="w-full">
                      Вступить в команду
                    </Button>
                    <FormError message={sendError} />
                  </>
                )
              ) : (
                <>
                  <Button type="button" onClick={() => goWithAccount('/register')} className="w-full">
                    Создать аккаунт и вступить
                  </Button>
                  <Button type="button" variant="neutral" onClick={() => goWithAccount('/login')} className="w-full">
                    У меня есть аккаунт — войти
                  </Button>
                  <p className="text-center text-xs leading-relaxed text-text-secondary">
                    После входа заявка уйдёт капитану сама — останется дождаться, когда он её примет.
                  </p>
                </>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  )
}
