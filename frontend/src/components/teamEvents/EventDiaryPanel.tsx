import { useEffect, useState } from 'react'
import { Button } from '../ui/Button'
import { CARD_CLASS } from '../ui/cardStyle'
import { FormError } from '../ui/FormError'
import * as teamEventsApi from '../../api/teamEvents'
import { ApiError } from '../../api/client'
import { useAuth } from '../../hooks/useAuth'
import type { TeamEventDiaryEntryRead, TeamEventRead } from '../../types/teamEvent'

interface EventDiaryPanelProps {
  teamId: string
  event: TeamEventRead
}

export function EventDiaryPanel({ teamId, event }: EventDiaryPanelProps) {
  const { accessToken } = useAuth()
  const [entry, setEntry] = useState<TeamEventDiaryEntryRead | null | undefined>(undefined)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [note, setNote] = useState('')
  const [isEditing, setIsEditing] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [justGrantedRewards, setJustGrantedRewards] = useState(false)

  useEffect(() => {
    if (accessToken === null) {
      return
    }
    let cancelled = false
    teamEventsApi
      .getMyDiaryEntry(teamId, event.id, accessToken)
      .then((result) => {
        if (!cancelled) {
          setEntry(result)
          setIsEditing(result === null)
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setLoadError(err instanceof ApiError ? err.message : 'Не удалось загрузить дневник.')
        }
      })
    return () => {
      cancelled = true
    }
  }, [accessToken, teamId, event.id])

  async function handleSave(noteValue: string | null) {
    if (accessToken === null) {
      return
    }
    const isFirstSave = entry === null
    setIsSaving(true)
    setSaveError(null)
    try {
      const saved = await teamEventsApi.saveMyDiaryEntry(teamId, event.id, { note: noteValue }, accessToken)
      setEntry(saved)
      setIsEditing(false)
      setJustGrantedRewards(isFirstSave)
    } catch (err) {
      setSaveError(err instanceof ApiError ? err.message : 'Не удалось сохранить запись.')
    } finally {
      setIsSaving(false)
    }
  }

  if (entry === undefined) {
    return loadError !== null ? (
      <FormError message={loadError} />
    ) : (
      <p className="text-sm text-[#8A94A6]">Загрузка...</p>
    )
  }

  if (!isEditing && entry !== null) {
    return (
      <div className="flex flex-col gap-3">
        {justGrantedRewards && (
          <div className={`flex items-center gap-2 p-3 text-sm text-accent-ice ${CARD_CLASS}`}>
            <i className="ti ti-sparkles" aria-hidden="true" />
            Начислены характеристики и +50 XP за тренировку
          </div>
        )}
        <div className={`flex flex-col gap-2 p-3 ${CARD_CLASS}`}>
          <span className="text-xs font-medium uppercase tracking-wide text-[#8A94A6]">Твоя запись</span>
          {entry.note === null || entry.note === '' ? (
            <span className="text-sm text-[#8A94A6]">Без заметки -- отмечено как пройдено.</span>
          ) : (
            <p className="whitespace-pre-wrap text-sm text-[#F5F7FA]">{entry.note}</p>
          )}
          <Button
            type="button"
            variant="neutral"
            className="mt-1 self-start !px-3 !py-1.5 !text-xs"
            onClick={() => {
              setNote(entry.note ?? '')
              setIsEditing(true)
            }}
          >
            Редактировать
          </Button>
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm text-[#8A94A6]">
        Как прошла тренировка? Заметка (или явный пропуск) начисляет характеристики и XP -- один раз, за первое
        сохранение.
      </p>
      <textarea
        value={note}
        onChange={(e) => setNote(e.target.value)}
        placeholder="Что получилось, а что нет..."
        maxLength={2000}
        className="min-h-40 w-full resize-none rounded border border-white/10 bg-dark-bg p-3 text-sm text-text-primary outline-none placeholder:text-text-secondary/60 focus:border-accent-ice"
      />
      <FormError message={saveError} />
      <Button type="button" onClick={() => handleSave(note.trim() || null)} isLoading={isSaving}>
        Сохранить
      </Button>
      {entry === null && (
        <button
          type="button"
          onClick={() => handleSave(null)}
          disabled={isSaving}
          className="text-xs text-text-secondary underline decoration-dotted underline-offset-2 transition-colors hover:text-text-primary disabled:opacity-50"
        >
          Пропустить без заметки
        </button>
      )}
    </div>
  )
}
