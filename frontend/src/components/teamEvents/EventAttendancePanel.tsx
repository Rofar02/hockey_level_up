import { useEffect, useState } from 'react'
import { Button } from '../ui/Button'
import { CARD_CLASS } from '../ui/cardStyle'
import { ChoiceCard } from '../ui/ChoiceCard'
import { FormError } from '../ui/FormError'
import { SelectField } from '../ui/SelectField'
import { TextField } from '../ui/TextField'
import * as teamEventsApi from '../../api/teamEvents'
import { ApiError } from '../../api/client'
import { useAuth } from '../../hooks/useAuth'
import type {
  TeamEventAbsenceReason,
  TeamEventAttendanceMemberRead,
  TeamEventAttendanceRosterRead,
  TeamEventAttendanceStatus,
  TeamEventRead,
} from '../../types/teamEvent'
import { getDisplayName } from '../../utils/displayName'

interface EventAttendancePanelProps {
  teamId: string
  event: TeamEventRead
  isCaptain: boolean
}

const REASON_OPTIONS: { value: TeamEventAbsenceReason; label: string }[] = [
  { value: 'work', label: 'Работа' },
  { value: 'injury', label: 'Травма' },
  { value: 'study', label: 'Учёба' },
  { value: 'other', label: 'Другое' },
]

const REASON_LABELS: Record<TeamEventAbsenceReason, string> = {
  work: 'Работа',
  injury: 'Травма',
  study: 'Учёба',
  other: 'Другое',
}

