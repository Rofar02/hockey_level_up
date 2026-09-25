import { useEffect, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button } from '../ui/Button'
import { CardGlow } from '../ui/CardGlow'
import { CARD_CLASS } from '../ui/cardStyle'
import { BoardPlanModal } from './BoardPlanView'
import * as teamEventsApi from '../../api/teamEvents'
import * as teamsApi from '../../api/teams'
import { useAuth } from '../../hooks/useAuth'
import { boardTotalMinutes, formatMinutes, totalMinutes } from '../../utils/boardPlan'
import type { DayPlanRead } from '../../types/schedule'
import type { TeamEventDiaryEntryRead, TeamEventLineupRead, TeamEventRead } from '../../types/teamEvent'
import { formatTime } from '../../utils/date'

interface Loaded {
  teamId: string
  event: TeamEventRead
  lineup: TeamEventLineupRead | null
  diaryEntry: TeamEventDiaryEntryRead | null
}

// HomePage's today card for a day a team event has taken over (the player
// marked "going" -- see ScheduleService.apply_team_event_to_day):
// "Подготовка" before the event starts (board, lineup group, jersey color,
// the app's own on-ice warmup), then the team diary once it has. The team
// diary replaces the personal on-ice one here -- it's the one that grants
// the team-training rewards. A game has no team diary, so after its start
// (and on any load failure) this hands back to the ordinary personal card.
export function TeamDayCard({
  day,
  eyebrow,
  onStartWarmup,
  personalCard,
}: {
  day: DayPlanRead & { team_event_id: string }
  eyebrow: string
  onStartWarmup: () => void
  personalCard: ReactNode
}) {
  const { accessToken, user } = useAuth()
  const navigate = useNavigate()
  const [loaded, setLoaded] = useState<Loaded | null>(null)
  const [failed, setFailed] = useState(false)
  const eventId = day.team_event_id

  useEffect(() => {
    if (accessToken === null) {
      return
    }
    let cancelled = false
    async function load(token: string): Promise<Loaded | null> {
      // One team per user in v2 (TeamMembership is unique on user_id).
      const [team] = await teamsApi.listMyTeams(token)
      if (team === undefined) {
        return null
      }
      const event = await teamEventsApi.getTeamEvent(team.id, eventId, token)
      const [lineup, diaryEntry] = await Promise.all([
        teamEventsApi.getLineup(team.id, eventId, token).catch(() => null),
        event.event_type === 'training'
          ? teamEventsApi.getMyDiaryEntry(team.id, eventId, token).catch(() => null)
          : Promise.resolve(null),
      ])
      return { teamId: team.id, event, lineup, diaryEntry }
    }
    load(accessToken)
      .then((result) => {
        if (cancelled) {
          return
        }
        if (result === null) {
          setFailed(true)
        } else {
          setLoaded(result)
        }
      })
      .catch(() => {
        if (!cancelled) {
          setFailed(true)
        }
      })
    return () => {
      cancelled = true
    }
  }, [accessToken, eventId])

  if (failed) {
    return <>{personalCard}</>
  }
  if (loaded === null) {
    return (
      <div className={`relative overflow-hidden p-5 ${CARD_CLASS}`}>
        <CardGlow />
        <p className="relative text-sm text-[#8A94A6]">Загрузка командного события...</p>
      </div>
    )
  }

  const { teamId, event, lineup, diaryEntry } = loaded
  const startsAt = new Date(event.starts_at)
  const hasStarted = Date.now() >= startsAt.getTime()
  const isTraining = event.event_type === 'training'
  if (hasStarted && !isTraining) {
    return <>{personalCard}</>
  }

  const eventPath = `/teams/${teamId}/events/${event.id}`
  const title = isTraining ? 'Командная тренировка' : `Игра${event.opponent_name ? ` с ${event.opponent_name}` : ''}`
  const diaryDone = hasStarted && diaryEntry !== null
  const warmupAvailable =
    !hasStarted &&
    day.training_session !== null &&
    day.training_session.blocks.some((block) => block.completed_at === null)

  return (
    <div className={`relative overflow-hidden p-5 ${CARD_CLASS}`}>
      <CardGlow />
      <div className="relative flex flex-col gap-4">
        <div className="flex items-center justify-between gap-3">
          <p className="text-xs uppercase tracking-wide text-[#8A94A6]">{eyebrow}</p>
          {diaryDone && (
            <span className="flex items-center gap-1 rounded-full bg-accent-ice/15 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-accent-ice">
              <i className="ti ti-check" aria-hidden="true" />
              Выполнено
            </span>
          )}
        </div>
        <div>
          <p className="flex items-center gap-2 text-2xl font-bold text-[#F5F7FA]">
            <i className="ti ti-users-group text-accent-ice" aria-hidden="true" />
            {title}
          </p>
          <p className="mt-1 text-sm text-[#8A94A6]">
            {hasStarted ? 'Началась' : 'Начало'} в {formatTime(startsAt)}
          </p>
        </div>

        {!hasStarted && (
          <div className="flex flex-col gap-3">
            {isTraining && <BoardSummary event={event} />}
            <LineupSummary lineup={lineup} userId={user?.id ?? null} isTraining={isTraining} />
          </div>
        )}

        {hasStarted ? (
          <Button onClick={() => navigate(`${eventPath}?tab=diary`)} className="w-full">
            {diaryDone ? 'Открыть дневник' : 'Вести дневник'}
          </Button>
        ) : (
          <div className="flex flex-col gap-2">
            {warmupAvailable && (
              <Button onClick={onStartWarmup} className="w-full">
                Разминка до выхода на лёд
              </Button>
            )}
            <Button variant={warmupAvailable ? 'neutral' : 'primary'} onClick={() => navigate(eventPath)} className="w-full">
              Открыть событие
            </Button>
          </div>
        )}
      </div>
    </div>
  )
}

