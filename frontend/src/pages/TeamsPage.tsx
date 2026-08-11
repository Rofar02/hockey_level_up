import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { BackLink } from '../components/ui/BackLink'
import { Button } from '../components/ui/Button'
import { FormError } from '../components/ui/FormError'
import { IceGlowBackground } from '../components/ui/IceGlowBackground'
import { TabButton } from '../components/ui/TabButton'
import { TextField } from '../components/ui/TextField'
import * as teamsApi from '../api/teams'
import { API_BASE_URL, ApiError } from '../api/client'
import { useAuth } from '../hooks/useAuth'
import type { TeamJoinRequestRead, TeamSummaryRead } from '../types/team'

// Same icy top-border card convention as Home/Profile/TrainingSession.
const CARD_CLASS = 'rounded-md border-t border-[rgba(215,239,255,0.35)] bg-dark-card'

type TeamsTab = 'mine' | 'create' | 'join'

export function TeamsPage() {
  const navigate = useNavigate()
  const { accessToken } = useAuth()

  const [activeTab, setActiveTab] = useState<TeamsTab>('mine')

  const [teams, setTeams] = useState<TeamSummaryRead[] | null>(null)
  const [requests, setRequests] = useState<TeamJoinRequestRead[] | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)

  const [createName, setCreateName] = useState('')
  const [isCreating, setIsCreating] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)

  const [joinCode, setJoinCode] = useState('')
  const [isJoining, setIsJoining] = useState(false)
  const [joinError, setJoinError] = useState<string | null>(null)

  const [cancelingIds, setCancelingIds] = useState<Set<string>>(new Set())

  useEffect(() => {
    if (accessToken === null) {
      return
    }
    let cancelled = false
    Promise.all([teamsApi.listMyTeams(accessToken), teamsApi.listMyJoinRequests(accessToken)])
      .then(([teamsResult, requestsResult]) => {
        if (!cancelled) {
          setTeams(teamsResult)
          setRequests(requestsResult)
          setLoadError(null)
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setLoadError(err instanceof ApiError ? err.message : 'Не удалось загрузить команды.')
        }
      })
    return () => {
      cancelled = true
    }
  }, [accessToken])

  async function refresh() {
    if (accessToken === null) {
      return
    }
    const [teamsResult, requestsResult] = await Promise.all([
      teamsApi.listMyTeams(accessToken),
      teamsApi.listMyJoinRequests(accessToken),
    ])
    setTeams(teamsResult)
    setRequests(requestsResult)
  }

  async function handleCreate(event: FormEvent) {
    event.preventDefault()
    if (accessToken === null || createName.trim() === '') {
      return
    }
    setCreateError(null)
    setIsCreating(true)
    try {
      const created = await teamsApi.createTeam({ name: createName.trim() }, accessToken)
      navigate(`/teams/${created.id}`)
    } catch (err) {
      setCreateError(err instanceof ApiError ? err.message : 'Не удалось создать команду.')
    } finally {
      setIsCreating(false)
    }
  }

  async function handleJoin(event: FormEvent) {
    event.preventDefault()
    if (accessToken === null || joinCode.trim() === '') {
      return
    }
    setJoinError(null)
    setIsJoining(true)
    try {
      await teamsApi.joinTeam({ code: joinCode.trim().toUpperCase() }, accessToken)
      setJoinCode('')
      await refresh()
      // Land back on "Мои команды" so the freshly-sent request's "на
      // рассмотрении" status is immediately visible, rather than leaving
      // the athlete staring at the now-empty join form.
      setActiveTab('mine')
    } catch (err) {
      setJoinError(err instanceof ApiError ? err.message : 'Не удалось отправить заявку.')
    } finally {
      setIsJoining(false)
    }
  }

  async function handleCancelRequest(requestId: string) {
    if (accessToken === null || cancelingIds.has(requestId)) {
      return
    }
    setCancelingIds((previous) => new Set(previous).add(requestId))
    try {
      await teamsApi.cancelJoinRequest(requestId, accessToken)
      setRequests((previous) => previous?.filter((request) => request.id !== requestId) ?? previous)
    } catch {
      // Best-effort -- worst case the request just stays in the list until
      // a manual refresh, no need to surface a banner for a cancel click.
    } finally {
      setCancelingIds((previous) => {
        const next = new Set(previous)
        next.delete(requestId)
        return next
      })
    }
  }

  const isLoading = teams === null || requests === null

  return (
    <div className="relative min-h-svh overflow-hidden">
      <IceGlowBackground />
      <div className="relative z-[1] mx-auto flex max-w-2xl flex-col gap-6 px-4 py-8">
        <div className="flex flex-col gap-2">
          <BackLink />
          <h1 className="text-xl font-semibold">Команды</h1>
        </div>

        <FormError message={loadError} />
        {isLoading && loadError === null && <p className="text-sm text-[#8A94A6]">Загрузка...</p>}

        {!isLoading && (
          <>
            <div className="flex border-b border-white/10">
              <TabButton active={activeTab === 'mine'} onClick={() => setActiveTab('mine')} badge={requests.length}>
                Мои команды
              </TabButton>
              <TabButton active={activeTab === 'create'} onClick={() => setActiveTab('create')}>
                Создать
              </TabButton>
              <TabButton active={activeTab === 'join'} onClick={() => setActiveTab('join')}>
                Вступить по коду
              </TabButton>
            </div>

            {activeTab === 'mine' && (
              <div className="flex flex-col gap-6">
                <div className="flex flex-col gap-2">
                  {teams.length === 0 && (
                    <p className="text-sm text-[#8A94A6]">Вы пока не состоите ни в одной команде.</p>
                  )}
                  {teams.map((team) => (
                    <button
                      key={team.id}
                      type="button"
                      onClick={() => navigate(`/teams/${team.id}`)}
                      className={`flex w-full items-center gap-3 p-4 text-left transition-colors hover:border-white/20 ${CARD_CLASS}`}
                    >
                      <div className="flex h-10 w-10 shrink-0 items-center justify-center overflow-hidden rounded-full border border-white/10 bg-dark-bg">
                        {team.logo_url !== null ? (
                          <img
                            src={`${API_BASE_URL}${team.logo_url}`}
                            alt=""
                            className="h-full w-full object-cover"
                          />
                        ) : (
                          <i className="ti ti-shield text-lg text-[#8A94A6]" aria-hidden="true" />
                        )}
                      </div>
                      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
                        <span className="truncate text-sm font-medium text-[#F5F7FA]">{team.name}</span>
                        <span className="text-xs text-[#8A94A6]">
                          {team.member_count} {team.member_count === 1 ? 'участник' : 'участников'}
                        </span>
                      </div>
                      {team.is_captain && (
                        <span className="shrink-0 rounded-full bg-accent-ice/15 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-accent-ice">
                          Капитан
                        </span>
                      )}
                    </button>
                  ))}
                </div>

                {requests.length > 0 && (
                  <div className="flex flex-col gap-2">
                    <p className="text-xs font-medium uppercase tracking-wide text-[#8A94A6]">Мои заявки</p>
                    {requests.map((request) => (
                      <div
                        key={request.id}
                        className={`flex items-center justify-between gap-4 p-4 ${CARD_CLASS}`}
                      >
                        <span className="min-w-0 flex-1 truncate text-sm text-[#F5F7FA]">
                          Заявка в «{request.team_name}» на рассмотрении
                        </span>
                        <Button
                          type="button"
                          variant="neutral"
                          isLoading={cancelingIds.has(request.id)}
                          onClick={() => handleCancelRequest(request.id)}
                          className="shrink-0 !px-3 !py-1.5 !text-xs"
                        >
                          Отменить
                        </Button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {activeTab === 'create' && (
              <div className="flex flex-col gap-3">
                <form onSubmit={handleCreate} className="flex flex-col gap-3 sm:flex-row sm:items-end">
                  <TextField
                    label="Название"
                    value={createName}
                    onChange={(event) => setCreateName(event.target.value)}
                    maxLength={100}
                    className="flex-1"
                  />
                  <Button type="submit" isLoading={isCreating} disabled={createName.trim() === ''}>
                    Создать
                  </Button>
                </form>
                <FormError message={createError} />
              </div>
            )}

            {activeTab === 'join' && (
              <div className="flex flex-col gap-3">
                <form onSubmit={handleJoin} className="flex flex-col gap-3 sm:flex-row sm:items-end">
                  <TextField
                    label="Код приглашения"
                    value={joinCode}
                    onChange={(event) => setJoinCode(event.target.value)}
                    maxLength={16}
                    className="flex-1 uppercase"
                  />
                  <Button
                    type="submit"
                    variant="neutral"
                    isLoading={isJoining}
                    disabled={joinCode.trim() === ''}
                  >
                    Отправить заявку
                  </Button>
                </form>
                <FormError message={joinError} />
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