function RosterSection({
  title,
  members,
  showReason,
}: {
  title: string
  members: TeamEventAttendanceMemberRead[]
  showReason?: boolean
}) {
  if (members.length === 0) {
    return null
  }
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-xs font-medium uppercase tracking-wide text-[#8A94A6]">
        {title} ({members.length})
      </span>
      <div className="flex flex-col gap-1">
        {members.map((member) => (
          <div key={member.user_id} className="flex items-center justify-between gap-2 px-1 py-1 text-sm">
            <span className="truncate text-[#F5F7FA]">{getDisplayName(member, { patronymic: false })}</span>
            {showReason && member.reason !== null && (
              <span className="shrink-0 text-xs text-[#8A94A6]">{REASON_LABELS[member.reason]}</span>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

export function EventAttendancePanel({ teamId, event, isCaptain }: EventAttendancePanelProps) {
  const { accessToken, user } = useAuth()
  const [roster, setRoster] = useState<TeamEventAttendanceRosterRead | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)

  const [isEditing, setIsEditing] = useState(false)
  const [choice, setChoice] = useState<TeamEventAttendanceStatus | null>(null)
  const [reason, setReason] = useState<TeamEventAbsenceReason>('other')
  const [reasonNote, setReasonNote] = useState('')
  const [isSaving, setIsSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)

  const [isNudging, setIsNudging] = useState(false)
  const [nudgeMessage, setNudgeMessage] = useState<string | null>(null)
  const [nudgeError, setNudgeError] = useState<string | null>(null)

  async function refresh() {
    if (accessToken === null) {
      return
    }
    const result = await teamEventsApi.getAttendanceRoster(teamId, event.id, accessToken)
    setRoster(result)
  }

  useEffect(() => {
    let cancelled = false
    refresh().catch((err: unknown) => {
      if (!cancelled) {
        setLoadError(err instanceof ApiError ? err.message : 'Не удалось загрузить явку.')
      }
    })
    return () => {
      cancelled = true
    }
    // event.starts_at (not just event.id) -- is_locked is computed
    // server-side from starts_at, so a captain's reschedule must re-fetch
    // the roster while this tab stays mounted, not just on first load.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accessToken, teamId, event.id, event.starts_at])

  if (roster === null) {
    return loadError !== null ? (
      <FormError message={loadError} />
    ) : (
      <p className="text-sm text-[#8A94A6]">Загрузка...</p>
    )
  }

  const myStatus: TeamEventAttendanceStatus | 'unmarked' = roster.going.some((m) => m.user_id === user?.id)
    ? 'going'
    : roster.not_going.some((m) => m.user_id === user?.id)
      ? 'not_going'
      : 'unmarked'

  function startEditing() {
    setChoice(myStatus === 'unmarked' ? null : (myStatus as TeamEventAttendanceStatus))
    setReason('other')
    setReasonNote('')
    setSaveError(null)
    setIsEditing(true)
  }

  async function handleSave() {
    if (accessToken === null || choice === null) {
      return
    }
    setIsSaving(true)
    setSaveError(null)
    try {
      await teamEventsApi.setMyAttendance(
        teamId,
        event.id,
        {
          status: choice,
          reason: choice === 'not_going' ? reason : undefined,
          reason_note: choice === 'not_going' && reasonNote.trim() !== '' ? reasonNote.trim() : undefined,
        },
        accessToken,
      )
      setIsEditing(false)
      await refresh()
    } catch (err) {
      setSaveError(err instanceof ApiError ? err.message : 'Не удалось сохранить явку.')
    } finally {
      setIsSaving(false)
    }
  }

  async function handleNudge() {
    if (accessToken === null) {
      return
    }
    setIsNudging(true)
    setNudgeError(null)
    setNudgeMessage(null)
    try {
      const result = await teamEventsApi.sendAttendanceNudge(teamId, event.id, accessToken)
      setNudgeMessage(`Напоминание отправлено: ${result.notified_count}`)
    } catch (err) {
      setNudgeError(err instanceof ApiError ? err.message : 'Не удалось отправить напоминание.')
    } finally {
      setIsNudging(false)
    }
  }

  return (
    <div className="flex flex-col gap-4">
      {roster.is_locked && (
        <div className={`p-3 text-sm text-[#8A94A6] ${CARD_CLASS}`}>
          Явка закрыта -- до события меньше 2 часов. Изменить ответ уже нельзя.
        </div>
      )}

      {!roster.is_locked && !isEditing && (
        <div className={`flex items-center justify-between gap-3 p-3 ${CARD_CLASS}`}>
          <span className="text-sm text-[#F5F7FA]">
            {myStatus === 'going' && 'Ты отметился: буду'}
            {myStatus === 'not_going' && 'Ты отметился: не буду'}
            {myStatus === 'unmarked' && 'Ты ещё не отметился'}
          </span>
          <Button type="button" variant="neutral" className="!px-3 !py-1.5 !text-xs" onClick={startEditing}>
            {myStatus === 'unmarked' ? 'Отметиться' : 'Изменить'}
          </Button>
        </div>
      )}

      {!roster.is_locked && isEditing && (
        <div className={`flex flex-col gap-3 p-3 ${CARD_CLASS}`}>
          <div className="flex gap-2">
            <ChoiceCard
              title="Буду"
              description="Приду на событие"
              selected={choice === 'going'}
              onClick={() => setChoice('going')}
            />
            <ChoiceCard
              title="Не буду"
              description="Не смогу прийти"
              selected={choice === 'not_going'}
              onClick={() => setChoice('not_going')}
            />
          </div>
          {choice === 'not_going' && (
            <>
              <SelectField
                label="Причина"
                options={REASON_OPTIONS}
                value={reason}
                onChange={(e) => setReason(e.target.value as TeamEventAbsenceReason)}
              />
              <TextField
                label="Комментарий (необязательно)"
                value={reasonNote}
                onChange={(e) => setReasonNote(e.target.value)}
              />
            </>
          )}
          <FormError message={saveError} />
          <div className="flex gap-2">
            <Button type="button" variant="neutral" className="flex-1" onClick={() => setIsEditing(false)}>
              Отмена
            </Button>
            <Button type="button" className="flex-1" disabled={choice === null} isLoading={isSaving} onClick={handleSave}>
              Сохранить
            </Button>
          </div>
        </div>
      )}

      {isCaptain && (
        <div className={`flex flex-col gap-2 p-3 ${CARD_CLASS}`}>
          <Button
            type="button"
            variant="neutral"
            onClick={handleNudge}
            isLoading={isNudging}
            disabled={roster.unmarked.length === 0}
          >
            Напомнить неотметившимся ({roster.unmarked.length})
          </Button>
          {nudgeMessage !== null && <p className="text-xs text-accent-ice">{nudgeMessage}</p>}
          <FormError message={nudgeError} />
        </div>
      )}

      <div className={`flex flex-col gap-4 p-3 ${CARD_CLASS}`}>
        <RosterSection title="Буду" members={roster.going} />
        <RosterSection title="Не буду" members={roster.not_going} showReason />
        <RosterSection title="Не отметились" members={roster.unmarked} />
      </div>
    </div>
  )
}
