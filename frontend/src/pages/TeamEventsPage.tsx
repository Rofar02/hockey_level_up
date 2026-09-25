import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { EventPlanStatus } from '../components/teamEvents/EventPlanStatus'
import { BackLink } from '../components/ui/BackLink'
import { Button } from '../components/ui/Button'
import { CARD_CLASS } from '../components/ui/cardStyle'
import { EmptyState } from '../components/ui/EmptyState'
import { FormError } from '../components/ui/FormError'
import { IceGlowBackground } from '../components/ui/IceGlowBackground'
import { Modal } from '../components/ui/Modal'
import { SelectField } from '../components/ui/SelectField'
import { TextField } from '../components/ui/TextField'
import * as teamsApi from '../api/teams'
import * as teamEventsApi from '../api/teamEvents'
import { ApiError } from '../api/client'
import { useAuth } from '../hooks/useAuth'
import { isPastEvent, upcomingEvents } from '../utils/teamEvents'
import type { TeamRead } from '../types/team'
import type { TeamEventRead, TeamEventType } from '../types/teamEvent'
import { formatDateTime, toDatetimeLocalValue } from '../utils/date'

const EVENT_TYPE_OPTIONS: { value: TeamEventType; label: string }[] = [
  { value: 'training', label: 'Тренировка' },
  { value: 'game', label: 'Игра' },
]

function nextHourDefault(): string {
  const date = new Date()
  date.setHours(date.getHours() + 1, 0, 0, 0)
  return toDatetimeLocalValue(date)
}

function EventTypeIcon({ eventType }: { eventType: TeamEventType }) {
  return (
    <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-accent-ice/10">
      <i
        className={`ti ${eventType === 'training' ? 'ti-clipboard-list' : 'ti-trophy'} text-lg text-accent-ice`}
        aria-hidden="true"
      />
    </span>
  )
}

function EventList({
  title,
  events,
  isCaptain,
  muted = false,
  onOpen,
}: {
  title: string
  events: TeamEventRead[]
  isCaptain: boolean
  muted?: boolean
  onOpen: (event: TeamEventRead) => void
}) {
  if (events.length === 0) {
    return null
  }
  return (
    <section className="flex flex-col gap-2">
      <h2 className="text-xs font-semibold uppercase tracking-wide text-[#8A94A6]">{title}</h2>
      {events.map((event) => {
        const cancelled = event.status === 'cancelled'
        return (
          <button
            key={event.id}
            type="button"
            onClick={() => onOpen(event)}
            className={`flex items-center gap-3 p-3 text-left transition-colors hover:bg-white/5 ${CARD_CLASS} ${
              muted ? 'opacity-70' : ''
            }`}
          >
            <EventTypeIcon eventType={event.event_type} />
            <div className="flex min-w-0 flex-1 flex-col gap-1">
              <span className={`truncate text-sm font-medium text-[#F5F7FA] ${cancelled ? 'line-through' : ''}`}>
                {event.event_type === 'training' ? 'Тренировка' : `Игра с ${event.opponent_name}`}
              </span>
              <span className="text-xs text-[#8A94A6]">
                {formatDateTime(new Date(event.starts_at))}
                {cancelled && ' · отменена'}
              </span>
              {!cancelled && !muted && <EventPlanStatus event={event} isCaptain={isCaptain} />}
            </div>
            <i className="ti ti-chevron-right text-[#8A94A6]" aria-hidden="true" />
          </button>
        )
      })}
    </section>
  )
}