function SummaryRow({ icon, label, children }: { icon: string; label: string; children: ReactNode }) {
  return (
    <div className="flex items-start gap-3">
      <i className={`ti ${icon} mt-0.5 text-lg text-[#8A94A6]`} aria-hidden="true" />
      <div className="min-w-0">
        <p className="text-[11px] uppercase tracking-wide text-[#5B6472]">{label}</p>
        <div className="text-sm text-[#F5F7FA]">{children}</div>
      </div>
    </div>
  )
}

// One line per section ("Разминка · 2 · 10 мин") -- stays short however
// many drills the coach adds; the full plan opens in BoardPlanModal.
function BoardSummary({ event }: { event: TeamEventRead }) {
  const [isPlanOpen, setIsPlanOpen] = useState(false)
  // sections is null for a non-captain while the board is still a draft.
  const sections =
    event.board_status === 'published'
      ? (event.sections ?? []).filter((section) => section.drills.length > 0)
      : null
  if (sections === null || sections.length === 0) {
    return (
      <SummaryRow icon="ti-clipboard-list" label="План">
        <span className="text-[#8A94A6]">Тренер ещё не опубликовал план</span>
      </SummaryRow>
    )
  }
  const boardMinutes = boardTotalMinutes(sections)
  return (
    <SummaryRow icon="ti-clipboard-list" label={boardMinutes !== null ? `План · ${formatMinutes(boardMinutes)}` : 'План'}>
      {sections.map((section) => {
        const minutes = totalMinutes(section.drills)
        return (
          <p key={section.id} className="truncate">
            {section.name}
            <span className="text-[#8A94A6]">
              {' · '}
              {section.drills.length}
              {minutes !== null && ` · ${formatMinutes(minutes)}`}
            </span>
          </p>
        )
      })}
      <button
        type="button"
        onClick={() => setIsPlanOpen(true)}
        className="mt-1 flex items-center gap-1 text-sm font-medium text-accent-ice transition-opacity hover:opacity-80"
      >
        Смотреть план
        <i className="ti ti-chevron-right" aria-hidden="true" />
      </button>
      {isPlanOpen && <BoardPlanModal sections={sections} onClose={() => setIsPlanOpen(false)} />}
    </SummaryRow>
  )
}

function LineupSummary({
  lineup,
  userId,
  isTraining,
}: {
  lineup: TeamEventLineupRead | null
  userId: string | null
  isTraining: boolean
}) {
  const groups = lineup?.lineup_status === 'published' ? lineup.groups : null
  const groupIndex = groups?.findIndex((group) => group.players.some((player) => player.user_id === userId)) ?? -1
  const group = groups !== null && groupIndex >= 0 ? groups[groupIndex] : null

  let content: ReactNode
  if (groups === null) {
    content = <span className="text-[#8A94A6]">Состав ещё не опубликован</span>
  } else if (group === null) {
    content = <span className="text-[#8A94A6]">Тебя пока нет в составе</span>
  } else {
    content = (
      <span className="flex items-center gap-2">
        {isTraining && group.color !== null && (
          <span className="h-3 w-3 shrink-0 rounded-full" style={{ backgroundColor: group.color }} aria-hidden="true" />
        )}
        {group.name ?? `Группа ${groupIndex + 1}`}
        {isTraining && group.color !== null && <span className="text-[#8A94A6]">· цвет майки</span>}
      </span>
    )
  }
  return (
    <SummaryRow icon="ti-users" label="Состав">
      {content}
    </SummaryRow>
  )
}
