import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { BackLink } from '../components/ui/BackLink'
import { Button } from '../components/ui/Button'
import { FormError } from '../components/ui/FormError'
import { IceGlowBackground } from '../components/ui/IceGlowBackground'
import { Modal } from '../components/ui/Modal'
import { ExerciseDetailModal } from '../components/ExerciseDetailModal'
import { ExerciseTechnique } from '../components/ExerciseTechnique'
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
import { hasExerciseTechnique } from '../utils/exerciseTechnique'
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

// 'in-progress' (some but not all blocks completed) vs 'done' (every block
// completed) -- previously collapsed into one "locked" boolean, which is
// exactly what made "уже начат" show on a fully-finished day too.
type DayCompletionStatus = 'not-started' | 'in-progress' | 'done'

function completionStatusFromBlocks(blocks: SessionBlockRead[] | undefined): DayCompletionStatus {
  if (blocks === undefined || blocks.length === 0) {
    return 'not-started'
  }
  const completedCount = blocks.filter((block) => block.completed_at !== null).length
  if (completedCount === 0) {
    return 'not-started'
  }
  return completedCount === blocks.length ? 'done' : 'in-progress'
}

const COMPLETION_BADGE_LABELS: Partial<Record<DayCompletionStatus, string>> = {
  'in-progress': 'уже начат',
  done: 'пройдено',
}

interface DayRow {
  isoDate: string
  date: Date
  sessionType: DaySessionType
  completionStatus: DayCompletionStatus
  trainingSession: TrainingSessionRead | null
}

// "Started" (in-progress or done) is what actually gates editing controls
// and which click-behavior a row gets -- the 3-way status only matters for
// which badge text to show.
function isStarted(row: DayRow): boolean {
  return row.completionStatus !== 'not-started'
}

function rowsFromPlan(plan: WeeklyPlanRead): DayRow[] {
  return plan.day_plans.map((day) => ({
    isoDate: day.date,
    date: parseIsoDate(day.date),
    sessionType: day.session_type,
    completionStatus: completionStatusFromBlocks(day.training_session?.blocks),
    trainingSession: day.training_session,
  }))
}

