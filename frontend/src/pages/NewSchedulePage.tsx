import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { BackLink } from '../components/ui/BackLink'
import { Button } from '../components/ui/Button'
import { FormError } from '../components/ui/FormError'
import { IceGlowBackground } from '../components/ui/IceGlowBackground'
import { Modal } from '../components/ui/Modal'
import * as scheduleApi from '../api/schedule'
import { ApiError } from '../api/client'
import { useAuth } from '../hooks/useAuth'
import type { ExerciseRead } from '../types/exercise'
import { DAY_SESSION_TYPE_LABELS, TRAINING_PHASES } from '../types/schedule'
import type {
  DaySessionType,
  SessionBlockRead,
  TrainingPhase,
  TrainingSessionRead,
  WeeklyPlanRead,
} from '../types/schedule'
import { WEEKDAY_LABELS, addDays, formatShortDate, getMondayOfCurrentWeek, parseIsoDate, toIsoDate } from '../utils/date'
import { loadOptional } from '../utils/loadOptional'

const SESSION_TYPE_OPTIONS: DaySessionType[] = ['on_ice', 'off_ice', 'rest']

// Same icy top-border card convention as Home/TrainingSession/Profile.
const CARD_BORDER = 'border-t border-[rgba(215,239,255,0.35)]'

// Same labels TrainingSessionPage uses for these phases -- duplicated
// locally rather than imported since PHASE_LABELS there is page-local, not
// exported (matches how CARD_BORDER itself is duplicated per-page in this
// codebase rather than centralized).
const PHASE_LABELS: Record<TrainingPhase, string> = {
  warmup: 'Разминка',
  main: 'Основная часть',
  cooldown: 'Заминка',
}

function formatPhaseCounts(trainingSession: TrainingSessionRead): string {
  const counts: Record<TrainingPhase, number> = { warmup: 0, main: 0, cooldown: 0 }
  for (const block of trainingSession.blocks) {
    counts[block.phase] += 1
  }
  return TRAINING_PHASES.map((phase) => `${PHASE_LABELS[phase]}: ${counts[phase]}`).join(' · ')
}

// Same volume formatting as TrainingSessionPage's own (unexported, page-
// local there too) formatTargetVolume -- duplicated rather than imported
// for the same reason PHASE_LABELS is.
function formatTargetVolume(exercise: ExerciseRead): string | null {
  if (exercise.target_sets !== null && exercise.target_reps !== null) {
    return `${exercise.target_sets} × ${exercise.target_reps}`
  }
  if (exercise.target_duration_seconds !== null) {
    return `${exercise.target_duration_seconds} сек`
  }
  return null
}

type WeekSlot = 'current' | 'next'
type WeekStatus = 'loading' | 'view' | 'plan'

// Computed once at module load (same as the pre-existing behavior this
// replaces) -- doesn't track a real midnight rollover while the page stays
// open, which was already true before this change.
const THIS_MONDAY = getMondayOfCurrentWeek()
const NEXT_MONDAY = addDays(THIS_MONDAY, 7)
const WEEK_START_DATES: Record<WeekSlot, Date> = { current: THIS_MONDAY, next: NEXT_MONDAY }

function datesForWeek(slot: WeekSlot): Date[] {
  const start = WEEK_START_DATES[slot]
  return Array.from({ length: 7 }, (_, i) => addDays(start, i))
}

interface DayRow {
  isoDate: string
  date: Date
  sessionType: DaySessionType
  // Informational only in view mode (there are no editing controls to gate
  // by it anymore) -- true once at least one SessionBlock for this day is
  // already completed.
  locked: boolean
  trainingSession: TrainingSessionRead | null
}

function rowsFromPlan(plan: WeeklyPlanRead): DayRow[] {
  return plan.day_plans.map((day) => ({
    isoDate: day.date,
    date: parseIsoDate(day.date),
    sessionType: day.session_type,
    locked: day.training_session?.blocks.some((block) => block.completed_at !== null) ?? false,
    trainingSession: day.training_session,
  }))
}

function rowsForWeek(dates: Date[]): DayRow[] {
  return dates.map((date) => ({
    isoDate: toIsoDate(date),
    date,
    sessionType: 'rest',
    locked: false,
    trainingSession: null,
  }))
}

