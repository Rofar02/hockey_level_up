import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { CARD_CLASS } from '../components/ui/cardStyle'
import { CardGlow } from '../components/ui/CardGlow'
import { IceGlowBackground } from '../components/ui/IceGlowBackground'
import { NextEventCard } from '../components/teamEvents/NextEventCard'
import * as friendsApi from '../api/friends'
import * as leaderboardApi from '../api/leaderboard'
import * as teamsApi from '../api/teams'
import * as usersApi from '../api/users'
import { API_BASE_URL } from '../api/client'
import { useAuth } from '../hooks/useAuth'
import type { ActivityFeedEntryRead } from '../types/friendActivity'
import type { LeaderboardMeRead } from '../types/leaderboard'
import { DAY_SESSION_TYPE_LABELS } from '../types/schedule'
import type { TeamRead, TeamScoreRead, TeamSummaryRead } from '../types/team'
import type { TeamAttentionRead } from '../types/user'
import { formatDateTime } from '../utils/date'
import { copyText } from '../utils/clipboard'
import { ListSkeleton } from '../components/ui/Skeleton'

// The "Команда" tab: the player's team up top (next event, schedule,
// ranking, invite code), then the friends side -- activity feed, joint
// trainings, the player leaderboard. Everything here links into the
// existing detail screens; this page only gathers the entry points that
// used to sit two or three taps deep under "Ещё".

const FEED_PREVIEW_SIZE = 3

function feedText(entry: ActivityFeedEntryRead): string {
  if (entry.event_type === 'level_up') {
    return `достиг ${entry.level} уровня`
  }
  if (entry.event_type === 'party_completed') {
    const others = (entry.party_size ?? 2) - 1
    return `потренировался вместе с ${others} ${others === 1 ? 'другом' : 'друзьями'}`
  }
  const label = entry.session_type !== null ? DAY_SESSION_TYPE_LABELS[entry.session_type].toLowerCase() : 'тренировку'
  return `завершил тренировку: ${label}`
}

