import { useEffect, useRef, useState } from 'react'
import type { ChangeEvent } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { BackLink } from '../components/ui/BackLink'
import { Button } from '../components/ui/Button'
import { CARD_CLASS } from '../components/ui/cardStyle'
import { EmptyState } from '../components/ui/EmptyState'
import { FormError } from '../components/ui/FormError'
import { IceGlowBackground } from '../components/ui/IceGlowBackground'
import { RankBadge } from '../components/ui/RankBadge'
import { TabButton } from '../components/ui/TabButton'
import * as teamsApi from '../api/teams'
import { API_BASE_URL, ApiError } from '../api/client'
import { useAuth } from '../hooks/useAuth'
import type { LeaderboardEntryRead } from '../types/leaderboard'
import type { TeamJoinRequestRead, TeamMemberRead, TeamRead, TeamScoreRead } from '../types/team'
import { POSITION_LABELS } from '../types/user'
import { getDisplayName } from '../utils/displayName'

type DetailTab = 'members' | 'leaderboard' | 'requests'

// Mirrors TeamRatingService.MIN_MEMBERS_FOR_LEADERBOARD -- purely for the
// "N more needed" hint text below; the backend is the actual source of
// truth for who appears in GET /teams/leaderboard.
const MIN_MEMBERS_FOR_TEAM_RANKING = 8

function formatRatingExcess(value: number): string {
  const sign = value > 0 ? '+' : ''
  return `${sign}${value.toFixed(1)}`
}

function formatTeamScore(value: number): string {
  return value.toLocaleString('ru-RU', { maximumFractionDigits: 1 })
}

// navigator.clipboard is only defined in a secure context (https, or
// localhost) -- a phone hitting the dev server over plain http at the PC's
// LAN IP (see README) doesn't get it at all, so `handleCopyInviteCode`
// falls back to this old-but-universal execCommand trick rather than
// silently doing nothing.
function copyTextFallback(text: string): boolean {
  const textarea = document.createElement('textarea')
  textarea.value = text
  textarea.style.position = 'fixed'
  textarea.style.opacity = '0'
  document.body.appendChild(textarea)
  textarea.focus()
  textarea.select()
  let succeeded = false
  try {
    succeeded = document.execCommand('copy')
  } catch {
    succeeded = false
  }
  document.body.removeChild(textarea)
  return succeeded
}

