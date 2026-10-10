import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import * as dayReportApi from '../api/dayReport'
import { ApiError } from '../api/client'
import { MuscleLoadChart } from '../components/MuscleLoadChart'
import { BackLink } from '../components/ui/BackLink'
import { CARD_CLASS } from '../components/ui/cardStyle'
import { FormError } from '../components/ui/FormError'
import { IceGlowBackground } from '../components/ui/IceGlowBackground'
import { useAuth } from '../hooks/useAuth'
import type { DayReportExerciseRead, DayReportRead, DayReportTrainingRead } from '../types/dayReport'
import { MUSCLE_GROUP_LABELS, MUSCLE_GROUPS, TARGET_STAT_LABELS } from '../types/exercise'
import type { MuscleGroup, TargetStat } from '../types/exercise'
import type { MuscleLoadRead } from '../types/progress'
import { DAY_SESSION_TYPE_LABELS, SESSION_TYPE_COLORS, SESSION_TYPE_ICONS } from '../types/schedule'
import { SET_FEEDBACK_LABELS } from '../types/setCompletion'
import type { SetFeedback } from '../types/setCompletion'
import { parseIsoDate, toIsoDate } from '../utils/date'

const EFFORT_LABELS = { easy: 'Легко', normal: 'Нормально', hard: 'Тяжело' } as const
const FOCUS_RESULT_LABELS = { done: 'Получилось', partial: 'Частично', missed: 'Не получилось' } as const
const GAME_RESULT_LABELS = { win: 'Победа', draw: 'Ничья', loss: 'Поражение' } as const
const PHASE_ORDER = { warmup: 0, main: 1, cooldown: 2, puck: 3 } as const

function formatLongDate(isoDate: string): string {
  const text = parseIsoDate(isoDate).toLocaleDateString('ru-RU', { weekday: 'long', day: 'numeric', month: 'long' })
  return text.charAt(0).toUpperCase() + text.slice(1)
}

function formatSet(set: { weight_kg: number | null; reps: number | null; seconds: number | null }): string {
  if (set.weight_kg !== null && set.reps !== null) return `${set.weight_kg}×${set.reps}`
  if (set.reps !== null) return `${set.reps} повт`
  if (set.seconds !== null) return `${set.seconds} сек`
  return '✓'
}

function isMuscleGroup(value: string): value is MuscleGroup {
  return (MUSCLE_GROUPS as readonly string[]).includes(value)
}

