import { useState } from 'react'
import type { FormEvent } from 'react'
import * as teamEventsApi from '../../api/teamEvents'
import { ApiError } from '../../api/client'
import { useAuth } from '../../hooks/useAuth'
import type { TeamEventRead } from '../../types/teamEvent'
import { Button } from '../ui/Button'
import { FormError } from '../ui/FormError'

// A played game's final score (2026-10-09): everyone sees it, the captain
// enters it -- wins and goals on the team card are counted from it.
export function GameScoreBlock({
  teamId,
  event,
  isCaptain,
  onEventChange,
}: {
  teamId: string
  event: TeamEventRead
  isCaptain: boolean
  onEventChange: (event: TeamEventRead) => void
}) {
  const { accessToken } = useAuth()
  const hasScore = event.our_score != null && event.opponent_score != null
  const [isEditing, setIsEditing] = useState(false)
  const [our, setOur] = useState(event.our_score != null ? String(event.our_score) : '')
  const [their, setTheir] = useState(event.opponent_score != null ? String(event.opponent_score) : '')
  const [isSaving, setIsSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const started = new Date(event.starts_at).getTime() <= Date.now()
  if (event.event_type !== 'game' || event.status !== 'scheduled' || !started) {
    return null
  }
  if (!hasScore && !isCaptain) {
    return null
  }

  const valid = /^\d{1,2}$/.test(our) && /^\d{1,2}$/.test(their)

  async function handleSave(formEvent: FormEvent) {
    formEvent.preventDefault()
    if (accessToken === null || !valid) {
      return
    }
    setError(null)
    setIsSaving(true)
    try {
      onEventChange(
        await teamEventsApi.setTeamEventScore(
          teamId,
          event.id,
          { our_score: Number(our), opponent_score: Number(their) },
          accessToken,
        ),
      )
      setIsEditing(false)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Не удалось сохранить счёт.')
    } finally {
      setIsSaving(false)
    }
  }

  if (hasScore && !isEditing) {
    return (
      <div className="flex items-center justify-between gap-3 border-t border-white/5 pt-3">
        <span className="text-sm text-[#8A94A6]">Счёт</span>
        <span className="font-display text-2xl font-bold text-[#F5F7FA]">
          {event.our_score} : {event.opponent_score}
        </span>
        {isCaptain && (
          <button type="button" onClick={() => setIsEditing(true)} className="text-xs text-accent-ice">
            Изменить
          </button>
        )}
      </div>
    )
  }

  if (!isEditing) {
    return (
      <div className="flex items-center justify-between gap-3 border-t border-white/5 pt-3">
        <span className="text-sm text-[#8A94A6]">Внесите счёт — по нему считаются победы на карточке команды.</span>
        <Button type="button" className="shrink-0 !px-3 !py-1.5 !text-xs" onClick={() => setIsEditing(true)}>
          Внести счёт
        </Button>
      </div>
    )
  }

  return (
    <form onSubmit={handleSave} className="flex flex-col gap-2 border-t border-white/5 pt-3">
      <div className="flex items-center gap-2">
        <label className="flex flex-1 flex-col gap-1 text-xs text-[#8A94A6]">
          Мы
          <input
            inputMode="numeric"
            value={our}
            onChange={(e) => setOur(e.target.value.replace(/\D/g, '').slice(0, 2))}
            className="rounded border border-white/10 bg-dark-bg px-3 py-2 text-center font-display text-xl text-text-primary focus:border-accent-ice focus:outline-none"
          />
        </label>
        <span className="mt-5 font-display text-xl text-[#8A94A6]">:</span>
        <label className="flex flex-1 flex-col gap-1 text-xs text-[#8A94A6]">
          {event.opponent_name ?? 'Соперник'}
          <input
            inputMode="numeric"
            value={their}
            onChange={(e) => setTheir(e.target.value.replace(/\D/g, '').slice(0, 2))}
            className="rounded border border-white/10 bg-dark-bg px-3 py-2 text-center font-display text-xl text-text-primary focus:border-accent-ice focus:outline-none"
          />
        </label>
      </div>
      <FormError message={error} />
      <div className="flex gap-2">
        <Button type="submit" isLoading={isSaving} disabled={!valid} className="!px-3 !py-1.5 !text-xs">
          Сохранить
        </Button>
        <Button type="button" variant="neutral" className="!px-3 !py-1.5 !text-xs" onClick={() => setIsEditing(false)}>
          Отмена
        </Button>
      </div>
    </form>
  )
}