function rowsForWeek(dates: Date[]): DayRow[] {
  return dates.map((date) => ({
    isoDate: toIsoDate(date),
    date,
    sessionType: 'rest',
    completionStatus: 'not-started',
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
  // null = view mode (read-only); non-null = editing, holding the
  // session_type each day had when editing started, so handleSaveChanges
  // can diff against it (rather than a per-row originalSessionType field
  // that view/plan mode would carry around for no reason) and
  // handleCancelEditing can revert to it exactly.
  const [editSnapshot, setEditSnapshot] = useState<Map<string, DaySessionType> | null>(null)
  // Set only when handleSaveChanges finds a changed, unlocked day -- which
  // in edit mode is every changed day, since edit mode only exists for an
  // already-generated week. Holds the exact rows to submit if confirmed.
  const [pendingRegeneration, setPendingRegeneration] = useState<DayRow[] | null>(null)
  // A started day expands inline (not a modal) to list its exercises --
  // accordion, one day at a time. Not-started days keep using
  // previewIsoDate/DayPreviewModal instead; the two are mutually exclusive
  // since a row is either isPreviewable or isExpandable, never both.
  const [expandedRowIsoDate, setExpandedRowIsoDate] = useState<string | null>(null)
  // The real, full ExerciseDetailModal (Подходы/Техника, actual logged
  // weights/reps via SetLogger) -- opened for an exercise inside a started
  // day's expanded list. Deliberately a single top-level modal, not nested
  // inside DayPreviewModal or an inline panel's own modal: this app has no
  // precedent anywhere for one Modal opening from inside another.
  const [selectedExercise, setSelectedExercise] = useState<{
    exercise: ExerciseRead
    trainingSessionId: string
  } | null>(null)

  useEffect(() => {
    if (accessToken === null) {
      return
    }
    let cancelled = false
    setWeekStatus('loading')
    setLoadError(null)
    setEditSnapshot(null)
    setPendingRegeneration(null)
    setExpandedRowIsoDate(null)
    setSelectedExercise(null)
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

  function handleStartEditing() {
    setSubmitError(null)
    setExpandedRowIsoDate(null)
    setEditSnapshot(new Map(rows.map((row) => [row.isoDate, row.sessionType])))
  }

  function handleCancelEditing() {
    if (editSnapshot === null) {
      return
    }
    setRows((previous) =>
      previous.map((row) => ({ ...row, sessionType: editSnapshot.get(row.isoDate) ?? row.sessionType })),
    )
    setEditSnapshot(null)
    setSubmitError(null)
  }

  function handleSaveChanges() {
    if (editSnapshot === null) {
      return
    }
    // Started rows never show a type selector in edit mode (see the
    // EditableDayRow render below), so this filter is belt-and-suspenders,
    // not the primary guard.
    const changed = rows.filter((row) => !isStarted(row) && row.sessionType !== editSnapshot.get(row.isoDate))
    if (changed.length === 0) {
      setEditSnapshot(null)
      return
    }
    // Edit mode only exists for an already-generated week (weekStatus ===
    // 'view'), so every changed row necessarily already has a
    // trainingSession -- unlike the pre-tabs version of this page, there's
    // no "just-generated, nothing to lose" case to skip the confirmation
    // for here.
    setPendingRegeneration(changed)
  }

  async function performSaveChanges(changed: DayRow[]) {
    if (accessToken === null) {
      return
    }
    setPendingRegeneration(null)
    setSubmitError(null)
    setIsSubmitting(true)
    try {
      const payload = { days: changed.map((row) => ({ date: row.isoDate, session_type: row.sessionType })) }
      // Explicit week_start_date only for next week -- current week keeps
      // using the plain /current endpoint, per the existing, already-
      // tested split on the backend.
      const result =
        selectedWeek === 'current'
          ? await scheduleApi.patchCurrentWeeklyPlan(payload, accessToken)
          : await scheduleApi.patchWeeklyPlan(toIsoDate(WEEK_START_DATES.next), payload, accessToken)

      const refreshedRows = rowsFromPlan(result.weekly_plan)
      if (result.conflicts.length > 0) {
        // Stay in edit mode so the user can see what happened and retry
        // other days -- re-baseline the snapshot to the just-fetched
        // truth so the failed day (now reverted server-side) doesn't keep
        // showing as "changed".
        setRows(refreshedRows)
        setEditSnapshot(new Map(refreshedRows.map((row) => [row.isoDate, row.sessionType])))
        setSubmitError(
          result.conflicts
            .map((conflict) => `${formatShortDate(parseIsoDate(conflict.date))}: ${conflict.detail}`)
            .join('; '),
        )
        return
      }

      setRows(refreshedRows)
      setEditSnapshot(null)
    } catch (err) {
      setSubmitError(
        err instanceof ApiError ? err.message : 'Не удалось сохранить изменения. Попробуйте ещё раз.',
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
                <EditableDayRow
                  key={row.isoDate}
                  row={row}
                  weekdayLabel={WEEKDAY_LABELS[index]}
                  onSelectType={(type) => setDayType(index, type)}
                />
              ))}
            </div>
            <FormError message={submitError} />
            <Button onClick={handleGeneratePlan} isLoading={isSubmitting} className="self-end">
              Сгенерировать план
            </Button>
          </>
        )}

        {weekStatus === 'view' && loadError === null && editSnapshot === null && (
          <>
            <div className="flex flex-col gap-3">
              {rows.map((row, index) => {
                const trainingSession = row.trainingSession
                const started = isStarted(row)
                // Not-started days with a plan open the read-only
                // DayPreviewModal (technique-only, no logging); started
                // days expand inline instead, listing exercises that open
                // the real ExerciseDetailModal -- see the state comments
                // above for why these stay mutually exclusive.
                const isPreviewable = !started && trainingSession !== null
                const isExpandable = started && trainingSession !== null
                const isExpanded = isExpandable && expandedRowIsoDate === row.isoDate
                const badgeLabel = COMPLETION_BADGE_LABELS[row.completionStatus]

                return (
                  <div key={row.isoDate} className={`flex flex-col gap-2 rounded-md ${CARD_BORDER} bg-dark-card p-3`}>
                    <div
                      role={isPreviewable || isExpandable ? 'button' : undefined}
                      tabIndex={isPreviewable || isExpandable ? 0 : undefined}
                      onClick={
                        isPreviewable
                          ? () => setPreviewIsoDate(row.isoDate)
                          : isExpandable
                            ? () => setExpandedRowIsoDate(isExpanded ? null : row.isoDate)
                            : undefined
                      }
                      onKeyDown={
                        isPreviewable || isExpandable
                          ? (event) => {
                              if (event.key === 'Enter' || event.key === ' ') {
                                event.preventDefault()
                                if (isPreviewable) {
                                  setPreviewIsoDate(row.isoDate)
                                } else {
                                  setExpandedRowIsoDate(isExpanded ? null : row.isoDate)
                                }
                              }
                            }
                          : undefined
                      }
                      className={`flex flex-wrap items-center justify-between gap-3 ${
                        isPreviewable || isExpandable ? 'cursor-pointer' : ''
                      }`}
                    >
                      <div className="flex items-baseline gap-2">
                        <span className="text-sm font-medium text-[#F5F7FA]">{WEEKDAY_LABELS[index]}</span>
                        <span className="font-mono text-sm text-[#8A94A6]">{formatShortDate(row.date)}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="text-sm text-[#8A94A6]">{DAY_SESSION_TYPE_LABELS[row.sessionType]}</span>
                        {badgeLabel !== undefined && (
                          <span className="rounded border border-white/10 px-2 py-1 text-xs text-[#8A94A6]">
                            {badgeLabel}
                          </span>
                        )}
                        {isExpandable && (
                          <i
                            className={`ti ti-chevron-down text-xs text-[#8A94A6] transition-transform ${
                              isExpanded ? 'rotate-180' : ''
                            }`}
                            aria-hidden="true"
                          />
                        )}
                      </div>
                    </div>
                    <DaySummary row={row} />
                    {isExpanded && trainingSession !== null && (
                      <StartedDayExerciseList
                        trainingSession={trainingSession}
                        onSelectExercise={(exercise) =>
                          setSelectedExercise({ exercise, trainingSessionId: trainingSession.id })
                        }
                      />
                    )}
                  </div>
                )
              })}
            </div>
            <Button variant="neutral" onClick={handleStartEditing} className="self-end">
              Изменить план
            </Button>
          </>
        )}

        {weekStatus === 'view' && loadError === null && editSnapshot !== null && (
          <>
            <div className="flex flex-col gap-3">
              {rows.map((row, index) => (
                <EditableDayRow
                  key={row.isoDate}
                  row={row}
                  weekdayLabel={WEEKDAY_LABELS[index]}
                  onSelectType={(type) => setDayType(index, type)}
                />
              ))}
            </div>
            <FormError message={submitError} />
            <div className="flex justify-end gap-3">
              <Button variant="neutral" onClick={handleCancelEditing}>
                Отмена
              </Button>
              <Button onClick={handleSaveChanges} isLoading={isSubmitting}>
                Сохранить изменения
              </Button>
            </div>
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

        {selectedExercise !== null && accessToken !== null && (
          <ExerciseDetailModal
            exercise={selectedExercise.exercise}
            trainingSessionId={selectedExercise.trainingSessionId}
            accessToken={accessToken}
            onClose={() => setSelectedExercise(null)}
          />
        )}
      </div>
    </div>
  )
}

function EditableDayRow({
  row,
  weekdayLabel,
  onSelectType,
}: {
  row: DayRow
  weekdayLabel: string
  onSelectType: (type: DaySessionType) => void
}) {
  return (
    <div className={`flex flex-col gap-2 rounded-md ${CARD_BORDER} bg-dark-card p-3`}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-baseline gap-2">
          <span className="text-sm font-medium text-[#F5F7FA]">{weekdayLabel}</span>
          <span className="font-mono text-sm text-[#8A94A6]">{formatShortDate(row.date)}</span>
        </div>
        {isStarted(row) ? (
          <div className="flex items-center gap-2">
            <span className="text-sm text-[#8A94A6]">{DAY_SESSION_TYPE_LABELS[row.sessionType]}</span>
            <span className="rounded border border-white/10 px-2 py-1 text-xs text-[#8A94A6]">
              {COMPLETION_BADGE_LABELS[row.completionStatus]}
            </span>
          </div>
        ) : (
          <div className="flex gap-2">
            {SESSION_TYPE_OPTIONS.map((option) => (
              <button
                key={option}
                type="button"
                onClick={() => onSelectType(option)}
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
    </div>
  )
}

// Inline exercise list for a started day (in-progress or done) -- not a
// modal. Each exercise opens the real ExerciseDetailModal (Подходы/
// Техника, actual logged weight/reps), which is the whole point: a started
// day has real results worth seeing, not just the plan.
function StartedDayExerciseList({
  trainingSession,
  onSelectExercise,
}: {
  trainingSession: TrainingSessionRead
  onSelectExercise: (exercise: ExerciseRead) => void
}) {
  const warmup = trainingSession.blocks.filter((block) => block.phase === 'warmup')
  const main = trainingSession.blocks.filter((block) => block.phase === 'main')
  const cooldown = trainingSession.blocks.filter((block) => block.phase === 'cooldown')

  return (
    <div className="mt-1 flex flex-col gap-3 border-t border-white/5 pt-3">
      {warmup.length > 0 && (
        <StartedDayPhaseSection title={PHASE_LABELS.warmup} blocks={warmup} onSelectExercise={onSelectExercise} />
      )}
      {main.length > 0 && (
        <StartedDayPhaseSection title={PHASE_LABELS.main} blocks={main} onSelectExercise={onSelectExercise} />
      )}
      {cooldown.length > 0 && (
        <StartedDayPhaseSection title={PHASE_LABELS.cooldown} blocks={cooldown} onSelectExercise={onSelectExercise} />
      )}
    </div>
  )
}

function StartedDayPhaseSection({
  title,
  blocks,
  onSelectExercise,
}: {
  title: string
  blocks: SessionBlockRead[]
  onSelectExercise: (exercise: ExerciseRead) => void
}) {
  return (
    <div className="flex flex-col gap-2">
      <p className="text-xs font-medium uppercase tracking-wide text-[#8A94A6]">{title}</p>
      <div className="flex flex-col gap-1.5">
        {blocks.map((block) => {
          const volume = formatTargetVolume(block.exercise)
          return (
            <button
              key={block.id}
              type="button"
              onClick={() => onSelectExercise(block.exercise)}
              className="-mx-2 flex items-center justify-between gap-3 rounded px-2 py-1 text-left transition-colors hover:bg-white/5"
            >
              <span className="flex min-w-0 items-center gap-2">
                {block.completed_at !== null && (
                  <i className="ti ti-check shrink-0 text-xs text-accent-ice" aria-hidden="true" />
                )}
                <span className="min-w-0 truncate text-sm text-[#F5F7FA]">{block.exercise.name}</span>
              </span>
              {volume !== null && (
                <span className="shrink-0 whitespace-nowrap font-mono text-xs text-[#8A94A6]">{volume}</span>
              )}
            </button>
          )
        })}
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

  // Accordion (at most one exercise's technique open at a time) rather than
  // independent expand state per row -- keeps this already-scrollable modal
  // from growing unbounded if every exercise in the day got expanded at
  // once. Lives here, not per-phase-section, so opening one exercise in
  // "Основная часть" collapses one that was open in "Разминка".
  const [expandedBlockId, setExpandedBlockId] = useState<string | null>(null)

  return (
    <Modal
      title={`${weekdayLabel}, ${formatShortDate(date)} — ${DAY_SESSION_TYPE_LABELS[sessionType]}`}
      onClose={onClose}
    >
      <div className="flex flex-col gap-4">
        {warmup.length > 0 && (
          <DayPreviewPhaseSection
            title={PHASE_LABELS.warmup}
            blocks={warmup}
            expandedBlockId={expandedBlockId}
            onToggle={setExpandedBlockId}
          />
        )}
        {main.length > 0 && (
          <DayPreviewPhaseSection
            title={PHASE_LABELS.main}
            blocks={main}
            expandedBlockId={expandedBlockId}
            onToggle={setExpandedBlockId}
          />
        )}
        {cooldown.length > 0 && (
          <DayPreviewPhaseSection
            title={PHASE_LABELS.cooldown}
            blocks={cooldown}
            expandedBlockId={expandedBlockId}
            onToggle={setExpandedBlockId}
          />
        )}
      </div>
    </Modal>
  )
}

function DayPreviewPhaseSection({
  title,
  blocks,
  expandedBlockId,
  onToggle,
}: {
  title: string
  blocks: SessionBlockRead[]
  expandedBlockId: string | null
  onToggle: (blockId: string | null) => void
}) {
  return (
    <div className="flex flex-col gap-2">
      <p className="text-xs font-medium uppercase tracking-wide text-[#8A94A6]">{title}</p>
      <div className="flex flex-col gap-1.5">
        {blocks.map((block) => {
          const volume = formatTargetVolume(block.exercise)
          // Only exercises with real technique content (video or
          // description) become clickable -- one with neither stays plain,
          // unclickable text, same as before this change, rather than
          // opening an empty detail panel.
          const clickable = hasExerciseTechnique(block.exercise)
          const expanded = clickable && expandedBlockId === block.id

          return (
            <div key={block.id}>
              {clickable ? (
                <button
                  type="button"
                  onClick={() => onToggle(expanded ? null : block.id)}
                  className="-mx-2 flex w-full items-center justify-between gap-3 rounded px-2 py-1 text-left transition-colors hover:bg-white/5"
                >
                  <span className="min-w-0 truncate text-sm text-[#F5F7FA]">{block.exercise.name}</span>
                  <div className="flex shrink-0 items-center gap-2">
                    {volume !== null && (
                      <span className="whitespace-nowrap font-mono text-xs text-[#8A94A6]">{volume}</span>
                    )}
                    <i
                      className={`ti ti-chevron-down text-xs text-[#8A94A6] transition-transform ${
                        expanded ? 'rotate-180' : ''
                      }`}
                      aria-hidden="true"
                    />
                  </div>
                </button>
              ) : (
                <div className="flex items-center justify-between gap-3 text-sm">
                  <span className="min-w-0 truncate text-[#F5F7FA]">{block.exercise.name}</span>
                  {volume !== null && (
                    <span className="shrink-0 whitespace-nowrap font-mono text-xs text-[#8A94A6]">{volume}</span>
                  )}
                </div>
              )}
              {expanded && (
                <div className={`mt-2 rounded-md ${CARD_BORDER} bg-dark-bg/40 p-3`}>
                  <ExerciseTechnique exercise={block.exercise} />
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