// «Как прошёл день» (2026-10-10, owner's request): the whole day in one
// place -- the gym's sets and weights, the ice report, the muscles the day
// loaded and the stats it moved.
export function DayReportPage() {
  const { date } = useParams<{ date: string }>()
  const { accessToken } = useAuth()
  const [report, setReport] = useState<DayReportRead | null>(null)
  const [error, setError] = useState<string | null>(null)
  const dateIso = date === undefined || date === 'today' ? toIsoDate(new Date()) : date

  useEffect(() => {
    if (accessToken === null) {
      return
    }
    let cancelled = false
    dayReportApi
      .getDayReport(dateIso, accessToken)
      .then((result) => {
        if (!cancelled) setReport(result)
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof ApiError && err.status === 404 ? 'На этот день нет тренировок.' : 'Не удалось загрузить отчёт.')
        }
      })
    return () => {
      cancelled = true
    }
  }, [accessToken, dateIso])

  const loads: MuscleLoadRead[] =
    report?.muscles
      .filter((muscle) => isMuscleGroup(muscle.muscle_group))
      .map((muscle) => ({
        muscle_group: muscle.muscle_group as MuscleGroup,
        intensity: muscle.intensity,
        last_updated_at: new Date().toISOString(),
      })) ?? []
  const trainings = report?.trainings.filter((training) => training.session_type !== 'rest') ?? []

  return (
    <div className="relative min-h-svh overflow-hidden">
      <IceGlowBackground />
      <div className="relative z-[1] mx-auto flex max-w-2xl flex-col gap-5 px-4 py-8">
        <BackLink />
        <div className="flex flex-col gap-0.5">
          <span className="text-xs font-semibold uppercase tracking-wide text-accent-persimmon">Как прошёл день</span>
          <h1 className="font-display text-[28px] font-semibold uppercase leading-tight">{formatLongDate(dateIso)}</h1>
        </div>
        <FormError message={error} />
        {report === null && error === null && <p className="text-sm text-text-secondary">Загрузка...</p>}

        {report !== null && (
          <>
            <div className="grid grid-cols-4 gap-2">
              <SummaryTile value={trainings.length} label={trainings.length === 1 ? 'тренировка' : 'тренировки'} />
              <SummaryTile value={report.exercises_done} label="упражнений" />
              <SummaryTile value={report.sets_total} label="подходов" />
              <SummaryTile value={Math.round(report.tonnage_kg)} label="кг поднято" />
            </div>

            {loads.length > 0 && (
              <div className={`flex flex-col gap-3 p-4 ${CARD_CLASS}`}>
                <span className="text-xs font-medium uppercase tracking-wide text-text-secondary">Что нагрузил</span>
                <MuscleLoadChart loads={loads} />
                <div className="flex flex-col gap-2">
                  {loads.slice(0, 6).map((load) => (
                    <div key={load.muscle_group} className="flex items-center gap-3 text-sm">
                      <span className="w-32 shrink-0 text-text-primary">{MUSCLE_GROUP_LABELS[load.muscle_group]}</span>
                      <span className="h-2 flex-1 overflow-hidden rounded-full bg-white/10">
                        <span
                          className="block h-full rounded-full bg-accent-persimmon"
                          style={{ width: `${Math.min(100, load.intensity * 10)}%` }}
                        />
                      </span>
                      <span className="w-9 shrink-0 text-right font-mono text-xs text-text-secondary">
                        {load.intensity.toFixed(1)}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {report.stats.length > 0 && (
              <div className={`flex flex-col gap-2 p-4 ${CARD_CLASS}`}>
                <span className="text-xs font-medium uppercase tracking-wide text-text-secondary">Прирост характеристик</span>
                {report.stats.map((stat) => {
                  const delta = stat.after - stat.before
                  return (
                    <div key={stat.stat} className="flex items-center justify-between text-sm">
                      <span>{TARGET_STAT_LABELS[stat.stat as TargetStat] ?? stat.stat}</span>
                      <span className="font-mono text-xs text-text-secondary">
                        {stat.before} → <span className="text-text-primary">{stat.after}</span>{' '}
                        <span className={delta >= 0 ? 'text-accent-ice' : 'text-accent-persimmon'}>
                          {delta >= 0 ? '+' : ''}
                          {delta.toFixed(1)}
                        </span>
                      </span>
                    </div>
                  )
                })}
              </div>
            )}

            {trainings.map((training) => (
              <TrainingCard key={training.day_plan_id} training={training} />
            ))}
          </>
        )}
      </div>
    </div>
  )
}

function SummaryTile({ value, label }: { value: number; label: string }) {
  return (
    <div className={`flex flex-col gap-0.5 px-2.5 py-2.5 ${CARD_CLASS}`}>
      <span className="font-display text-[22px] font-semibold leading-none">{value}</span>
      <span className="text-[11px] leading-tight text-text-secondary">{label}</span>
    </div>
  )
}

function TrainingCard({ training }: { training: DayReportTrainingRead }) {
  const isIceLike = training.session_type === 'on_ice' || training.session_type === 'game'
  const exercises = [...training.exercises].sort((a, b) => PHASE_ORDER[a.phase] - PHASE_ORDER[b.phase])
  const main = exercises.filter((exercise) => exercise.phase === 'main' || exercise.phase === 'puck')
  const extra = exercises.filter((exercise) => exercise.phase !== 'main' && exercise.phase !== 'puck')
  return (
    <div className={`flex flex-col gap-3 p-4 ${CARD_CLASS}`}>
      <div className="flex items-center justify-between gap-3">
        <span className="flex items-center gap-2 text-base font-semibold">
          <i className={`ti ${SESSION_TYPE_ICONS[training.session_type]} ${SESSION_TYPE_COLORS[training.session_type]}`} aria-hidden="true" />
          {training.team_event_id !== null
            ? training.session_type === 'game'
              ? 'Командная игра'
              : 'Командная тренировка'
            : DAY_SESSION_TYPE_LABELS[training.session_type]}
          {training.time_of_day !== null && (
            <span className="text-xs font-normal text-text-secondary">· {training.time_of_day === 'morning' ? 'утро' : 'вечер'}</span>
          )}
        </span>
        {training.minutes !== null && !isIceLike && (
          <span className="font-mono text-xs text-text-secondary">{training.minutes} мин</span>
        )}
      </div>

      {isIceLike ? (
        training.ice === null ? (
          <p className="text-sm text-text-secondary">Отчёт после льда ещё не отправлен.</p>
        ) : training.ice.skipped ? (
          <p className="text-sm text-text-secondary">Не был на льду.</p>
        ) : (
          <div className="flex flex-col gap-3">
            <div className="grid grid-cols-3 gap-2 text-center">
              {training.ice.game_result !== null ? (
                <IceTile value={GAME_RESULT_LABELS[training.ice.game_result]} label="итог" />
              ) : (
                <IceTile value={training.ice.duration_minutes !== null ? `${training.ice.duration_minutes}` : '—'} label="минут на льду" />
              )}
              {training.ice.game_result !== null ? (
                <IceTile value={`${training.ice.goals ?? 0}+${training.ice.assists ?? 0}`} label="голы + пасы" />
              ) : (
                <IceTile value={training.ice.effort !== null ? EFFORT_LABELS[training.ice.effort] : '—'} label="нагрузка" />
              )}
              <IceTile
                value={training.ice.focus_result !== null ? FOCUS_RESULT_LABELS[training.ice.focus_result] : '—'}
                label={training.ice.focus_title ?? 'фокус'}
              />
            </div>
            {training.ice.note !== null && training.ice.note.trim() !== '' && (
              <p className="rounded-lg bg-white/[0.04] px-3 py-2.5 text-sm leading-relaxed text-text-primary">
                «{training.ice.note}»
              </p>
            )}
            {extra.some((exercise) => exercise.done) && (
              <p className="text-xs text-text-secondary">
                Подготовка: {extra.filter((exercise) => exercise.done).length} из {extra.length}
              </p>
            )}
          </div>
        )
      ) : (
        <>
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-text-secondary">
            <span>
              Упражнений <b className="text-text-primary">{training.exercises_done}</b> из {training.exercises_total}
            </span>
            <span>
              Подходов <b className="text-text-primary">{training.sets_total}</b>
            </span>
            {training.tonnage_kg > 0 && (
              <span>
                Объём <b className="text-text-primary">{Math.round(training.tonnage_kg)} кг</b>
              </span>
            )}
          </div>
          <div className="flex flex-col divide-y divide-white/5">
            {main.map((exercise) => (
              <ExerciseLine key={exercise.name} exercise={exercise} />
            ))}
          </div>
          {extra.length > 0 && (
            <p className="text-xs text-text-secondary">
              Разминка и заминка: {extra.filter((exercise) => exercise.done || exercise.skipped).length} из {extra.length}
            </p>
          )}
        </>
      )}
    </div>
  )
}

function IceTile({ value, label }: { value: string; label: string }) {
  return (
    <div className="flex min-w-0 flex-col gap-0.5 rounded-lg bg-white/[0.04] px-2 py-2.5">
      <span className="truncate text-sm font-semibold">{value}</span>
      <span className="truncate text-[11px] text-text-secondary">{label}</span>
    </div>
  )
}

function ExerciseLine({ exercise }: { exercise: DayReportExerciseRead }) {
  return (
    <div className="flex flex-col gap-1.5 py-2.5">
      <div className="flex items-center justify-between gap-3">
        <span className={`min-w-0 text-sm ${exercise.done ? 'text-text-primary' : 'text-text-secondary'}`}>{exercise.name}</span>
        {exercise.feedback !== null && (
          <span className="shrink-0 text-[11px] text-text-secondary">{SET_FEEDBACK_LABELS[exercise.feedback as SetFeedback]}</span>
        )}
        {exercise.skipped && <span className="shrink-0 text-[11px] text-text-secondary">пропущено</span>}
        {!exercise.done && !exercise.skipped && <span className="shrink-0 text-[11px] text-text-secondary">не сделано</span>}
      </div>
      {exercise.sets.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {exercise.sets.map((set, index) => (
            <span key={index} className="rounded-full bg-white/[0.06] px-2.5 py-1 font-mono text-[11px] text-text-primary">
              {formatSet(set)}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}
