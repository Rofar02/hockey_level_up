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
  // What's actually generated for this day as of the last load/save --
  // null for a genuinely ungenerated day (create mode, or a rest day).
  // Once sessionType diverges from originalSessionType this is stale (the
  // real content will be regenerated on save), so callers must check that
  // before trusting it -- see DaySummary below.
  trainingSession: TrainingSessionRead | null
}

function rowsFromPlan(plan: WeeklyPlanRead): DayRow[] {
  return plan.day_plans.map((day) => ({
    isoDate: day.date,
    date: parseIsoDate(day.date),
    sessionType: day.session_type,
    originalSessionType: day.session_type,
    locked: day.training_session?.blocks.some((block) => block.completed_at !== null) ?? false,
    trainingSession: day.training_session,
  }))
}

function rowsForNewWeek(): DayRow[] {
  return NEW_WEEK_DATES.map((date) => ({
    isoDate: toIsoDate(date),
    date,
    sessionType: 'rest',
    originalSessionType: 'rest',
    locked: false,
    trainingSession: null,
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
  // Set only when handleSaveChanges finds a changed row that already has a
  // generated plan -- rendering the confirm modal and holding the exact
  // rows to submit if the user confirms. null the rest of the time.
  const [pendingRegeneration, setPendingRegeneration] = useState<DayRow[] | null>(null)
  // Read-only day-plan preview modal -- stores the isoDate (not an index)
  // so it stays correct even if `rows` gets replaced (e.g. after a PATCH
  // response), matching how ProfilePage tracks selectedSkillId by id
  // rather than by array position.
  const [previewIsoDate, setPreviewIsoDate] = useState<string | null>(null)

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

  function handleSaveChanges() {
    const changed = rows.filter((row) => !row.locked && row.sessionType !== row.originalSessionType)
    if (changed.length === 0) {
      navigate('/', { replace: true })
      return
    }

    // A locked (already-started) row can never reach here -- its type
    // selector is replaced by a static badge, so the UI itself blocks
    // picking a different type for it. The real, reachable risk this
    // guards is quieter: a day that's already generated (has a
    // trainingSession) but not yet started gets silently regenerated,
    // discarding whatever exercises were picked for it, with no warning
    // today. That's what triggers the confirmation.
    const hasGeneratedContent = changed.some((row) => row.trainingSession !== null)
    if (hasGeneratedContent) {
      setPendingRegeneration(changed)
      return
    }
    performSaveChanges(changed)
  }

  async function performSaveChanges(changed: DayRow[]) {
    if (accessToken === null) {
      return
    }
    setPendingRegeneration(null)
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
      <div className="relative min-h-svh overflow-hidden">
        <IceGlowBackground />
        <div className="relative z-[1] mx-auto flex max-w-2xl flex-col gap-6 px-4 py-10">
          <BackLink />
          <p className="text-sm text-[#8A94A6]">Загрузка...</p>
        </div>
      </div>
    )
  }

  const previewIndex = previewIsoDate !== null ? rows.findIndex((row) => row.isoDate === previewIsoDate) : -1
  const previewRow = previewIndex !== -1 ? rows[previewIndex] : null

  return (
    <div className="relative min-h-svh overflow-hidden">
      <IceGlowBackground />
      <div className="relative z-[1] mx-auto flex max-w-2xl flex-col gap-6 px-4 py-10">
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
                    {row.locked ? (
                      <div className="flex items-center gap-2">
                        <span className="text-sm text-[#8A94A6]">
                          {DAY_SESSION_TYPE_LABELS[row.sessionType]}
                        </span>
                        <span className="rounded border border-white/10 px-2 py-1 text-xs text-[#8A94A6]">
                          уже начат
                        </span>
                      </div>
                    ) : (
                      <div className="flex gap-2">
                        {SESSION_TYPE_OPTIONS.map((option) => (
                          <button
                            key={option}
                            type="button"
                            // stopPropagation keeps picking a type from also
                            // opening the read-only preview modal -- same
                            // pattern as TrainingSessionPage's ExerciseRow
                            // Checkbox inside its own clickable row.
                            onClick={(event) => {
                              event.stopPropagation()
                              setDayType(index, option)
                            }}
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
                    )}
                  </div>
                  <DaySummary row={row} />
                </div>
              )
            })}
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

      {pendingRegeneration !== null && (
        <Modal title="Пересобрать план на эти дни?" onClose={() => setPendingRegeneration(null)}>
          <div className="flex flex-col gap-4">
            <p className="text-sm text-[#8A94A6]">
              Для этих дней уже подобраны упражнения. При смене типа план будет собран заново, а
              текущий набор упражнений — заменён:
            </p>
            <ul className="flex flex-col gap-1 text-sm text-[#F5F7FA]">
              {pendingRegeneration.map((row) => (
                <li key={row.isoDate}>
                  {formatShortDate(row.date)} — {DAY_SESSION_TYPE_LABELS[row.sessionType]}
                </li>
              ))}
            </ul>
            <div className="flex gap-3">
              <Button onClick={() => performSaveChanges(pendingRegeneration)} isLoading={isSubmitting}>
                Пересобрать
              </Button>
              <Button variant="neutral" onClick={() => setPendingRegeneration(null)}>
                Отмена
              </Button>
            </div>
          </div>
        </Modal>
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

function DaySummary({ row }: { row: DayRow }) {
  if (row.sessionType === 'rest') {
    return null
  }

  const typeChanged = row.sessionType !== row.originalSessionType

  // Only worth calling out as "will be replaced" if there's actually
  // existing content at risk -- in create mode (or any day that was rest
  // before) trainingSession is already null, so a type change there has
  // nothing to lose and just falls through to the plain "not generated
  // yet" message below instead of implying something's being discarded.
  if (typeChanged && row.trainingSession !== null) {
    return <p className="text-xs text-[#8A94A6]">Текущий план будет заменён после сохранения.</p>
  }

  if (row.trainingSession === null) {
    return <p className="text-xs text-[#8A94A6]">План ещё не сгенерирован.</p>
  }

  return (
    <p className="text-xs text-[#8A94A6] opacity-55">{formatPhaseCounts(row.trainingSession)}</p>
  )
}

// Read-only preview of what's actually generated for a day -- no checkbox,
// no "Начать", no SetLogger, nothing that mutates SessionBlock state. Fully
// independent of TrainingSessionPage/SetLogger; only reads data this page
// already has from GET /schedule/weekly/current.
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
