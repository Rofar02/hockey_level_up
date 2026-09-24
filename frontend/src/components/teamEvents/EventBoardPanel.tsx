import { useState } from 'react'
import type { FormEvent } from 'react'
import { Button } from '../ui/Button'
import { CARD_CLASS } from '../ui/cardStyle'
import { EmptyState } from '../ui/EmptyState'
import { FormError } from '../ui/FormError'
import { TextField } from '../ui/TextField'
import * as teamEventsApi from '../../api/teamEvents'
import { ApiError } from '../../api/client'
import { useAuth } from '../../hooks/useAuth'
import type { TeamEventDrillRead, TeamEventRead } from '../../types/teamEvent'

interface EventBoardPanelProps {
  teamId: string
  event: TeamEventRead
  isCaptain: boolean
  onEventChange: (event: TeamEventRead) => void
}

export function EventBoardPanel({ teamId, event, isCaptain, onEventChange }: EventBoardPanelProps) {
  const { accessToken } = useAuth()
  const [actionError, setActionError] = useState<string | null>(null)
  const [busyDrillId, setBusyDrillId] = useState<string | null>(null)

  const [newTitle, setNewTitle] = useState('')
  const [newDescription, setNewDescription] = useState('')
  const [isAdding, setIsAdding] = useState(false)

  const [editingDrillId, setEditingDrillId] = useState<string | null>(null)
  const [editTitle, setEditTitle] = useState('')
  const [editDescription, setEditDescription] = useState('')

  const [isPublishing, setIsPublishing] = useState(false)

  async function refresh() {
    if (accessToken === null) {
      return
    }
    const updated = await teamEventsApi.getTeamEvent(teamId, event.id, accessToken)
    onEventChange(updated)
  }

  async function handleAdd(e: FormEvent) {
    e.preventDefault()
    if (accessToken === null || newTitle.trim() === '') {
      return
    }
    setIsAdding(true)
    setActionError(null)
    try {
      await teamEventsApi.addDrill(
        teamId,
        event.id,
        { title: newTitle.trim(), description: newDescription.trim() || undefined },
        accessToken,
      )
      setNewTitle('')
      setNewDescription('')
      await refresh()
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : 'Не удалось добавить упражнение.')
    } finally {
      setIsAdding(false)
    }
  }

  function startEdit(drill: TeamEventDrillRead) {
    setEditingDrillId(drill.id)
    setEditTitle(drill.title)
    setEditDescription(drill.description ?? '')
  }

  async function handleSaveEdit(e: FormEvent) {
    e.preventDefault()
    if (accessToken === null || editingDrillId === null || editTitle.trim() === '') {
      return
    }
    setBusyDrillId(editingDrillId)
    setActionError(null)
    try {
      await teamEventsApi.updateDrill(
        teamId,
        event.id,
        editingDrillId,
        { title: editTitle.trim(), description: editDescription.trim() || undefined },
        accessToken,
      )
      setEditingDrillId(null)
      await refresh()
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : 'Не удалось сохранить изменения.')
    } finally {
      setBusyDrillId(null)
    }
  }

  async function handleDelete(drillId: string) {
    if (accessToken === null) {
      return
    }
    setBusyDrillId(drillId)
    setActionError(null)
    try {
      await teamEventsApi.deleteDrill(teamId, event.id, drillId, accessToken)
      await refresh()
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : 'Не удалось удалить упражнение.')
    } finally {
      setBusyDrillId(null)
    }
  }

  async function handleMove(index: number, direction: -1 | 1) {
    if (accessToken === null || event.drills === null) {
      return
    }
    const drillIds = event.drills.map((d) => d.id)
    const targetIndex = index + direction
    if (targetIndex < 0 || targetIndex >= drillIds.length) {
      return
    }
    ;[drillIds[index], drillIds[targetIndex]] = [drillIds[targetIndex], drillIds[index]]
    setBusyDrillId(drillIds[index])
    setActionError(null)
    try {
      await teamEventsApi.reorderDrills(teamId, event.id, drillIds, accessToken)
      await refresh()
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : 'Не удалось изменить порядок.')
    } finally {
      setBusyDrillId(null)
    }
  }

  async function handlePublish() {
    if (accessToken === null) {
      return
    }
    setIsPublishing(true)
    setActionError(null)
    try {
      const updated = await teamEventsApi.publishBoard(teamId, event.id, accessToken)
      onEventChange(updated)
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : 'Не удалось опубликовать план.')
    } finally {
      setIsPublishing(false)
    }
  }

  if (!isCaptain && event.drills === null) {
    return (
      <EmptyState
        icon="ti-clipboard-off"
        title="Тренер ещё готовит план"
        hint="Как только план будет опубликован, ты увидишь все упражнения."
      />
    )
  }

  const drills = event.drills ?? []

  return (
    <div className="flex flex-col gap-4">
      {isCaptain && (
        <div className="flex items-center justify-between gap-3">
          <span
            className={`rounded-full px-2.5 py-1 text-xs font-medium uppercase tracking-wide ${
              event.board_status === 'published' ? 'bg-accent-ice/15 text-accent-ice' : 'bg-white/10 text-[#8A94A6]'
            }`}
          >
            {event.board_status === 'published' ? 'План опубликован' : 'Черновик -- видно только тебе'}
          </span>
          {event.board_status !== 'published' && (
            <Button type="button" onClick={handlePublish} isLoading={isPublishing} className="!px-3 !py-1.5 !text-xs">
              Опубликовать
            </Button>
          )}
        </div>
      )}

      <FormError message={actionError} />

      {drills.length === 0 && (
        <EmptyState icon="ti-clipboard-list" title="Пока нет ни одного упражнения" />
      )}

      <div className="flex flex-col gap-2">
        {drills.map((drill, index) => (
          <div key={drill.id} className={`flex flex-col gap-2 p-3 ${CARD_CLASS}`}>
            {editingDrillId === drill.id ? (
              <form onSubmit={handleSaveEdit} className="flex flex-col gap-2">
                <TextField
                  label="Название"
                  value={editTitle}
                  onChange={(e) => setEditTitle(e.target.value)}
                  required
                />
                <TextField
                  label="Описание"
                  value={editDescription}
                  onChange={(e) => setEditDescription(e.target.value)}
                />
                <div className="flex gap-2">
                  <Button
                    type="button"
                    variant="neutral"
                    className="flex-1 !py-1.5 !text-xs"
                    onClick={() => setEditingDrillId(null)}
                  >
                    Отмена
                  </Button>
                  <Button
                    type="submit"
                    isLoading={busyDrillId === drill.id}
                    className="flex-1 !py-1.5 !text-xs"
                  >
                    Сохранить
                  </Button>
                </div>
              </form>
            ) : (
              <div className="flex items-start gap-3">
                <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-white/10 text-xs text-[#8A94A6]">
                  {index + 1}
                </span>
                <div className="flex min-w-0 flex-1 flex-col gap-0.5">
                  <span className="text-sm font-medium text-[#F5F7FA]">{drill.title}</span>
                  {drill.description !== null && drill.description !== '' && (
                    <span className="text-xs text-[#8A94A6]">{drill.description}</span>
                  )}
                </div>
                {isCaptain && (
                  <div className="flex shrink-0 items-center gap-1">
                    <button
                      type="button"
                      disabled={index === 0 || busyDrillId !== null}
                      onClick={() => handleMove(index, -1)}
                      aria-label="Выше"
                      className="text-[#8A94A6] transition-colors hover:text-[#F5F7FA] disabled:opacity-30"
                    >
                      <i className="ti ti-chevron-up" aria-hidden="true" />
                    </button>
                    <button
                      type="button"
                      disabled={index === drills.length - 1 || busyDrillId !== null}
                      onClick={() => handleMove(index, 1)}
                      aria-label="Ниже"
                      className="text-[#8A94A6] transition-colors hover:text-[#F5F7FA] disabled:opacity-30"
                    >
                      <i className="ti ti-chevron-down" aria-hidden="true" />
                    </button>
                    <button
                      type="button"
                      disabled={busyDrillId !== null}
                      onClick={() => startEdit(drill)}
                      aria-label="Редактировать"
                      className="text-[#8A94A6] transition-colors hover:text-[#F5F7FA]"
                    >
                      <i className="ti ti-pencil" aria-hidden="true" />
                    </button>
                    <button
                      type="button"
                      disabled={busyDrillId !== null}
                      onClick={() => handleDelete(drill.id)}
                      aria-label="Удалить"
                      className="text-[#8A94A6] transition-colors hover:text-red-400"
                    >
                      <i className="ti ti-trash" aria-hidden="true" />
                    </button>
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
      </div>

      {isCaptain && (
        <form onSubmit={handleAdd} className={`flex flex-col gap-2 p-3 ${CARD_CLASS}`}>
          <span className="text-xs font-medium uppercase tracking-wide text-[#8A94A6]">Добавить упражнение</span>
          <TextField
            label="Название"
            value={newTitle}
            onChange={(e) => setNewTitle(e.target.value)}
            placeholder="Например, катание на короткой площадке"
          />
          <TextField
            label="Описание (необязательно)"
            value={newDescription}
            onChange={(e) => setNewDescription(e.target.value)}
          />
          <Button type="submit" variant="neutral" isLoading={isAdding} disabled={newTitle.trim() === ''}>
            Добавить
          </Button>
        </form>
      )}
    </div>
  )
}
