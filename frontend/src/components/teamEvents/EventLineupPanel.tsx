import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { Button } from '../ui/Button'
import { CARD_CLASS } from '../ui/cardStyle'
import { EmptyState } from '../ui/EmptyState'
import { FormError } from '../ui/FormError'
import { TextField } from '../ui/TextField'
import * as teamEventsApi from '../../api/teamEvents'
import { ApiError } from '../../api/client'
import { useAuth } from '../../hooks/useAuth'
import type { TeamEventLineupRead, TeamEventRead } from '../../types/teamEvent'
import { POSITION_LABELS } from '../../types/user'
import { getDisplayName } from '../../utils/displayName'

interface EventLineupPanelProps {
  teamId: string
  event: TeamEventRead
  isCaptain: boolean
}

const DEFAULT_COLORS = ['#3B82F6', '#EF4444', '#22C55E', '#EAB308', '#A855F7', '#F97316']

export function EventLineupPanel({ teamId, event, isCaptain }: EventLineupPanelProps) {
  const { accessToken } = useAuth()
  const [lineup, setLineup] = useState<TeamEventLineupRead | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [busyUserId, setBusyUserId] = useState<string | null>(null)

  const [newGroupName, setNewGroupName] = useState('')
  const [newGroupColor, setNewGroupColor] = useState(DEFAULT_COLORS[0])
  const [isCreatingGroup, setIsCreatingGroup] = useState(false)

  const [isPublishing, setIsPublishing] = useState(false)

  async function refresh() {
    if (accessToken === null) {
      return
    }
    const result = await teamEventsApi.getLineup(teamId, event.id, accessToken)
    setLineup(result)
  }

  useEffect(() => {
    let cancelled = false
    refresh().catch((err: unknown) => {
      if (!cancelled) {
        setLoadError(err instanceof ApiError ? err.message : 'Не удалось загрузить состав.')
      }
    })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accessToken, teamId, event.id])

  async function handleCreateGroup(e: FormEvent) {
    e.preventDefault()
    if (accessToken === null) {
      return
    }
    setIsCreatingGroup(true)
    setActionError(null)
    try {
      await teamEventsApi.createLineupGroup(
        teamId,
        event.id,
        {
          name: newGroupName.trim() || undefined,
          color: event.event_type === 'training' ? newGroupColor : undefined,
        },
        accessToken,
      )
      setNewGroupName('')
      await refresh()
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : 'Не удалось создать группу.')
    } finally {
      setIsCreatingGroup(false)
    }
  }

  async function handleDeleteGroup(groupId: string) {
    if (accessToken === null) {
      return
    }
    setActionError(null)
    try {
      await teamEventsApi.deleteLineupGroup(teamId, event.id, groupId, accessToken)
      await refresh()
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : 'Не удалось удалить группу.')
    }
  }

  async function handleAssign(userId: string, groupId: string) {
    if (accessToken === null || groupId === '') {
      return
    }
    setBusyUserId(userId)
    setActionError(null)
    try {
      await teamEventsApi.assignLineupPlayer(teamId, event.id, userId, groupId, accessToken)
      await refresh()
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : 'Не удалось добавить игрока в группу.')
    } finally {
      setBusyUserId(null)
    }
  }

  async function handleUnassign(userId: string) {
    if (accessToken === null) {
      return
    }
    setBusyUserId(userId)
    setActionError(null)
    try {
      await teamEventsApi.unassignLineupPlayer(teamId, event.id, userId, accessToken)
      await refresh()
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : 'Не удалось убрать игрока из группы.')
    } finally {
      setBusyUserId(null)
    }
  }

  async function handlePublish() {
    if (accessToken === null) {
      return
    }
    setIsPublishing(true)
    setActionError(null)
    try {
      const updated = await teamEventsApi.publishLineup(teamId, event.id, accessToken)
      setLineup(updated)
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : 'Не удалось опубликовать состав.')
    } finally {
      setIsPublishing(false)
    }
  }

  if (lineup === null) {
    return loadError !== null ? (
      <FormError message={loadError} />
    ) : (
      <p className="text-sm text-[#8A94A6]">Загрузка...</p>
    )
  }

  if (!isCaptain && lineup.groups === null) {
    return (
      <EmptyState
        icon="ti-users-group"
        title="Тренер ещё собирает состав"
        hint="Как только состав будет опубликован, ты увидишь свою группу."
      />
    )
  }

  const groups = lineup.groups ?? []
  const unassigned = lineup.unassigned ?? []
  const groupOptions = groups.map((g) => ({ value: g.id, label: g.name ?? 'Без названия' }))

  return (
    <div className="flex flex-col gap-4">
      {isCaptain && (
        <div className="flex items-center justify-between gap-3">
          <span
            className={`rounded-full px-2.5 py-1 text-xs font-medium uppercase tracking-wide ${
              lineup.lineup_status === 'published' ? 'bg-accent-ice/15 text-accent-ice' : 'bg-white/10 text-[#8A94A6]'
            }`}
          >
            {lineup.lineup_status === 'published' ? 'Состав опубликован' : 'Черновик -- видно только тебе'}
          </span>
          {lineup.lineup_status !== 'published' && (
            <Button type="button" onClick={handlePublish} isLoading={isPublishing} className="!px-3 !py-1.5 !text-xs">
              Опубликовать
            </Button>
          )}
        </div>
      )}

      <FormError message={actionError} />

      {groups.length === 0 && <EmptyState icon="ti-users-group" title="Пока нет ни одной группы" />}

      <div className="flex flex-col gap-3">
        {groups.map((group) => (
          <div key={group.id} className={`flex flex-col gap-2 p-3 ${CARD_CLASS}`}>
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                {group.color !== null && (
                  <span
                    className="h-3 w-3 shrink-0 rounded-full"
                    style={{ backgroundColor: group.color }}
                    aria-hidden="true"
                  />
                )}
                <span className="text-sm font-medium text-[#F5F7FA]">{group.name ?? 'Без названия'}</span>
              </div>
              {isCaptain && (
                <button
                  type="button"
                  onClick={() => handleDeleteGroup(group.id)}
                  aria-label="Удалить группу"
                  className="text-[#8A94A6] transition-colors hover:text-red-400"
                >
                  <i className="ti ti-trash" aria-hidden="true" />
                </button>
              )}
            </div>
            {group.players.length === 0 && <span className="text-xs text-[#8A94A6]">Пусто</span>}
            {group.players.map((player) => (
              <div key={player.user_id} className="flex items-center justify-between gap-2 pl-5 text-sm">
                <span className="truncate text-[#F5F7FA]">
                  {getDisplayName(player, { patronymic: false })}
                  {player.position !== null && (
                    <span className="ml-1.5 text-xs text-[#8A94A6]">{POSITION_LABELS[player.position]}</span>
                  )}
                </span>
                {isCaptain && (
                  <button
                    type="button"
                    disabled={busyUserId === player.user_id}
                    onClick={() => handleUnassign(player.user_id)}
                    aria-label="Убрать из группы"
                    className="shrink-0 text-[#8A94A6] transition-colors hover:text-red-400"
                  >
                    <i className="ti ti-x" aria-hidden="true" />
                  </button>
                )}
              </div>
            ))}
          </div>
        ))}
      </div>

      {isCaptain && unassigned.length > 0 && (
        <div className={`flex flex-col gap-2 p-3 ${CARD_CLASS}`}>
          <span className="text-xs font-medium uppercase tracking-wide text-[#8A94A6]">
            Не распределены ({unassigned.length})
          </span>
          {unassigned.map((player) => (
            <div key={player.user_id} className="flex items-center justify-between gap-2 text-sm">
              <span className="truncate text-[#F5F7FA]">
                {getDisplayName(player, { patronymic: false })}
                {player.position !== null && (
                  <span className="ml-1.5 text-xs text-[#8A94A6]">{POSITION_LABELS[player.position]}</span>
                )}
              </span>
              <select
                disabled={busyUserId === player.user_id || groupOptions.length === 0}
                onChange={(e) => handleAssign(player.user_id, e.target.value)}
                value=""
                className="shrink-0 rounded border border-white/10 bg-dark-bg px-2 py-1 text-xs text-text-primary focus:border-accent-ice focus:outline-none"
              >
                <option value="">В группу...</option>
                {groupOptions.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>
          ))}
        </div>
      )}

      {isCaptain && (
        <form onSubmit={handleCreateGroup} className={`flex flex-col gap-2 p-3 ${CARD_CLASS}`}>
          <span className="text-xs font-medium uppercase tracking-wide text-[#8A94A6]">Новая группа</span>
          <TextField
            label="Название (необязательно)"
            value={newGroupName}
            onChange={(e) => setNewGroupName(e.target.value)}
            placeholder="Например, Тройка 1"
          />
          {event.event_type === 'training' && (
            <div className="flex flex-col gap-1.5">
              <span className="text-sm text-text-secondary">Цвет</span>
              <div className="flex gap-2">
                {DEFAULT_COLORS.map((color) => (
                  <button
                    key={color}
                    type="button"
                    onClick={() => setNewGroupColor(color)}
                    aria-label={color}
                    className={`h-7 w-7 rounded-full border-2 transition-transform ${
                      newGroupColor === color ? 'scale-110 border-white' : 'border-transparent'
                    }`}
                    style={{ backgroundColor: color }}
                  />
                ))}
              </div>
            </div>
          )}
          <Button type="submit" variant="neutral" isLoading={isCreatingGroup}>
            Создать группу
          </Button>
        </form>
      )}
    </div>
  )
}
