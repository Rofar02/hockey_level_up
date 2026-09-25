import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button } from '../ui/Button'
import { CardGlow } from '../ui/CardGlow'
import { CARD_CLASS } from '../ui/cardStyle'
import { EventPlanStatus } from './EventPlanStatus'
import * as teamEventsApi from '../../api/teamEvents'
import { useAuth } from '../../hooks/useAuth'
import type { TeamEventRead } from '../../types/teamEvent'
import { formatDateTime } from '../../utils/date'
import { upcomingEvents } from '../../utils/teamEvents'

// Team page entry point to the schedule: the next event with its plan
// status and a direct way into its board, instead of a bare
// "Тренировки и игры" link the plan was easy to miss behind.
export function NextEventCard({ teamId, isCaptain }: { teamId: string; isCaptain: boolean }) {
  const { accessToken } = useAuth()
  const navigate = useNavigate()
  const [events, setEvents] = useState<TeamEventRead[] | null>(null)

  useEffect(() => {
    if (accessToken === null) {
      return
    }
    let cancelled = false
    teamEventsApi
      .listTeamEvents(teamId, accessToken)
      .then((result) => {
        if (!cancelled) {
          setEvents(result)
        }
      })
      .catch(() => {
        if (!cancelled) {
          setEvents([])
        }
      })
    return () => {
      cancelled = true
    }
  }, [accessToken, teamId])

  const eventsPath = `/teams/${teamId}/events`
  const next = events !== null ? upcomingEvents(events)[0] : undefined

  return (
    <section className={`relative flex flex-col gap-3 overflow-hidden p-4 ${CARD_CLASS}`} aria-label="Тренировки и игры">
      <CardGlow />
      <div className="relative flex items-center justify-between gap-3">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-[#8A94A6]">Ближайшее</h2>
        <button
          type="button"
          onClick={() => navigate(eventsPath)}
          className="flex min-h-11 items-center gap-1 text-sm text-accent-ice transition-opacity hover:opacity-80"
        >
          Все тренировки и игры
          <i className="ti ti-chevron-right" aria-hidden="true" />
        </button>
      </div>

      {events === null && <p className="relative text-sm text-[#8A94A6]">Загрузка...</p>}

      {events !== null && next === undefined && (
        <div className="relative flex flex-col gap-3">
          <p className="text-sm text-[#8A94A6]">
            {isCaptain ? 'Ничего не запланировано. Создай тренировку — и составь к ней план.' : 'Тренер пока ничего не запланировал.'}
          </p>
          {isCaptain && (
            <Button onClick={() => navigate(eventsPath)} className="w-full">
              + Запланировать тренировку
            </Button>
          )}
        </div>
      )}

      {next !== undefined && <NextEventBody teamId={teamId} event={next} isCaptain={isCaptain} />}
    </section>
  )
}

function NextEventBody({ teamId, event, isCaptain }: { teamId: string; event: TeamEventRead; isCaptain: boolean }) {
  const navigate = useNavigate()
  const isTraining = event.event_type === 'training'
  const hasDrills = (event.sections ?? []).some((section) => section.drills.length > 0)
  const eventPath = `/teams/${teamId}/events/${event.id}`

  let cta: { label: string; to: string }
  if (isTraining && isCaptain) {
    cta = { label: hasDrills ? 'Открыть план тренировки' : 'Составить план тренировки', to: `${eventPath}?tab=board` }
  } else if (isTraining) {
    cta = { label: 'Посмотреть план', to: `${eventPath}?tab=board` }
  } else {
    cta = { label: 'Открыть игру', to: eventPath }
  }

  return (
    <div className="relative flex flex-col gap-3">
      <div className="flex items-center gap-3">
        <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-accent-ice/10">
          <i className={`ti ${isTraining ? 'ti-ice-skating' : 'ti-trophy'} text-xl text-accent-ice`} aria-hidden="true" />
        </span>
        <div className="flex min-w-0 flex-col gap-0.5">
          <p className="truncate text-base font-semibold text-[#F5F7FA]">
            {isTraining ? 'Тренировка' : `Игра с ${event.opponent_name}`}
          </p>
          <p className="text-sm text-[#8A94A6]">{formatDateTime(new Date(event.starts_at))}</p>
        </div>
      </div>
      <EventPlanStatus event={event} isCaptain={isCaptain} />
      <Button onClick={() => navigate(cta.to)} className="w-full">
        {cta.label}
      </Button>
    </div>
  )
}
