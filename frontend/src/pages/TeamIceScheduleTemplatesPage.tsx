import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { useParams } from 'react-router-dom'
import { BackLink } from '../components/ui/BackLink'
import { Button } from '../components/ui/Button'
import { CARD_CLASS } from '../components/ui/cardStyle'
import { EmptyState } from '../components/ui/EmptyState'
import { FormError } from '../components/ui/FormError'
import { IceGlowBackground } from '../components/ui/IceGlowBackground'
import { SelectField } from '../components/ui/SelectField'
import { Switch } from '../components/ui/Switch'
import { TextField } from '../components/ui/TextField'
import * as teamsApi from '../api/teams'
import * as teamEventsApi from '../api/teamEvents'
import { ApiError } from '../api/client'
import { useAuth } from '../hooks/useAuth'
import type { TeamRead } from '../types/team'
import type { TeamIceScheduleTemplateRead } from '../types/teamEvent'
import { WEEKDAY_LABELS } from '../utils/date'

const WEEKDAY_OPTIONS = WEEKDAY_LABELS.map((label, index) => ({ value: String(index), label }))

export function TeamIceScheduleTemplatesPage() {
  const { teamId } = useParams<{ teamId: string }>()
  const { accessToken } = useAuth()

  const [team, setTeam] = useState<TeamRead | null>(null)
  const [templates, setTemplates] = useState<TeamIceScheduleTemplateRead[] | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [busyId, setBusyId] = useState<string | null>(null)

  const [newWeekday, setNewWeekday] = useState('1')
  const [newTime, setNewTime] = useState('19:00')
  const [isCreating, setIsCreating] = useState(false)

  async function refresh() {
    if (accessToken === null || teamId === undefined) {
      return
    }
    const result = await teamEventsApi.listIceScheduleTemplates(teamId, accessToken)
    setTemplates(result)
  }

  useEffect(() => {
    if (accessToken === null || teamId === undefined) {
      return
    }
    let cancelled = false
    Promise.all([teamsApi.getTeam(teamId, accessToken), teamEventsApi.listIceScheduleTemplates(teamId, accessToken)])
      .then(([teamResult, templatesResult]) => {
        if (cancelled) {
          return
        }
        setTeam(teamResult)
        setTemplates(templatesResult)
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setLoadError(err instanceof ApiError ? err.message : 'Не удалось загрузить расписание.')
        }
      })
    return () => {
      cancelled = true
    }
  }, [accessToken, teamId])

  async function handleCreate(e: FormEvent) {
    e.preventDefault()
    if (accessToken === null || teamId === undefined) {
      return
    }
    setIsCreating(true)
    setActionError(null)
    try {
      await teamEventsApi.createIceScheduleTemplate(
        teamId,
        { weekday: Number(newWeekday), start_time: `${newTime}:00` },
        accessToken,
      )
      await refresh()
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : 'Не удалось создать расписание.')
    } finally {
      setIsCreating(false)
    }
  }

  async function handleToggleActive(template: TeamIceScheduleTemplateRead) {
    if (accessToken === null || teamId === undefined) {
      return
    }
    setBusyId(template.id)
    setActionError(null)
    try {
      await teamEventsApi.setIceScheduleTemplateActive(teamId, template.id, !template.active, accessToken)
      await refresh()
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : 'Не удалось изменить расписание.')
    } finally {
      setBusyId(null)
    }
  }

  async function handleDelete(templateId: string) {
    if (accessToken === null || teamId === undefined) {
      return
    }
    setBusyId(templateId)
    setActionError(null)
    try {
      await teamEventsApi.deleteIceScheduleTemplate(teamId, templateId, accessToken)
      await refresh()
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : 'Не удалось удалить расписание.')
    } finally {
      setBusyId(null)
    }
  }

  const isLoading = team === null || templates === null

  return (
    <div className="relative min-h-svh overflow-hidden">
      <IceGlowBackground />
      <div className="relative z-[1] mx-auto flex max-w-2xl flex-col gap-6 px-4 py-8">
        <BackLink />
        <h1 className="text-lg font-semibold text-[#F5F7FA]">Расписание льда</h1>
        <p className="text-sm text-[#8A94A6]">
          Повторяющиеся тренировки по дням недели -- система сама создаёт события на несколько недель вперёд.
        </p>

        <FormError message={loadError} />
        {isLoading && loadError === null && <p className="text-sm text-[#8A94A6]">Загрузка...</p>}

        {!isLoading && (
          <>
            <FormError message={actionError} />

            {templates.length === 0 ? (
              <EmptyState icon="ti-calendar-repeat" title="Пока нет повторяющихся тренировок" />
            ) : (
              <div className="flex flex-col gap-2">
                {templates.map((template) => (
                  <div key={template.id} className={`flex items-center gap-3 p-3 ${CARD_CLASS}`}>
                    <span className="flex-1 text-sm text-[#F5F7FA]">
                      {WEEKDAY_LABELS[template.weekday]}, {template.start_time.slice(0, 5)}
                    </span>
                    {team.is_captain && (
                      <>
                        <Switch
                          checked={template.active}
                          disabled={busyId === template.id}
                          onClick={() => handleToggleActive(template)}
                        />
                        <button
                          type="button"
                          disabled={busyId === template.id}
                          onClick={() => handleDelete(template.id)}
                          aria-label="Удалить"
                          className="text-[#8A94A6] transition-colors hover:text-red-400"
                        >
                          <i className="ti ti-trash" aria-hidden="true" />
                        </button>
                      </>
                    )}
                  </div>
                ))}
              </div>
            )}

            {team.is_captain && (
              <form onSubmit={handleCreate} className={`flex flex-col gap-3 p-3 ${CARD_CLASS}`}>
                <span className="text-xs font-medium uppercase tracking-wide text-[#8A94A6]">Добавить слот</span>
                <SelectField
                  label="День недели"
                  options={WEEKDAY_OPTIONS}
                  value={newWeekday}
                  onChange={(e) => setNewWeekday(e.target.value)}
                />
                <TextField
                  label="Время"
                  type="time"
                  value={newTime}
                  onChange={(e) => setNewTime(e.target.value)}
                  required
                />
                <Button type="submit" isLoading={isCreating}>
                  Добавить
                </Button>
              </form>
            )}
          </>
        )}
      </div>
    </div>
  )
}
