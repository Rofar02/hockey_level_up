import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { BackLink } from '../components/ui/BackLink'
import { Button } from '../components/ui/Button'
import { CARD_CLASS } from '../components/ui/cardStyle'
import { FormError } from '../components/ui/FormError'
import { IceGlowBackground } from '../components/ui/IceGlowBackground'
import { Modal } from '../components/ui/Modal'
import { TabButton } from '../components/ui/TabButton'
import { TextField } from '../components/ui/TextField'
import { EventBoardPanel } from '../components/teamEvents/EventBoardPanel'
import { EventAttendancePanel } from '../components/teamEvents/EventAttendancePanel'
import { EventLineupPanel } from '../components/teamEvents/EventLineupPanel'
import * as teamsApi from '../api/teams'
import * as teamEventsApi from '../api/teamEvents'
import { ApiError } from '../api/client'
import { useAuth } from '../hooks/useAuth'
import type { TeamRead } from '../types/team'
import type { TeamEventRead } from '../types/teamEvent'
import { formatDateTime, toDatetimeLocalValue } from '../utils/date'

type DetailTab = 'board' | 'attendance' | 'lineup'

export function TeamEventDetailPage() {
  const { teamId, eventId } = useParams<{ teamId: string; eventId: string }>()
  const { accessToken } = useAuth()
  // ?tab=board|attendance|lineup -- e.g. the team page's "Ближайшее" card
  // links straight to the board. (No diary tab: after a team training
  // players and the coach use their ordinary personal diary.)
  const [searchParams] = useSearchParams()
  const requestedTab = searchParams.get('tab')

  const [team, setTeam] = useState<TeamRead | null>(null)
  const [event, setEvent] = useState<TeamEventRead | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<DetailTab | null>(null)

  const [isRescheduleOpen, setIsRescheduleOpen] = useState(false)
  const [rescheduleValue, setRescheduleValue] = useState('')
  const [isRescheduling, setIsRescheduling] = useState(false)
  const [rescheduleError, setRescheduleError] = useState<string | null>(null)

  const [isCancelling, setIsCancelling] = useState(false)
  const [cancelError, setCancelError] = useState<string | null>(null)
  const [isConfirmingCancel, setIsConfirmingCancel] = useState(false)

  async function load() {
    if (accessToken === null || teamId === undefined || eventId === undefined) {
      return
    }
    const [teamResult, eventResult] = await Promise.all([
      teamsApi.getTeam(teamId, accessToken),
      teamEventsApi.getTeamEvent(teamId, eventId, accessToken),
    ])
    setTeam(teamResult)
    setEvent(eventResult)
    setActiveTab((current) => {
      if (current !== null) {
        return current
      }
      const trainingOnly: string[] = ['board']
      if (
        (requestedTab === 'board' || requestedTab === 'attendance' || requestedTab === 'lineup') &&
        (eventResult.event_type === 'training' || !trainingOnly.includes(requestedTab))
      ) {
        return requestedTab
      }
      return eventResult.event_type === 'training' ? 'board' : 'attendance'
    })
  }

  useEffect(() => {
    let cancelled = false
    load().catch((err: unknown) => {
      if (!cancelled) {
        setLoadError(err instanceof ApiError ? err.message : 'Не удалось загрузить событие.')
      }
    })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accessToken, teamId, eventId])

  function openReschedule() {
    if (event === null) {
      return
    }
    setRescheduleValue(toDatetimeLocalValue(new Date(event.starts_at)))
    setRescheduleError(null)
    setIsRescheduleOpen(true)
  }

  async function handleReschedule(e: FormEvent) {
    e.preventDefault()
    if (accessToken === null || teamId === undefined || eventId === undefined) {
      return
    }
    setIsRescheduling(true)
    setRescheduleError(null)
    try {
      const updated = await teamEventsApi.rescheduleTeamEvent(
        teamId,
        eventId,
        { starts_at: new Date(rescheduleValue).toISOString() },
        accessToken,
      )
      setEvent(updated)
      setIsRescheduleOpen(false)
    } catch (err) {
      setRescheduleError(err instanceof ApiError ? err.message : 'Не удалось перенести событие.')
    } finally {
      setIsRescheduling(false)
    }
  }

  async function handleCancel() {
    if (accessToken === null || teamId === undefined || eventId === undefined) {
      return
    }
    setIsCancelling(true)
    setCancelError(null)
    try {
      const updated = await teamEventsApi.cancelTeamEvent(teamId, eventId, accessToken)
      setEvent(updated)
      setIsConfirmingCancel(false)
    } catch (err) {
      setCancelError(err instanceof ApiError ? err.message : 'Не удалось отменить событие.')
    } finally {
      setIsCancelling(false)
    }
  }

  const isLoading = team === null || event === null || activeTab === null

  if (!isLoading && event.status === 'cancelled') {
    return (
      <div className="relative min-h-svh overflow-hidden">
        <IceGlowBackground />
        <div className="relative z-[1] mx-auto flex max-w-2xl flex-col gap-6 px-4 py-8">
          <BackLink />
          <div className={`flex flex-col items-center gap-2 p-8 text-center ${CARD_CLASS}`}>
            <i className="ti ti-calendar-off text-3xl text-[#8A94A6]" aria-hidden="true" />
            <p className="text-sm text-[#F5F7FA]">
              {event.event_type === 'training' ? 'Тренировка отменена' : 'Игра отменена'}
            </p>
            <p className="text-xs text-[#8A94A6]">{formatDateTime(new Date(event.starts_at))}</p>
          </div>
        </div>
      </div>
    )
  }

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
              <div className="flex items-start justify-between gap-3">
                <div className="flex flex-col gap-1">
                  <h1 className="text-lg font-semibold text-[#F5F7FA]">
                    {event.event_type === 'training' ? 'Тренировка' : `Игра с ${event.opponent_name}`}
                  </h1>
                  <span className="text-sm text-[#8A94A6]">{formatDateTime(new Date(event.starts_at))}</span>
                </div>
              </div>
              {team.is_captain && (
                <div className="flex flex-wrap gap-2 border-t border-white/5 pt-3">
                  <Button type="button" variant="neutral" className="!px-3 !py-1.5 !text-xs" onClick={openReschedule}>
                    Перенести
                  </Button>
                  <Button
                    type="button"
                    variant="neutral"
                    className="!px-3 !py-1.5 !text-xs"
                    onClick={() => setIsConfirmingCancel(true)}
                  >
                    Отменить
                  </Button>
                </div>
              )}
              <FormError message={cancelError} />
            </div>

            <div className="flex border-b border-white/10">
              {event.event_type === 'training' && (
                <TabButton active={activeTab === 'board'} onClick={() => setActiveTab('board')}>
                  Доска
                </TabButton>
              )}
              <TabButton active={activeTab === 'attendance'} onClick={() => setActiveTab('attendance')}>
                Явка
              </TabButton>
              <TabButton active={activeTab === 'lineup'} onClick={() => setActiveTab('lineup')}>
                Состав
              </TabButton>
            </div>

            {activeTab === 'board' && event.event_type === 'training' && (
              <EventBoardPanel
                teamId={teamId!}
                event={event}
                isCaptain={team.is_captain}
                onEventChange={setEvent}
              />
            )}
            {activeTab === 'attendance' && (
              <EventAttendancePanel teamId={teamId!} event={event} isCaptain={team.is_captain} />
            )}
            {activeTab === 'lineup' && (
              <EventLineupPanel teamId={teamId!} event={event} isCaptain={team.is_captain} />
            )}
          </>
        )}
      </div>

      {isRescheduleOpen && (
        <Modal title="Перенести время" onClose={() => setIsRescheduleOpen(false)}>
          <form onSubmit={handleReschedule} className="flex flex-col gap-4">
            <TextField
              label="Новые дата и время"
              type="datetime-local"
              value={rescheduleValue}
              onChange={(e) => setRescheduleValue(e.target.value)}
              required
            />
            <FormError message={rescheduleError} />
            <Button type="submit" isLoading={isRescheduling}>
              Сохранить
            </Button>
          </form>
        </Modal>
      )}

      {isConfirmingCancel && (
        <Modal title="Отменить событие?" onClose={() => setIsConfirmingCancel(false)}>
          <div className="flex flex-col gap-4">
            <p className="text-sm text-[#8A94A6]">
              Команда получит уведомление об отмене. Это действие нельзя отменить обратно.
            </p>
            <FormError message={cancelError} />
            <div className="flex gap-2">
              <Button type="button" variant="neutral" onClick={() => setIsConfirmingCancel(false)} className="flex-1">
                Назад
              </Button>
              <Button type="button" onClick={handleCancel} isLoading={isCancelling} className="flex-1">
                Отменить событие
              </Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}