export function TeamDetailPage() {
  const { teamId } = useParams<{ teamId: string }>()
  const navigate = useNavigate()
  const { accessToken } = useAuth()

  const [team, setTeam] = useState<TeamRead | null>(null)
  const [leaderboard, setLeaderboard] = useState<LeaderboardEntryRead[] | null>(null)
  const [pendingRequests, setPendingRequests] = useState<TeamJoinRequestRead[] | null>(null)
  const [teamScore, setTeamScore] = useState<TeamScoreRead | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)

  const [activeTab, setActiveTab] = useState<DetailTab>('members')

  const [actionError, setActionError] = useState<string | null>(null)
  const [isLeaving, setIsLeaving] = useState(false)
  const [isDisbanding, setIsDisbanding] = useState(false)
  const [decidingIds, setDecidingIds] = useState<Set<string>>(new Set())
  const [copied, setCopied] = useState(false)

  const [memberActionError, setMemberActionError] = useState<string | null>(null)
  const [actingMemberIds, setActingMemberIds] = useState<Set<string>>(new Set())

  const logoInputRef = useRef<HTMLInputElement>(null)
  const [isUploadingLogo, setIsUploadingLogo] = useState(false)
  const [logoError, setLogoError] = useState<string | null>(null)
  const [copyError, setCopyError] = useState<string | null>(null)

  useEffect(() => {
    if (accessToken === null || teamId === undefined) {
      return
    }
    let cancelled = false
    teamsApi
      .getTeam(teamId, accessToken)
      .then((result) => {
        if (cancelled) {
          return
        }
        setTeam(result)
        setLoadError(null)
        return Promise.all([
          teamsApi.getTeamLeaderboard(teamId, accessToken),
          result.is_captain
            ? teamsApi.listTeamJoinRequests(teamId, accessToken)
            : Promise.resolve<TeamJoinRequestRead[]>([]),
          teamsApi.getTeamScore(teamId, accessToken),
        ])
      })
      .then((extra) => {
        if (cancelled || extra === undefined) {
          return
        }
        const [leaderboardResult, requestsResult, scoreResult] = extra
        setLeaderboard(leaderboardResult)
        setPendingRequests(requestsResult)
        setTeamScore(scoreResult)
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setLoadError(err instanceof ApiError ? err.message : 'Не удалось загрузить команду.')
        }
      })
    return () => {
      cancelled = true
    }
  }, [accessToken, teamId])

  async function handleLogoChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    // Reset so selecting the same file again still fires onChange.
    event.target.value = ''
    if (file === undefined || accessToken === null || team === null) {
      return
    }
    setLogoError(null)
    setIsUploadingLogo(true)
    try {
      const updated = await teamsApi.uploadTeamLogo(team.id, file, accessToken)
      setTeam(updated)
    } catch (err) {
      setLogoError(err instanceof ApiError ? err.message : 'Не удалось загрузить эмблему.')
    } finally {
      setIsUploadingLogo(false)
    }
  }

  async function handleCopyInviteCode() {
    if (team === null) {
      return
    }
    setCopyError(null)
    let succeeded = false
    if (navigator.clipboard !== undefined && window.isSecureContext) {
      try {
        await navigator.clipboard.writeText(team.invite_code)
        succeeded = true
      } catch {
        succeeded = false
      }
    }
    if (!succeeded) {
      succeeded = copyTextFallback(team.invite_code)
    }
    if (succeeded) {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } else {
      setCopyError('Не удалось скопировать — выделите код вручную.')
    }
  }

  async function handleLeave() {
    if (accessToken === null || team === null) {
      return
    }
    if (!window.confirm(`Покинуть команду «${team.name}»?`)) {
      return
    }
    setActionError(null)
    setIsLeaving(true)
    try {
      await teamsApi.leaveTeam(team.id, accessToken)
      navigate('/teams', { replace: true })
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : 'Не удалось покинуть команду.')
    } finally {
      setIsLeaving(false)
    }
  }

  async function handleDisband() {
    if (accessToken === null || team === null) {
      return
    }
    if (!window.confirm(`Расформировать команду «${team.name}»? Это действие необратимо.`)) {
      return
    }
    setActionError(null)
    setIsDisbanding(true)
    try {
      await teamsApi.disbandTeam(team.id, accessToken)
      navigate('/teams', { replace: true })
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : 'Не удалось расформировать команду.')
    } finally {
      setIsDisbanding(false)
    }
  }

  async function handleDecide(request: TeamJoinRequestRead, approve: boolean) {
    if (accessToken === null || decidingIds.has(request.id)) {
      return
    }
    setDecidingIds((previous) => new Set(previous).add(request.id))
    try {
      if (approve) {
        await teamsApi.approveJoinRequest(request.id, accessToken)
      } else {
        await teamsApi.rejectJoinRequest(request.id, accessToken)
      }
      setPendingRequests((previous) => previous?.filter((r) => r.id !== request.id) ?? previous)
      if (approve && teamId !== undefined) {
        // A newly-approved member changes member_count, which feeds both the
        // internal leaderboard's roster and team_score's sum_xp/8-member gate.
        const [refreshedTeam, refreshedLeaderboard, refreshedScore] = await Promise.all([
          teamsApi.getTeam(teamId, accessToken),
          teamsApi.getTeamLeaderboard(teamId, accessToken),
          teamsApi.getTeamScore(teamId, accessToken),
        ])
        setTeam(refreshedTeam)
        setLeaderboard(refreshedLeaderboard)
        setTeamScore(refreshedScore)
      }
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : 'Не удалось обработать заявку.')
    } finally {
      setDecidingIds((previous) => {
        const next = new Set(previous)
        next.delete(request.id)
        return next
      })
    }
  }

  async function handleKickMember(member: TeamMemberRead) {
    if (accessToken === null || team === null || actingMemberIds.has(member.id)) {
      return
    }
    if (!window.confirm(`Исключить ${getDisplayName(member)} из команды?`)) {
      return
    }
    setMemberActionError(null)
    setActingMemberIds((previous) => new Set(previous).add(member.id))
    try {
      await teamsApi.kickMember(team.id, member.id, accessToken)
      // Removing a member changes member_count, same downstream effects as
      // approving a join request above.
      const [refreshedTeam, refreshedLeaderboard, refreshedScore] = await Promise.all([
        teamsApi.getTeam(team.id, accessToken),
        teamsApi.getTeamLeaderboard(team.id, accessToken),
        teamsApi.getTeamScore(team.id, accessToken),
      ])
      setTeam(refreshedTeam)
      setLeaderboard(refreshedLeaderboard)
      setTeamScore(refreshedScore)
    } catch (err) {
      setMemberActionError(err instanceof ApiError ? err.message : 'Не удалось исключить участника.')
    } finally {
      setActingMemberIds((previous) => {
        const next = new Set(previous)
        next.delete(member.id)
        return next
      })
    }
  }

  async function handleTransferCaptaincy(member: TeamMemberRead) {
    if (accessToken === null || team === null || actingMemberIds.has(member.id)) {
      return
    }
    if (
      !window.confirm(
        `Передать капитанство «${getDisplayName(member)}»? Вы станете обычным участником команды.`,
      )
    ) {
      return
    }
    setMemberActionError(null)
    setActingMemberIds((previous) => new Set(previous).add(member.id))
    try {
      const updated = await teamsApi.transferCaptaincy(team.id, { user_id: member.id }, accessToken)
      setTeam(updated)
    } catch (err) {
      setMemberActionError(err instanceof ApiError ? err.message : 'Не удалось передать капитанство.')
    } finally {
      setActingMemberIds((previous) => {
        const next = new Set(previous)
        next.delete(member.id)
        return next
      })
    }
  }

  const isLoading =
    team === null || leaderboard === null || pendingRequests === null || teamScore === null
  // A non-captain never sees the "requests" tab -- if it were somehow left
  // active (shouldn't happen, no captain-only actions toggle team.is_captain
  // client-side) fall back to the one tab everyone always has.
  const effectiveTab = activeTab === 'requests' && team?.is_captain !== true ? 'members' : activeTab

  return (
    <div className="relative min-h-svh overflow-hidden">
      <IceGlowBackground />
      <div className="relative z-[1] mx-auto flex max-w-2xl flex-col gap-6 px-4 py-8">
        <BackLink />

        <FormError message={loadError} />
        {isLoading && loadError === null && <p className="text-sm text-[#8A94A6]">Загрузка...</p>}

        {!isLoading && (
          <>
            <div className={`flex flex-col gap-3 p-4 ${CARD_CLASS}`}>
              <div className="flex items-center gap-3">
                <div className="relative shrink-0">
                  <div className="relative flex h-14 w-14 items-center justify-center overflow-hidden rounded-full border border-white/10 bg-dark-bg">
                    {team.logo_url != null ? (
                      <img
                        src={`${API_BASE_URL}${team.logo_url}`}
                        alt=""
                        className="h-full w-full object-cover"
                      />
                    ) : (
                      <i className="ti ti-shield text-2xl text-[#8A94A6]" aria-hidden="true" />
                    )}
                    {isUploadingLogo && (
                      <div className="absolute inset-0 flex items-center justify-center bg-black/60">
                        <i className="ti ti-loader-2 animate-spin text-xl text-[#F5F7FA]" aria-hidden="true" />
                      </div>
                    )}
                  </div>
                  {team.is_captain && (
                    <>
                      <button
                        type="button"
                        onClick={() => logoInputRef.current?.click()}
                        disabled={isUploadingLogo}
                        aria-label="Изменить эмблему команды"
                        className="absolute -bottom-1 -right-1 flex h-6 w-6 items-center justify-center rounded-full border-2 border-dark-bg bg-accent-ice text-dark-bg transition-opacity hover:opacity-90 disabled:cursor-wait"
                      >
                        <i className="ti ti-camera text-xs" aria-hidden="true" />
                      </button>
                      <input
                        ref={logoInputRef}
                        type="file"
                        accept="image/*"
                        className="hidden"
                        onChange={handleLogoChange}
                      />
                    </>
                  )}
                </div>
                <h1 className="min-w-0 flex-1 truncate text-lg font-semibold text-[#F5F7FA]">{team.name}</h1>
              </div>
              <FormError message={logoError} />

              <div className="flex items-center justify-between gap-3 border-t border-white/5 pt-3">
                <div className="flex flex-col gap-0.5">
                  <span className="text-[10px] uppercase tracking-wide text-[#8A94A6]">Код приглашения</span>
                  <span className="font-mono text-sm text-[#F5F7FA]">{team.invite_code}</span>
                </div>
                <Button
                  type="button"
                  variant="neutral"
                  onClick={handleCopyInviteCode}
                  className="shrink-0 !px-3 !py-1.5 !text-xs"
                >
                  {copied ? 'Скопировано' : 'Копировать'}
                </Button>
              </div>
              <FormError message={copyError} />
            </div>

            <div className={`relative flex flex-col gap-2 overflow-hidden p-4 ${CARD_CLASS}`}>
              <div
                className="pointer-events-none absolute -right-8 -top-10 h-32 w-32 rounded-full"
                style={{
                  background: 'radial-gradient(circle, rgba(215,239,255,0.12) 0%, rgba(215,239,255,0) 70%)',
                }}
                aria-hidden="true"
              />
              <div className="relative flex items-center justify-between gap-3">
                <span className="text-xs font-medium uppercase tracking-wide text-[#8A94A6]">
                  Рейтинг команды
                </span>
                <span className="font-display text-2xl font-extrabold text-accent-ice">
                  {formatTeamScore(teamScore.team_score)}
                </span>
              </div>
              <span className="relative text-xs text-[#8A94A6]">
                Сумма XP {teamScore.sum_xp} × бонус за активность{' '}
                {(teamScore.activity_bonus * 100).toFixed(1)}% (
                {teamScore.avg_trainings_per_member_per_week.toFixed(1)} трен./нед на чел.)
              </span>
              {teamScore.member_count < MIN_MEMBERS_FOR_TEAM_RANKING && (
                <span className="relative text-xs text-[#8A94A6]">
                  Нужно ещё {MIN_MEMBERS_FOR_TEAM_RANKING - teamScore.member_count}{' '}
                  {MIN_MEMBERS_FOR_TEAM_RANKING - teamScore.member_count === 1 ? 'участник' : 'участников'},
                  чтобы попасть в общий рейтинг команд.
                </span>
              )}
            </div>

            <div className="flex flex-col gap-4">
              <div className="flex border-b border-white/10">
                <TabButton active={effectiveTab === 'members'} onClick={() => setActiveTab('members')}>
                  Участники
                </TabButton>
                <TabButton active={effectiveTab === 'leaderboard'} onClick={() => setActiveTab('leaderboard')}>
                  Рейтинг
                </TabButton>
                {team.is_captain && (
                  <TabButton
                    active={effectiveTab === 'requests'}
                    onClick={() => setActiveTab('requests')}
                    badge={pendingRequests.length}
                  >
                    Заявки
                  </TabButton>
                )}
              </div>

              {effectiveTab === 'members' && (
                <div className="flex flex-col gap-2">
                  {team.members.map((member) => (
                    <MemberRow
                      key={member.id}
                      member={member}
                      canManage={team.is_captain && !member.is_captain}
                      isBusy={actingMemberIds.has(member.id)}
                      onKick={() => handleKickMember(member)}
                      onTransferCaptaincy={() => handleTransferCaptaincy(member)}
                    />
                  ))}
                  <FormError message={memberActionError} />
                </div>
              )}

              {effectiveTab === 'leaderboard' &&
                (leaderboard.length === 0 ? (
                  <EmptyState
                    icon="ti-trophy"
                    title="Пока никто из участников не попал в рейтинг"
                    hint="Рейтинг появится, как только у участников накопится статистика"
                  />
                ) : (
                  <div className="flex flex-col gap-2">
                    {leaderboard.map((entry, index) => (
                      <div key={entry.id} className={`flex items-center gap-3 p-3 ${CARD_CLASS}`}>
                        <RankBadge rank={index + 1} />
                        <span className="min-w-0 flex-1 truncate text-sm text-[#F5F7FA]">
                          {getDisplayName(entry)}
                        </span>
                        <span
                          className={`shrink-0 font-mono text-sm font-bold ${
                            entry.rating_excess > 0 ? 'text-accent-ice' : 'text-[#8A94A6]'
                          }`}
                        >
                          {formatRatingExcess(entry.rating_excess)}
                        </span>
                      </div>
                    ))}
                  </div>
                ))}

              {effectiveTab === 'requests' && team.is_captain && (
                <div className="flex flex-col gap-2">
                  {pendingRequests.length === 0 && (
                    <EmptyState icon="ti-mail" title="Нет заявок на вступление" />
                  )}
                  {pendingRequests.map((request) => (
                    <div
                      key={request.id}
                      className={`flex items-center justify-between gap-4 p-4 ${CARD_CLASS}`}
                    >
                      <span className="min-w-0 truncate text-sm text-[#F5F7FA]">
                        {getDisplayName(request)}
                      </span>
                      <div className="flex shrink-0 gap-2">
                        <Button
                          type="button"
                          isLoading={decidingIds.has(request.id)}
                          onClick={() => handleDecide(request, true)}
                          className="!px-3 !py-1.5 !text-xs"
                        >
                          Принять
                        </Button>
                        <Button
                          type="button"
                          variant="neutral"
                          disabled={decidingIds.has(request.id)}
                          onClick={() => handleDecide(request, false)}
                          className="!px-3 !py-1.5 !text-xs"
                        >
                          Отклонить
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <FormError message={actionError} />

            <div className="flex flex-col gap-2">
              {team.is_captain ? (
                <>
                  <p className="text-xs text-[#8A94A6]">
                    Капитан не может покинуть команду — сначала расформируйте её.
                  </p>
                  <Button
                    type="button"
                    variant="neutral"
                    isLoading={isDisbanding}
                    onClick={handleDisband}
                    className="self-start"
                  >
                    Расформировать команду
                  </Button>
                </>
              ) : (
                <Button
                  type="button"
                  variant="neutral"
                  isLoading={isLeaving}
                  onClick={handleLeave}
                  className="self-start"
                >
                  Покинуть команду
                </Button>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  )
}

function MemberRow({
  member,
  canManage,
  isBusy,
  onKick,
  onTransferCaptaincy,
}: {
  member: TeamMemberRead
  canManage: boolean
  isBusy: boolean
  onKick: () => void
  onTransferCaptaincy: () => void
}) {
  const navigate = useNavigate()
  return (
    <div className={`flex items-center gap-3 p-3 ${CARD_CLASS}`}>
      <button
        type="button"
        onClick={() => navigate(`/profile/${member.id}`)}
        className="flex min-w-0 flex-1 flex-col text-left"
      >
        <span className="truncate text-sm font-medium text-[#F5F7FA]">{getDisplayName(member)}</span>
        <span className="text-xs text-[#8A94A6]">
          {[
            member.position !== null ? POSITION_LABELS[member.position] : null,
            member.jersey_number !== null ? `№${member.jersey_number}` : null,
          ]
            .filter(Boolean)
            .join(' · ')}
        </span>
      </button>
      {member.is_captain && (
        <span className="shrink-0 rounded-full bg-accent-ice/15 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-accent-ice">
          Капитан
        </span>
      )}
      {canManage && (
        <div className="flex shrink-0 items-center gap-1">
          <button
            type="button"
            onClick={onTransferCaptaincy}
            disabled={isBusy}
            aria-label={`Передать капитанство: ${getDisplayName(member)}`}
            className="flex h-7 w-7 items-center justify-center rounded-full text-[#8A94A6] transition-colors hover:bg-white/5 hover:text-accent-ice disabled:cursor-not-allowed disabled:opacity-50"
          >
            <i className="ti ti-crown text-sm" aria-hidden="true" />
          </button>
          <button
            type="button"
            onClick={onKick}
            disabled={isBusy}
            aria-label={`Исключить из команды: ${getDisplayName(member)}`}
            className="flex h-7 w-7 items-center justify-center rounded-full text-[#8A94A6] transition-colors hover:bg-white/5 hover:text-accent-persimmon disabled:cursor-not-allowed disabled:opacity-50"
          >
            <i className="ti ti-user-x text-sm" aria-hidden="true" />
          </button>
        </div>
      )}
    </div>
  )
}