export function TeamHubPage() {
  const { accessToken } = useAuth()
  const [teams, setTeams] = useState<TeamSummaryRead[] | null>(null)
  const [selectedTeamId, setSelectedTeamId] = useState<string | null>(null)
  const [team, setTeam] = useState<TeamRead | null>(null)
  const [score, setScore] = useState<TeamScoreRead | null>(null)
  const [feed, setFeed] = useState<ActivityFeedEntryRead[] | null>(null)
  const [hasFriends, setHasFriends] = useState<boolean | null>(null)
  const [leaderboardMe, setLeaderboardMe] = useState<LeaderboardMeRead | null>(null)
  const [copied, setCopied] = useState(false)
  const [attention, setAttention] = useState<TeamAttentionRead | null>(null)

  useEffect(() => {
    if (accessToken === null) {
      return
    }
    let cancelled = false
    teamsApi
      .listMyTeams(accessToken)
      .then((result) => {
        if (!cancelled) {
          setTeams(result)
          setSelectedTeamId(result[0]?.id ?? null)
        }
      })
      .catch(() => {
        if (!cancelled) {
          setTeams([])
        }
      })
    friendsApi
      .getFriendActivityFeed(accessToken)
      .then((result) => !cancelled && setFeed(result))
      .catch(() => !cancelled && setFeed([]))
    friendsApi
      .listFriends(accessToken)
      .then((result) => !cancelled && setHasFriends(result.length > 0))
      .catch(() => !cancelled && setHasFriends(false))
    usersApi
      .getTeamAttention(accessToken)
      .then((result) => !cancelled && setAttention(result))
      .catch(() => {})
    leaderboardApi
      .getMyLeaderboardPosition(accessToken)
      .then((result) => !cancelled && setLeaderboardMe(result))
      .catch(() => {
        // Not ranked yet -- the tile just drops the position line.
      })
    return () => {
      cancelled = true
    }
  }, [accessToken])

  useEffect(() => {
    if (accessToken === null || selectedTeamId === null) {
      return
    }
    let cancelled = false
    setTeam(null)
    setScore(null)
    teamsApi
      .getTeam(selectedTeamId, accessToken)
      .then((result) => !cancelled && setTeam(result))
      .catch(() => {})
    teamsApi
      .getTeamScore(selectedTeamId, accessToken)
      .then((result) => !cancelled && setScore(result))
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [accessToken, selectedTeamId])

  async function handleCopyInviteCode() {
    if (team === null) {
      return
    }
    if (await copyText(team.invite_code)) {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  const teamPath = selectedTeamId !== null ? `/teams/${selectedTeamId}` : '/teams'
  const captainTeamId = teams?.find((item) => item.is_captain)?.id ?? null
  const waiting = [
    attention !== null && attention.friend_requests > 0
      ? { key: 'friends', icon: 'ti-user-plus', text: `Заявки в друзья: ${attention.friend_requests}`, to: '/friends' }
      : null,
    attention !== null && attention.party_invites > 0
      ? {
          key: 'parties',
          icon: 'ti-users-group',
          text: `Зовут потренироваться: ${attention.party_invites}`,
          to: '/training-parties?tab=invites',
        }
      : null,
    attention !== null && attention.team_join_requests > 0
      ? {
          key: 'join',
          icon: 'ti-door-enter',
          text: `Заявки в команду: ${attention.team_join_requests}`,
          to: captainTeamId !== null ? `/teams/${captainTeamId}?tab=requests` : '/teams',
        }
      : null,
  ].filter((row): row is { key: string; icon: string; text: string; to: string } => row !== null)

  return (
    <div className="relative min-h-svh overflow-hidden">
      <IceGlowBackground />
      <div className="relative z-[1] mx-auto flex max-w-2xl flex-col gap-4 px-4 py-6">
        {teams === null && <ListSkeleton rows={3} />}

        {/* Whatever put the dot on the tab -- answered from here in one tap. */}
        {waiting.length > 0 && (
          <div className="flex flex-col overflow-hidden rounded-md border border-accent-persimmon/35 bg-accent-persimmon/[0.06]">
            {waiting.map((row) => (
              <Link
                key={row.key}
                to={row.to}
                className="flex min-h-12 items-center gap-3 border-b border-white/5 px-3.5 last:border-b-0"
              >
                <i className={`ti ${row.icon} text-lg text-[#FF8A6B]`} aria-hidden="true" />
                <span className="flex-1 text-sm font-medium text-[#F5F7FA]">{row.text}</span>
                <span className="text-xs font-semibold text-[#FF8A6B]">Ответить ›</span>
              </Link>
            ))}
          </div>
        )}

        {teams !== null && teams.length > 0 && (
          <>
            <div className="flex items-center gap-3">
              <span className="flex h-[52px] w-[52px] shrink-0 items-center justify-center overflow-hidden rounded-full border border-white/15 bg-dark-card text-[#8A94A6]">
                {team?.logo_url != null ? (
                  <img src={`${API_BASE_URL}${team.logo_url}`} alt="" className="h-full w-full object-cover" />
                ) : (
                  <i className="ti ti-shield text-2xl" aria-hidden="true" />
                )}
              </span>
              <div className="flex min-w-0 flex-1 flex-col gap-0.5">
                <h1 className="truncate text-xl font-bold text-[#F5F7FA]">
                  {teams.find((item) => item.id === selectedTeamId)?.name}
                </h1>
                <span className="text-xs text-[#8A94A6]">
                  {teams.find((item) => item.id === selectedTeamId)?.member_count} участн.
                  {score !== null && ` · рейтинг ${Math.round(score.team_score).toLocaleString('ru-RU')}`}
                </span>
              </div>
              <Link
                to="/teams"
                aria-label="Все мои команды"
                className="flex h-11 w-11 items-center justify-center text-[#8A94A6] transition-colors hover:text-[#F5F7FA]"
              >
                <i className="ti ti-arrows-exchange text-xl" aria-hidden="true" />
              </Link>
            </div>

            {teams.length > 1 && (
              <div className="flex gap-2 overflow-x-auto">
                {teams.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => setSelectedTeamId(item.id)}
                    className={`min-h-9 shrink-0 rounded-full border px-3 text-sm ${
                      item.id === selectedTeamId
                        ? 'border-accent-ice/40 bg-accent-ice/15 text-accent-ice'
                        : 'border-white/10 text-[#8A94A6]'
                    }`}
                  >
                    {item.name}
                  </button>
                ))}
              </div>
            )}

            {selectedTeamId !== null && team !== null && (
              <NextEventCard teamId={selectedTeamId} isCaptain={team.is_captain} />
            )}

            <div className="grid grid-cols-3 gap-2">
              <HubTile icon="ti-calendar-event" label="Тренировки и игры" to={`${teamPath}/events`} />
              <HubTile
                icon="ti-trophy"
                label="Рейтинг команды"
                hint={score !== null ? `${Math.round(score.team_score).toLocaleString('ru-RU')} XP` : undefined}
                to={teamPath}
              />
              <HubTile
                icon="ti-users"
                label="Участники"
                hint={team !== null ? `${team.members.length} чел.` : undefined}
                to={teamPath}
              />
            </div>

            {team !== null && (
              <div className={`flex items-center gap-3 px-3.5 py-3 ${CARD_CLASS}`}>
                <span className="flex flex-1 flex-col gap-0.5">
                  <span className="text-xs uppercase tracking-wide text-[#8A94A6]">Код приглашения</span>
                  <span className="font-mono text-base tracking-wider text-[#F5F7FA]">{team.invite_code}</span>
                </span>
                <button
                  type="button"
                  onClick={handleCopyInviteCode}
                  className="min-h-10 rounded-md border border-white/15 px-3.5 text-sm font-semibold text-[#F5F7FA] transition-colors hover:bg-white/5"
                >
                  {copied ? 'Скопировано' : 'Копировать'}
                </button>
              </div>
            )}
          </>
        )}

        {teams !== null && teams.length === 0 && (
          <>
            <h1 className="text-xl font-semibold">Команда</h1>
            <section className={`relative flex flex-col gap-3 overflow-hidden p-4 ${CARD_CLASS}`}>
              <CardGlow />
              <span className="relative font-display text-xl font-semibold uppercase tracking-wide text-[#F5F7FA]">
                Тренируйтесь командой
              </span>
              <p className="relative text-sm leading-relaxed text-[#C9D2DE]">
                Тренер выкладывает лёд и игры, состав и план разминки — у каждого игрока они сами появляются в
                «Сегодня» и в плане недели.
              </p>
              <Link
                to="/teams"
                className="relative flex min-h-11 items-center justify-center rounded-md bg-accent-persimmon text-sm font-semibold text-white"
              >
                Вступить по коду
              </Link>
              <Link
                to="/teams"
                className="relative flex min-h-11 items-center justify-center rounded-md border border-white/15 text-sm font-semibold text-[#F5F7FA]"
              >
                Создать свою команду
              </Link>
            </section>
          </>
        )}

        <SectionHeader action={<Link to="/friends" className="text-xs text-accent-ice">Все друзья ›</Link>}>
          Друзья
        </SectionHeader>

        {hasFriends === false ? (
          <Link to="/friends" className={`flex flex-col gap-1.5 p-4 ${CARD_CLASS}`}>
            <span className="text-sm font-medium text-[#F5F7FA]">Добавьте друга по коду</span>
            <span className="text-xs leading-relaxed text-[#8A94A6]">
              Сравнивайте статы, смотрите ленту тренировок и зовите на совместные тренировки.
            </span>
          </Link>
        ) : (
          feed !== null &&
          feed.length > 0 && (
            <div className={`flex flex-col ${CARD_CLASS}`}>
              {feed.slice(0, FEED_PREVIEW_SIZE).map((entry) => (
                <Link
                  key={entry.id}
                  to={`/profile/${entry.user_id}`}
                  className="flex items-center gap-3 border-b border-white/5 px-3.5 py-3 last:border-b-0"
                >
                  <span className="flex h-9 w-9 shrink-0 items-center justify-center overflow-hidden rounded-full bg-[#22304A] font-display text-sm text-accent-ice">
                    {entry.avatar_url !== null ? (
                      <img src={`${API_BASE_URL}${entry.avatar_url}`} alt="" className="h-full w-full object-cover" />
                    ) : (
                      `${entry.first_name[0] ?? ''}${entry.last_name[0] ?? ''}`
                    )}
                  </span>
                  <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                    <span className="text-sm text-[#F5F7FA]">
                      <b className="font-semibold">{entry.first_name}</b> {feedText(entry)}
                    </span>
                    <span className="text-xs text-[#8A94A6]">{formatDateTime(new Date(entry.created_at))}</span>
                  </span>
                </Link>
              ))}
            </div>
          )
        )}

        <div className="grid grid-cols-2 gap-2">
          <HubTile icon="ti-users-group" label="Совместные тренировки" to="/training-parties" />
          <HubTile
            icon="ti-trophy"
            label="Рейтинг игроков"
            hint={leaderboardMe !== null ? `Вы ${leaderboardMe.rank}-й` : undefined}
            to="/leaderboard"
          />
        </div>
      </div>
    </div>
  )
}

function SectionHeader({ children, action }: { children: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex items-center gap-2 px-1 pt-1">
      <span className="h-px w-4 shrink-0 bg-accent-ice/60" aria-hidden="true" />
      <span className="shrink-0 text-xs font-semibold uppercase tracking-wide text-[#8A94A6]">{children}</span>
      <span className="h-px flex-1 bg-white/10" aria-hidden="true" />
      {action}
    </div>
  )
}

function HubTile({ icon, label, hint, to }: { icon: string; label: string; hint?: string; to: string }) {
  return (
    <Link to={to} className={`flex flex-col gap-1.5 p-3 transition-colors hover:bg-white/5 ${CARD_CLASS}`}>
      <i className={`ti ${icon} text-xl text-accent-ice`} aria-hidden="true" />
      <span className="text-[13px] font-medium leading-tight text-[#F5F7FA]">{label}</span>
      {hint !== undefined && <span className="text-xs text-[#8A94A6]">{hint}</span>}
    </Link>
  )
}
