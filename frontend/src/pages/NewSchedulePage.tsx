import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { BackLink } from '../components/ui/BackLink'
import { Button } from '../components/ui/Button'
import { FormError } from '../components/ui/FormError'
import * as scheduleApi from '../api/schedule'
import { ApiError } from '../api/client'
import { useAuth } from '../hooks/useAuth'
import { DAY_SESSION_TYPE_LABELS } from '../types/schedule'
import type { DaySessionType, WeeklyPlanRead } from '../types/schedule'
import { WEEKDAY_LABELS, addDays, formatShortDate, getMondayOfCurrentWeek, parseIsoDate, toIsoDate } from '../utils/date'
import { loadOptional } from '../utils/loadOptional'

const SESSION_TYPE_OPTIONS: DaySessionType[] = ['on_ice', 'off_ice', 'rest']

const monday = getMondayOfCurrentWeek()
const NEW_WEEK_DATES = Array.from({ length: 7 }, (_, i) => addDays(monday, i))

interface DayRow {
  isoDate: string
  date: Date
  sessionType: DaySessionType
  // Unused (always equal to sessionType) in create mode -- lets the same
  // row shape drive both the "what changed" diff for PATCH and the create
  // flow's plain "send everything" payload.
  originalSessionType: DaySessionType
  // True once the day already has a completed SessionBlock -- edit mode
  // only, always false while creating a brand new week.
  locked: boolean
}

function rowsFromPlan(plan: WeeklyPlanRead): DayRow[] {
  return plan.day_plans.map((day) => ({
    isoDate: day.date,
    date: parseIsoDate(day.date),
    sessionType: day.session_type,
    originalSessionType: day.session_type,
    locked: day.training_session?.blocks.some((block) => block.completed_at !== null) ?? false,
  }))
}

function rowsForNewWeek(): DayRow[] {
  return NEW_WEEK_DATES.map((date) => ({
    isoDate: toIsoDate(date),
    date,
    sessionType: 'rest',
    originalSessionType: 'rest',
    locked: false,
  }))
}

export function NewSchedulePage() {
  const { accessToken } = useAuth()
  const navigate = useNavigate()

  const [mode, setMode] = useState<'loading' | 'create' | 'edit'>('loading')
  const [rows, setRows] = useState<DayRow[]>([])
  const [loadError, setLoadError] = useState<string | null>(null)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  useEffect(() => {
    if (accessToken === null) {
      return
    }
    let cancelled = false
    loadOptional(scheduleApi.getCurrentWeeklyPlan(accessToken))
      .then((plan) => {
        if (cancelled) {
          return
        }
        if (plan === null) {
          setMode('create')
          setRows(rowsForNewWeek())
        } else {
          setMode('edit')
          setRows(rowsFromPlan(plan))
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setLoadError(err instanceof ApiError ? err.message : 'Не удалось загрузить неделю.')
        }
      })
    return () => {
      cancelled = true
    }
  }, [accessToken])

  function setDayType(index: number, type: DaySessionType) {
    setRows((previous) => previous.map((row, i) => (i === index ? { ...row, sessionType: type } : row)))
  }

  async function handleCreate() {
    if (accessToken === null) {
      return
    }
    setSubmitError(null)
    setIsSubmitting(true)
    try {
      await scheduleApi.createWeeklyPlan(
        { days: rows.map((row) => ({ date: row.isoDate, session_type: row.sessionType })) },
        accessToken,
      )
      navigate('/', { replace: true })
    } catch (err) {
      setSubmitError(
        err instanceof ApiError ? err.message : 'Не удалось сохранить план недели. Попробуйте ещё раз.',
      )
    } finally {
      setIsSubmitting(false)
    }
  }

  async function handleSaveChanges() {
    if (accessToken === null) {
      return
    }
    const changed = rows.filter((row) => !row.locked && row.sessionType !== row.originalSessionType)
    if (changed.length === 0) {
      navigate('/', { replace: true })
      return
    }

    setSubmitError(null)
    setIsSubmitting(true)
    try {
      const result = await scheduleApi.patchCurrentWeeklyPlan(
        { days: changed.map((row) => ({ date: row.isoDate, session_type: row.sessionType })) },
        accessToken,
      )
      if (result.conflicts.length > 0) {
        setRows(rowsFromPlan(result.weekly_plan))
        setSubmitError(
          result.conflicts
            .map((conflict) => `${formatShortDate(parseIsoDate(conflict.date))}: ${conflict.detail}`)
            .join('; '),
        )
        return
      }
      navigate('/', { replace: true })
    } catch (err) {
      setSubmitError(
        err instanceof ApiError ? err.message : 'Не удалось сохранить изменения. Попробуйте ещё раз.',
      )
    } finally {
      setIsSubmitting(false)
    }
  }

  if (mode === 'loading') {
    return (
      <div className="mx-auto flex min-h-svh max-w-2xl flex-col gap-6 px-4 py-10">
        <BackLink />
        <p className="text-sm text-text-secondary">Загрузка...</p>
      </div>
    )
  }

  return (
    <div className="mx-auto flex min-h-svh max-w-2xl flex-col gap-6 px-4 py-10">
      <div className="flex flex-col gap-2">
        <BackLink />
        <h1 className="text-xl font-semibold">
          {mode === 'edit' ? 'Изменить неделю' : 'Спланировать неделю'}
        </h1>
      </div>

      <FormError message={loadError} />

      {loadError === null && (
        <>
          <div className="flex flex-col gap-3">
            {rows.map((row, index) => (
              <div
                key={row.isoDate}
                className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-white/5 bg-dark-card p-3"
              >
                <div className="flex items-baseline gap-2">
                  <span className="text-sm font-medium text-text-primary">{WEEKDAY_LABELS[index]}</span>
                  <span className="font-mono text-sm text-text-secondary">{formatShortDate(row.date)}</span>
                </div>
                {row.locked ? (
                  <div className="flex items-center gap-2">
                    <span className="text-sm text-text-secondary">
                      {DAY_SESSION_TYPE_LABELS[row.sessionType]}
                    </span>
                    <span className="rounded border border-white/10 px-2 py-1 text-xs text-text-secondary">
                      уже начат
                    </span>
                  </div>
                ) : (
                  <div className="flex gap-2">
                    {SESSION_TYPE_OPTIONS.map((option) => (
                      <button
                        key={option}
                        type="button"
                        onClick={() => setDayType(index, option)}
                        className={`rounded border px-3 py-1.5 text-sm font-medium transition-colors ${
                          row.sessionType === option
                            ? 'border-accent-ice bg-accent-ice/10 text-accent-ice'
                            : 'border-white/15 text-text-secondary hover:border-white/30 hover:text-text-primary'
                        }`}
                      >
                        {DAY_SESSION_TYPE_LABELS[option]}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
          <FormError message={submitError} />
          <Button
            onClick={mode === 'edit' ? handleSaveChanges : handleCreate}
            isLoading={isSubmitting}
            className="self-end"
          >
            {mode === 'edit' ? 'Сохранить изменения' : 'Сгенерировать план'}
          </Button>
        </>
      )}
    </div>
  )
}