export function TeamEventsPage() {
  const { teamId } = useParams<{ teamId: string }>()
  const navigate = useNavigate()
  const { accessToken } = useAuth()

  const [team, setTeam] = useState<TeamRead | null>(null)
  const [events, setEvents] = useState<TeamEventRead[] | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)

  const [isCreateOpen, setIsCreateOpen] = useState(false)
  const [createType, setCreateType] = useState<TeamEventType>('training')
  const [createStartsAt, setCreateStartsAt] = useState(nextHourDefault())
  const [createOpponent, setCreateOpponent] = useState('')
  const [isCreating, setIsCreating] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)

  useEffect(() => {
    if (accessToken === null || teamId === undefined) {
      return
    }
    let cancelled = false
    Promise.all([teamsApi.getTeam(teamId, accessToken), teamEventsApi.listTeamEvents(teamId, accessToken)])
      .then(([teamResult, eventsResult]) => {
        if (cancelled) {
          return
        }
        setTeam(teamResult)
        setEvents(eventsResult)
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setLoadError(err instanceof ApiError ? err.message : 'Не удалось загрузить события.')
        }
      })
    return () => {
      cancelled = true
    }
  }, [accessToken, teamId])

  function openCreateModal() {
    setCreateType('training')
    setCreateStartsAt(nextHourDefault())
    setCreateOpponent('')
    setCreateError(null)
    setIsCreateOpen(true)
  }

  async function handleCreate(e: FormEvent) {
    e.preventDefault()
    if (accessToken === null || teamId === undefined) {
      return
    }
    setIsCreating(true)
    setCreateError(null)
    try {
      const created = await teamEventsApi.createTeamEvent(
        teamId,
        {
          event_type: createType,
          starts_at: new Date(createStartsAt).toISOString(),
          opponent_name: createType === 'game' ? createOpponent.trim() : undefined,
        },
        accessToken,
      )
      setIsCreateOpen(false)
      navigate(`/teams/${teamId}/events/${created.id}`)
    } catch (err) {
      setCreateError(err instanceof ApiError ? err.message : 'Не удалось создать событие.')
    } finally {
      setIsCreating(false)
    }
  }

  const isLoading = team === null || events === null

  return (
    <div className="relative min-h-svh overflow-hidden">
      <IceGlowBackground />
      <div className="relative z-[1] mx-auto flex max-w-2xl flex-col gap-6 px-4 py-8">
        <BackLink />

        <div className="flex items-center justify-between gap-3">
          <h1 className="text-lg font-semibold text-[#F5F7FA]">Тренировки и игры</h1>
          {team?.is_captain === true && (
            <button
              type="button"
              onClick={() => navigate(`/teams/${teamId}/ice-schedule-templates`)}
              className="text-sm text-accent-ice hover:underline"
            >
              Расписание льда
            </button>
          )}
        </div>

        <FormError message={loadError} />
        {isLoading && loadError === null && <p className="text-sm text-[#8A94A6]">Загрузка...</p>}

        {!isLoading && (
          <>
            {team.is_captain && (
              <Button type="button" onClick={openCreateModal}>
                + Создать тренировку или игру
              </Button>
            )}

            {events.length === 0 ? (
              <EmptyState
                icon="ti-calendar-off"
                title="Пока ничего не запланировано"
                hint={
                  team.is_captain
                    ? 'Создайте тренировку или игру -- команда увидит её сразу.'
                    : 'Тренер ещё не назначил тренировки или игры.'
                }
              />
            ) : (
              <>
                <EventList
                  title="Предстоящие"
                  events={upcomingEvents(events)}
                  isCaptain={team.is_captain}
                  onOpen={(event) => navigate(`/teams/${teamId}/events/${event.id}`)}
                />
                <EventList
                  title="Прошедшие и отменённые"
                  muted
                  events={events
                    .filter((event) => event.status === 'cancelled' || isPastEvent(event))
                    .sort((x, y) => new Date(y.starts_at).getTime() - new Date(x.starts_at).getTime())}
                  isCaptain={team.is_captain}
                  onOpen={(event) => navigate(`/teams/${teamId}/events/${event.id}`)}
                />
              </>
            )}
          </>
        )}
      </div>

      {isCreateOpen && (
        <Modal title="Новое событие" onClose={() => setIsCreateOpen(false)}>
          <form onSubmit={handleCreate} className="flex flex-col gap-4">
            <SelectField
              label="Тип"
              options={EVENT_TYPE_OPTIONS}
              value={createType}
              onChange={(e) => setCreateType(e.target.value as TeamEventType)}
            />
            <TextField
              label="Дата и время"
              type="datetime-local"
              value={createStartsAt}
              onChange={(e) => setCreateStartsAt(e.target.value)}
              required
            />
            {createType === 'game' && (
              <TextField
                label="Соперник"
                value={createOpponent}
                onChange={(e) => setCreateOpponent(e.target.value)}
                placeholder="Название команды соперника"
                required
              />
            )}
            <FormError message={createError} />
            <Button type="submit" isLoading={isCreating}>
              Создать
            </Button>
          </form>
        </Modal>
      )}
    </div>
  )
}
