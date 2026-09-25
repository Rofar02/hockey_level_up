import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button } from '../ui/Button'
import { CardGlow } from '../ui/CardGlow'
import { CARD_CLASS } from '../ui/cardStyle'
import { EventPlanStatus } from './EventPlanStatus'
import * as teamEventsApi from '../../api/teamEvents'
import * as teamsApi from '../../api/teams'
import { useAuth } from '../../hooks/useAuth'
import type { TeamEventRead } from '../../types/teamEvent'
import { pluralRu } from '../../utils/boardPlan'
import { formatDateTime } from '../../utils/date'
import { upcomingEvents } from '../../utils/teamEvents'

// How far ahead an unfinished plan is worth nagging about.
const REMIND_WITHIN_MS = 7 * 24 * 60 * 60 * 1000

interface Reminder {
  teamId: string
  next: TeamEventRead
  more: number
}

// HomePage nudge for the team captain only: an upcoming training (within a
// week) whose plan the team can't see yet -- empty, or still a draft. Goes
// straight to that training's board; disappears once it's published.
export function CoachPlanReminderCard() {
  const { accessToken } = useAuth()
  const navigate = useNavigate()
  const [reminder, setReminder] = useState<Reminder | null>(null)

  useEffect(() => {
    if (accessToken === null) {
      return
    }
    let cancelled = false
    async function load(token: string): Promise<Reminder | null> {
      // One team per user in v2; only its captain builds plans.
      const [team] = await teamsApi.listMyTeams(token)
      if (team === undefined || !team.is_captain) {
        return null
      }
      const now = Date.now()
      const unfinished = upcomingEvents(await teamEventsApi.listTeamEvents(team.id, token), now).filter(
        (event) =>
          event.event_type === 'training' &&
          event.board_status !== 'published' &&
          new Date(event.starts_at).getTime() > now &&
          new Date(event.starts_at).getTime() - now <= REMIND_WITHIN_MS,
      )
      if (unfinished.length === 0) {
        return null
      }
      return { teamId: team.id, next: unfinished[0], more: unfinished.length - 1 }
    }
    load(accessToken)
      .then((result) => {
        if (!cancelled) {
          setReminder(result)
        }
      })
      .catch(() => {
        // Best-effort -- the home screen works fine without the nudge.
      })
    return () => {
      cancelled = true
    }
  }, [accessToken])

  if (reminder === null) {
    return null
  }
  const { teamId, next, more } = reminder

  return (
    <section
      aria-label="Завершите план тренировки"
      className={`relative flex flex-col gap-3 overflow-hidden border-[#FFCF5C]/30 p-4 ${CARD_CLASS}`}
    >
      <CardGlow />
      <div className="relative flex items-start gap-3">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[#FFCF5C]/15">
          <i className="ti ti-clipboard-text text-xl text-[#FFCF5C]" aria-hidden="true" />
        </span>
        <div className="flex min-w-0 flex-col gap-1">
          <h2 className="text-base font-semibold text-[#F5F7FA]">Завершите план тренировки</h2>
          <p className="text-sm text-[#8A94A6]">
            Тренировка {formatDateTime(new Date(next.starts_at))} — команда пока не видит план.
          </p>
          <EventPlanStatus event={next} isCaptain />
          {more > 0 && (
            <p className="text-xs text-[#8A94A6]">
              И ещё {more} {pluralRu(more, ['тренировка', 'тренировки', 'тренировок'])} без плана на этой неделе
            </p>
          )}
        </div>
      </div>
      <Button onClick={() => navigate(`/teams/${teamId}/events/${next.id}?tab=board`)} className="relative w-full">
        Завершить план
      </Button>
    </section>
  )
}
