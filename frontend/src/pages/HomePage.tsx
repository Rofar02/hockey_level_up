import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Button } from '../components/ui/Button'
import { FormError } from '../components/ui/FormError'
import * as progressApi from '../api/progress'
import * as scheduleApi from '../api/schedule'
import * as trainingBlockApi from '../api/trainingBlock'
import { ApiError } from '../api/client'
import { useAuth } from '../hooks/useAuth'
import { DAY_SESSION_TYPE_LABELS } from '../types/schedule'
import type { WeeklyPlanRead } from '../types/schedule'
import { BLOCK_PHASE_LABELS } from '../types/trainingBlock'
import type { TrainingBlockRead } from '../types/trainingBlock'
import type { TrainingStreakRead } from '../types/progress'
import { WEEKDAY_LABELS, formatShortDate, parseIsoDate, toIsoDate } from '../utils/date'
import { loadOptional } from '../utils/loadOptional'

export function HomePage() {
  const { user, logout, accessToken } = useAuth()
  const navigate = useNavigate()

  const [trainingBlock, setTrainingBlock] = useState<TrainingBlockRead | null>(null)
  const [weeklyPlan, setWeeklyPlan] = useState<WeeklyPlanRead | null>(null)
  const [streak, setStreak] = useState<TrainingStreakRead | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (accessToken === null) {
      return
    }
    let cancelled = false
    Promise.all([
      loadOptional(trainingBlockApi.getCurrentTrainingBlock(accessToken)),
      loadOptional(scheduleApi.getCurrentWeeklyPlan(accessToken)),
      progressApi.getMyStreak(accessToken),
    ])
      .then(([block, plan, streakResult]) => {
        if (cancelled) {
          return
        }
        setTrainingBlock(block)
        setWeeklyPlan(plan)
        setStreak(streakResult)
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : 'Не удалось загрузить дашборд.')
        }
      })
      .finally(() => {
        if (!cancelled) {
          setIsLoading(false)
        }
      })
    return () => {
      cancelled = true
    }
  }, [accessToken])

  const todayIso = toIsoDate(new Date())
  const today = weeklyPlan?.day_plans.find((day) => day.date === todayIso) ?? null

  function renderTodayAction() {
    if (today === null || today.session_type === 'rest') {
      return (
        <p className="text-sm text-text-secondary">
          {today === null ? 'Нет плана на сегодня' : 'Сегодня день отдыха'}
        </p>
      )
    }
    if (today.training_session === null) {
      return <p className="text-sm text-text-secondary">Нет плана на сегодня</p>
    }
    const dayId = today.id
    return (
      <Button onClick={() => navigate(`/training/${dayId}`)} className="self-start">
        Начать тренировку
      </Button>
    )
  }

  return (
    <div className="relative min-h-svh">
      <div className="absolute inset-0 bg-[url('/images/arena-bg.webp')] bg-cover bg-center" />
      {/* Lighter than LoginPage's bg-dark-bg/80 -- the dashboard should read
          as "on the ice", with the arena clearly visible behind the UI. */}
      <div className="absolute inset-0 bg-dark-bg/50" />
      <div className="relative mx-auto flex min-h-svh max-w-3xl flex-col gap-6 px-4 py-8">
        <div className="flex items-start justify-between gap-4">
          <div className="flex flex-col gap-2">
            <h1 className="text-2xl font-semibold">Привет, {user?.username}</h1>
            {trainingBlock !== null && (
              <span className="w-fit rounded-full border border-white/15 px-3 py-1 text-xs text-text-secondary">
                Блок {trainingBlock.block_number} · неделя {trainingBlock.week_in_block}/4 ·{' '}
                {BLOCK_PHASE_LABELS[trainingBlock.phase]}
              </span>
            )}
          </div>
          <div className="flex items-center gap-3">
            {streak !== null && (
              <div className="flex items-center gap-1.5 rounded-md border border-white/5 bg-dark-card px-3 py-2">
                <i className="ti ti-flame text-accent-persimmon" aria-hidden="true" />
                <span className="font-mono text-sm">{streak.current_streak}</span>
              </div>
            )}
            <Link
              to="/profile"
              className="rounded border border-white/15 px-4 py-2.5 font-medium text-text-primary transition-colors hover:bg-white/5"
            >
              Профиль
            </Link>
            <Button variant="neutral" onClick={logout}>
              Выйти
            </Button>
          </div>
        </div>

        {!isLoading && renderTodayAction()}

        <FormError message={error} />

        {isLoading && <p className="text-sm text-text-secondary">Загрузка...</p>}

        {!isLoading && weeklyPlan === null && (
          <Button onClick={() => navigate('/schedule/new')} className="self-start">
            Спланировать неделю
          </Button>
        )}

        {!isLoading && weeklyPlan !== null && (
          <div className="flex flex-col gap-2">
            <button
              type="button"
              onClick={() => navigate('/schedule/new')}
              className="self-end text-sm text-accent-ice hover:underline"
            >
              Изменить неделю
            </button>
            <div className="grid grid-cols-7 gap-2">
              {weeklyPlan.day_plans.map((day) => {
                const isToday = day.date === todayIso
                const isClickable = day.session_type !== 'rest'
                const dayDate = parseIsoDate(day.date)
                const className = `flex flex-col rounded-md border p-3 text-left transition-colors ${
                  isToday ? 'border-accent-ice' : 'border-white/5'
                } ${isClickable ? 'bg-dark-card hover:border-white/20' : 'bg-dark-card/50'}`

                const content = (
                  <>
                    <p className="text-xs text-text-secondary">{WEEKDAY_LABELS[(dayDate.getDay() + 6) % 7]}</p>
                    <p className="font-mono text-xs text-text-secondary">{formatShortDate(dayDate)}</p>
                    <p className="mt-2 text-sm font-medium">{DAY_SESSION_TYPE_LABELS[day.session_type]}</p>
                  </>
                )

                if (isClickable) {
                  return (
                    <button
                      key={day.id}
                      type="button"
                      onClick={() => navigate(`/training/${day.id}`)}
                      className={className}
                    >
                      {content}
                    </button>
                  )
                }
                return (
                  <div key={day.id} className={className}>
                    {content}
                  </div>
                )
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