export function NewSchedulePage() {
  const { accessToken } = useAuth()
  const navigate = useNavigate()

  const [selectedWeek, setSelectedWeek] = useState<WeekSlot>('current')
  const [weekStatus, setWeekStatus] = useState<WeekStatus>('loading')
  const [rows, setRows] = useState<DayRow[]>([])
  const [loadError, setLoadError] = useState<string | null>(null)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  // Read-only day-plan preview modal -- stores the isoDate (not an index)
  // so it stays correct even if `rows` gets replaced (e.g. after
  // generating a plan), matching how ProfilePage tracks selectedSkillId by
  // id rather than by array position.
  const [previewIsoDate, setPreviewIsoDate] = useState<string | null>(null)

  useEffect(() => {
    if (accessToken === null) {
      return
    }
    let cancelled = false
    setWeekStatus('loading')
    setLoadError(null)
    const weekStartIso = toIsoDate(WEEK_START_DATES[selectedWeek])
    loadOptional(scheduleApi.getWeeklyPlan(weekStartIso, accessToken))
      .then((plan) => {
        if (cancelled) {
          return
        }
        if (plan === null) {
          setWeekStatus('plan')
          setRows(rowsForWeek(datesForWeek(selectedWeek)))
        } else {
          setWeekStatus('view')
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
  }, [accessToken, selectedWeek])

  function setDayType(index: number, type: DaySessionType) {
    setRows((previous) => previous.map((row, i) => (i === index ? { ...row, sessionType: type } : row)))
  }

  async function handleGeneratePlan() {
    if (accessToken === null) {
      return
    }
    setSubmitError(null)
    setIsSubmitting(true)
    try {
      const created = await scheduleApi.createWeeklyPlan(
        { days: rows.map((row) => ({ date: row.isoDate, session_type: row.sessionType })) },
        accessToken,
      )
      if (selectedWeek === 'current') {
        navigate('/', { replace: true })
        return
      }
      // Planning ahead: stay on this page and show what was just
      // generated instead of navigating to Home, which only ever shows
      // the current week and couldn't display next week's plan at all.
      setRows(rowsFromPlan(created))
      setWeekStatus('view')
    } catch (err) {
      setSubmitError(
        err instanceof ApiError ? err.message : 'Не удалось сохранить план недели. Попробуйте ещё раз.',
      )
    } finally {
      setIsSubmitting(false)
    }
  }

  const previewIndex = previewIsoDate !== null ? rows.findIndex((row) => row.isoDate === previewIsoDate) : -1
  const previewRow = previewIndex !== -1 ? rows[previewIndex] : null

  return (
    <div className="relative min-h-svh overflow-hidden">
      <IceGlowBackground />
      <div className="relative z-[1] mx-auto flex max-w-2xl flex-col gap-6 px-4 py-10">
        <div className="flex flex-col gap-2">
          <BackLink />
          <h1 className="text-xl font-semibold">Неделя</h1>
        </div>

        <div className={`flex overflow-hidden rounded-md ${CARD_BORDER} bg-dark-card`}>
          <WeekTabButton active={selectedWeek === 'current'} onClick={() => setSelectedWeek('current')}>
            Текущая неделя
          </WeekTabButton>
          <WeekTabButton active={selectedWeek === 'next'} onClick={() => setSelectedWeek('next')}>
            Следующая неделя
          </WeekTabButton>
        </div>

        <FormError message={loadError} />

        {weekStatus === 'loading' && <p className="text-sm text-[#8A94A6]">Загрузка...</p>}

        {weekStatus === 'plan' && loadError === null && (
          <>
            <p className="text-sm text-[#8A94A6]">
              Планируете неделю с {formatShortDate(WEEK_START_DATES[selectedWeek])}
            </p>
            <div className="flex flex-col gap-3">
              {rows.map((row, index) => (
                <div
                  key={row.isoDate}
                  className={`flex flex-col gap-2 rounded-md ${CARD_BORDER} bg-dark-card p-3`}
                >
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div className="flex items-baseline gap-2">
                      <span className="text-sm font-medium text-[#F5F7FA]">{WEEKDAY_LABELS[index]}</span>
                      <span className="font-mono text-sm text-[#8A94A6]">{formatShortDate(row.date)}</span>
                    </div>
                    <div className="flex gap-2">
                      {SESSION_TYPE_OPTIONS.map((option) => (
                        <button
                          key={option}
                          type="button"
                          onClick={() => setDayType(index, option)}
                          className={`rounded border px-3 py-1.5 text-sm font-medium transition-colors ${
                            row.sessionType === option
                              ? 'border-accent-ice bg-accent-ice/10 text-accent-ice'
                              : 'border-white/15 text-[#8A94A6] hover:border-white/30 hover:text-[#F5F7FA]'
                          }`}
                        >
                          {DAY_SESSION_TYPE_LABELS[option]}
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
              ))}
            </div>
            <FormError message={submitError} />
            <Button onClick={handleGeneratePlan} isLoading={isSubmitting} className="self-end">
              Сгенерировать план
            </Button>
          </>
        )}

        {weekStatus === 'view' && loadError === null && (
          <div className="flex flex-col gap-3">
            {rows.map((row, index) => {
              const isPreviewable = row.trainingSession !== null
              return (
                <div
                  key={row.isoDate}
                  role={isPreviewable ? 'button' : undefined}
                  tabIndex={isPreviewable ? 0 : undefined}
                  onClick={isPreviewable ? () => setPreviewIsoDate(row.isoDate) : undefined}
                  onKeyDown={
                    isPreviewable
                      ? (event) => {
                          if (event.key === 'Enter' || event.key === ' ') {
                            event.preventDefault()
                            setPreviewIsoDate(row.isoDate)
                          }
                        }
                      : undefined
                  }
                  className={`flex flex-col gap-2 rounded-md ${CARD_BORDER} bg-dark-card p-3 ${
                    isPreviewable ? 'cursor-pointer transition-colors hover:border-white/20' : ''
                  }`}
                >
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div className="flex items-baseline gap-2">
                      <span className="text-sm font-medium text-[#F5F7FA]">{WEEKDAY_LABELS[index]}</span>
                      <span className="font-mono text-sm text-[#8A94A6]">{formatShortDate(row.date)}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-sm text-[#8A94A6]">{DAY_SESSION_TYPE_LABELS[row.sessionType]}</span>
                      {row.locked && (
                        <span className="rounded border border-white/10 px-2 py-1 text-xs text-[#8A94A6]">
                          уже начат
                        </span>
                      )}
                    </div>
                  </div>
                  <DaySummary row={row} />
                </div>
              )
            })}
          </div>
        )}

        {previewRow !== null && previewRow.trainingSession !== null && (
          <DayPreviewModal
            weekdayLabel={WEEKDAY_LABELS[previewIndex]}
            date={previewRow.date}
            sessionType={previewRow.sessionType}
            trainingSession={previewRow.trainingSession}
            onClose={() => setPreviewIsoDate(null)}
          />
        )}
      </div>
    </div>
  )
}

function WeekTabButton({
  active,
  onClick,
  children,
}: {
  active: boolean
  onClick: () => void
  children: string
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex-1 border-b-2 px-4 py-2.5 text-sm font-medium transition-colors ${
        active
          ? 'border-accent-persimmon text-[#F5F7FA]'
          : 'border-transparent text-[#8A94A6] hover:text-[#F5F7FA]'
      }`}
    >
      {children}
    </button>
  )
}

// Only ever rendered in view mode, where trainingSession is guaranteed
// non-null for every non-rest day (the whole plan already exists) -- the
// null check is a defensive no-op, not a real branch.
function DaySummary({ row }: { row: DayRow }) {
  if (row.sessionType === 'rest' || row.trainingSession === null) {
    return null
  }
  return <p className="text-xs text-[#8A94A6] opacity-55">{formatPhaseCounts(row.trainingSession)}</p>
}

// Read-only preview of what's actually generated for a day -- no checkbox,
// no "Начать", no SetLogger, nothing that mutates SessionBlock state. Fully
// independent of TrainingSessionPage/SetLogger; only reads data this page
// already has from GET /schedule/weekly.
function DayPreviewModal({
  weekdayLabel,
  date,
  sessionType,
  trainingSession,
  onClose,
}: {
  weekdayLabel: string
  date: Date
  sessionType: DaySessionType
  trainingSession: TrainingSessionRead
  onClose: () => void
}) {
  const warmup = trainingSession.blocks.filter((block) => block.phase === 'warmup')
  const main = trainingSession.blocks.filter((block) => block.phase === 'main')
  const cooldown = trainingSession.blocks.filter((block) => block.phase === 'cooldown')

  return (
    <Modal
      title={`${weekdayLabel}, ${formatShortDate(date)} — ${DAY_SESSION_TYPE_LABELS[sessionType]}`}
      onClose={onClose}
    >
      <div className="flex flex-col gap-4">
        {warmup.length > 0 && <DayPreviewPhaseSection title={PHASE_LABELS.warmup} blocks={warmup} />}
        {main.length > 0 && <DayPreviewPhaseSection title={PHASE_LABELS.main} blocks={main} />}
        {cooldown.length > 0 && <DayPreviewPhaseSection title={PHASE_LABELS.cooldown} blocks={cooldown} />}
      </div>
    </Modal>
  )
}

function DayPreviewPhaseSection({ title, blocks }: { title: string; blocks: SessionBlockRead[] }) {
  return (
    <div className="flex flex-col gap-2">
      <p className="text-xs font-medium uppercase tracking-wide text-[#8A94A6]">{title}</p>
      <div className="flex flex-col gap-1.5">
        {blocks.map((block) => {
          const volume = formatTargetVolume(block.exercise)
          return (
            <div key={block.id} className="flex items-center justify-between gap-3 text-sm">
              <span className="min-w-0 truncate text-[#F5F7FA]">{block.exercise.name}</span>
              {volume !== null && (
                <span className="shrink-0 whitespace-nowrap font-mono text-xs text-[#8A94A6]">{volume}</span>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
