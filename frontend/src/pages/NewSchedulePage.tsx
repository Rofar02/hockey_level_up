import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { BackLink } from '../components/ui/BackLink'
import { Button } from '../components/ui/Button'
import { CARD_BORDER } from '../components/ui/cardStyle'
import { Coachmark } from '../components/ui/Coachmark'
import { FormError } from '../components/ui/FormError'
import { IceGlowBackground } from '../components/ui/IceGlowBackground'
import { Modal } from '../components/ui/Modal'
import { ExerciseDetailModal } from '../components/ExerciseDetailModal'
import { ExerciseTechnique } from '../components/ExerciseTechnique'
import * as scheduleApi from '../api/schedule'
import * as sessionBlocksApi from '../api/sessionBlocks'
import { ApiError } from '../api/client'
import { useAuth } from '../hooks/useAuth'
import type { ExerciseRead } from '../types/exercise'
import {
  DAY_SESSION_TYPE_LABELS,
  SESSION_TYPE_COLORS,
  SESSION_TYPE_ICONS,
  TRAINING_PHASES,
} from '../types/schedule'
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

const SESSION_TYPE_OPTIONS: DaySessionType[] = ['on_ice', 'off_ice', 'rest', 'game']

// Explicit per-type classes, matching the existing single-color convention
// (border-accent-ice bg-accent-ice/10 text-accent-ice) rather than a
// `border-current`/`bg-current/10` shortcut -- Tailwind's opacity modifier
// isn't guaranteed to resolve against the `current` keyword the same way it
// does for a named color, so this stays explicit like every other selected-
// state style in this codebase.
const SESSION_TYPE_ACTIVE_CLASSES: Record<DaySessionType, string> = {
  on_ice: 'border-accent-ice bg-accent-ice/10 text-accent-ice',
  off_ice: 'border-white/40 bg-white/10 text-[#F5F7FA]',
  rest: 'border-white/25 bg-white/5 text-[#8A94A6]',
  game: 'border-accent-persimmon bg-accent-persimmon/10 text-accent-persimmon',
}

// Same labels TrainingSessionPage uses for these phases -- duplicated
// locally rather than imported since PHASE_LABELS there is page-local, not
// exported (matches how CARD_BORDER itself is duplicated per-page in this
// codebase rather than centralized).
const PHASE_LABELS: Record<TrainingPhase, string> = {
  warmup: 'Разминка',
  main: 'Основная часть',
  cooldown: 'Заминка',
  puck: 'Владение шайбой',
}

// Same tabler-icons family as SESSION_TYPE_ICONS (types/schedule.ts) --
// one glyph per phase card header, so a day with 15+ exercises reads as
// four distinct groups at a glance instead of the flat, unstyled list this
// replaced (found 2026-08-27: "не нравится как отображается список
// упражнений" -- every phase was just an uppercase label directly above
// plain text rows, nothing separating one exercise from the next).
const PHASE_ICONS: Record<TrainingPhase, string> = {
  warmup: 'ti-flame',
  main: 'ti-barbell',
  cooldown: 'ti-wind',
  puck: 'ti-disc',
}

function formatPhaseCounts(trainingSession: TrainingSessionRead): string {
  const counts: Record<TrainingPhase, number> = { warmup: 0, main: 0, cooldown: 0, puck: 0 }
  for (const block of trainingSession.blocks) {
    counts[block.phase] += 1
  }
  // Zero-count phases are dropped, not shown as "Шайба: 0" -- meaningful
  // for a session type that structurally has no MAIN block (on_ice/game),
  // but pure noise for puck (almost nobody owns a stick) if shown on every
  // single off-ice day regardless.
  return TRAINING_PHASES.filter((phase) => counts[phase] > 0)
    .map((phase) => `${PHASE_LABELS[phase]}: ${counts[phase]}`)
    .join(' · ')
}

// duration_seconds is the honest estimate derived from the
// actually-assembled blocks (app.core.session_duration on the backend), not
// a promise, so this reads "~NN мин" rather than an exact figure.
function formatEstimatedDuration(durationSeconds: number): string {
  return `~${Math.round(durationSeconds / 60)} мин`
}

// Same volume formatting as TrainingSessionPage's own (unexported, page-
// local there too) formatTargetVolume -- duplicated rather than imported
// for the same reason PHASE_LABELS is.
function formatTargetVolume(exercise: ExerciseRead): string | null {
  if (exercise.target_sets !== null && exercise.rep_range_min !== null && exercise.rep_range_max !== null) {
    return `${exercise.target_sets} × ${exercise.rep_range_min}-${exercise.rep_range_max}`
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
  // Skipped (warmup/cooldown-only, media-player redesign 2026-08-28) counts
  // as resolved here too -- otherwise a day with a fully-skipped warmup but
  // everything else done never reaches 'done'.
  const completedCount = blocks.filter(
    (block) => block.completed_at !== null || block.skipped_at !== null,
  ).length
  if (completedCount === 0) {
    return 'not-started'
  }
  return completedCount === blocks.length ? 'done' : 'in-progress'
}

const COMPLETION_BADGE_LABELS: Partial<Record<DayCompletionStatus, string>> = {
  'in-progress': 'уже начат',
  done: 'пройдено',
}

// 'уже начат' reads as an invitation to go finish it -- true for today (or,
// in principle, in-progress can't really happen for a future day), but
// wrong for a day that's already past: nothing left to "already start",
// it just never got finished (2026-08-29: "пишет в прошлом дне типа
// тренировка начата, не правильно").
function completionBadgeLabel(row: DayRow, todayIso: string): string | undefined {
  if (row.completionStatus === 'in-progress' && row.isoDate < todayIso) {
    return 'не завершено'
  }
  return COMPLETION_BADGE_LABELS[row.completionStatus]
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
  // session_type each day had when editing started, so
  // handleSaveChanges can diff against it (rather than per-row original*
  // fields that view/plan mode would carry around for no reason) and
  // handleCancelEditing can revert to it exactly.
  const [editSnapshot, setEditSnapshot] = useState<Map<string, { sessionType: DaySessionType }> | null>(
    null,
  )
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
  // Holds the whole block (not just its exercise) plus which day it
  // belongs to -- both needed by handleBlockCompleted below to call
  // POST /session-blocks/{id}/complete and patch the right row's
  // trainingSession.blocks once the last set is logged.
  const [selectedExercise, setSelectedExercise] = useState<{
    block: SessionBlockRead
    trainingSessionId: string
    dayIsoDate: string
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
        {
          days: rows.map((row) => ({
            date: row.isoDate,
            session_type: row.sessionType,
          })),
        },
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
    setEditSnapshot(new Map(rows.map((row) => [row.isoDate, { sessionType: row.sessionType }])))
  }

  function handleCancelEditing() {
    if (editSnapshot === null) {
      return
    }
    setRows((previous) =>
      previous.map((row) => {
        const original = editSnapshot.get(row.isoDate)
        return original === undefined ? row : { ...row, sessionType: original.sessionType }
      }),
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
    const changed = rows.filter((row) => {
      if (isStarted(row)) {
        return false
      }
      const original = editSnapshot.get(row.isoDate)
      return original === undefined || original.sessionType !== row.sessionType
    })
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
      const payload = {
        days: changed.map((row) => ({
          date: row.isoDate,
          session_type: row.sessionType,
        })),
      }
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
        setEditSnapshot(new Map(refreshedRows.map((row) => [row.isoDate, { sessionType: row.sessionType }])))
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

  // Mirrors TrainingSessionPage's handleComplete -- this is the same
  // POST /session-blocks/{id}/complete call, just reached from a started
  // day viewed via the weekly schedule instead of the dedicated session
  // page. Without it, ExerciseDetailModal's SetLogger happily logs every
  // set here (it's the same real component, not a read-only view), but the
  // block itself never gets marked complete and the block_completed event
  // (stat/XP/streak gain) never fires -- logging "through the Week page"
  // silently didn't count.
  async function handleBlockCompleted(dayIsoDate: string, block: SessionBlockRead) {
    // skipped_at also guarded here -- a warmup/cooldown block skipped from
    // the live session must stay resolved when reopened from this page too,
    // never completable a second time for stat/XP gain it already opted out
    // of.
    if (accessToken === null || block.completed_at !== null || block.skipped_at !== null) {
      return
    }
    setSubmitError(null)
    try {
      const updated = await sessionBlocksApi.completeSessionBlock(block.id, accessToken)
      setRows((previous) =>
        previous.map((row) => {
          if (row.isoDate !== dayIsoDate || row.trainingSession === null) {
            return row
          }
          const blocks = row.trainingSession.blocks.map((b) => (b.id === updated.id ? updated : b))
          return {
            ...row,
            trainingSession: { ...row.trainingSession, blocks },
            completionStatus: completionStatusFromBlocks(blocks),
          }
        }),
      )
    } catch (err) {
      // Same 409-tolerant handling as TrainingSessionPage.handleComplete --
      // already completed server-side (e.g. double-open race) isn't a real
      // error, just a stale local block.completed_at.
      if (!(err instanceof ApiError && err.status === 409)) {
        setSubmitError(err instanceof ApiError ? err.message : 'Не удалось отметить упражнение.')
      }
    }
  }

  const previewIndex = previewIsoDate !== null ? rows.findIndex((row) => row.isoDate === previewIsoDate) : -1
  const previewRow = previewIndex !== -1 ? rows[previewIndex] : null
  const todayIso = toIsoDate(new Date())

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
                  isToday={row.isoDate === todayIso}
                  isPast={row.isoDate < todayIso}
                  todayIso={todayIso}
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
            <Coachmark
              id="schedule-week-day-tap"
              icon="ti-hand-click"
              text="Нажмите на день, чтобы посмотреть его упражнения: ещё не начатый день откроет превью, а начатый или пройденный — список с результатами."
            />
            {/* "Campaign path" -- a connecting line + circular weekday node
                per row, read-only view only (editing keeps EditableDayRow's
                plain rows below: its interactive type-picker grid doesn't
                map cleanly onto a path node). */}
            <div className="relative flex flex-col">
              {rows.length > 1 && (
                <div className="absolute bottom-[26px] left-[19px] top-[26px] w-0.5 bg-gradient-to-b from-accent-ice/20 via-white/10 to-white/5" />
              )}
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
                const badgeLabel = completionBadgeLabel(row, todayIso)
                const isToday = row.isoDate === todayIso

                return (
                  <div key={row.isoDate} className="relative flex gap-3 pb-3 last:pb-0">
                    <div
                      className={`z-[1] flex h-10 w-10 shrink-0 items-center justify-center rounded-full border-2 bg-dark-bg font-mono text-[10px] font-bold ${
                        isToday ? 'border-accent-persimmon text-accent-persimmon' : 'border-white/15 text-[#8A94A6]'
                      }`}
                    >
                      {WEEKDAY_LABELS[index].toUpperCase()}
                    </div>
                    <div
                      // min-w-0: without it this flex-1 item's min-width
                      // defaults to `auto`, so a long DaySummary line (e.g.
                      // "Разминка: 3 · Основная часть: 5 · Заминка: 2 ·
                      // Владение шайбой: 2 · ~45 мин") grows the item to fit
                      // its own unwrapped width instead of wrapping inside
                      // it -- the row (and the page) then overflows sideways
                      // on a phone instead of the text just wrapping.
                      className={`flex min-w-0 flex-1 flex-col gap-2 rounded-md ${CARD_BORDER} bg-dark-card p-3 ${
                        isToday ? 'ring-1 ring-inset ring-accent-persimmon/40' : ''
                      }`}
                    >
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
                        {isToday && (
                          <span className="rounded-full bg-accent-persimmon/15 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-accent-persimmon">
                            Сегодня
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-2">
                        <span
                          className={`flex items-center gap-1.5 text-sm ${SESSION_TYPE_COLORS[row.sessionType]}`}
                        >
                          <i className={`ti ${SESSION_TYPE_ICONS[row.sessionType]}`} aria-hidden="true" />
                          {DAY_SESSION_TYPE_LABELS[row.sessionType]}
                        </span>
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
                        onSelectExercise={(block) =>
                          setSelectedExercise({
                            block,
                            trainingSessionId: trainingSession.id,
                            dayIsoDate: row.isoDate,
                          })
                        }
                      />
                    )}
                    </div>
                  </div>
                )
              })}
            </div>
            <FormError message={submitError} />
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
                  isToday={row.isoDate === todayIso}
                  isPast={row.isoDate < todayIso}
                  todayIso={todayIso}
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
            exercise={selectedExercise.block.exercise}
            trainingSessionId={selectedExercise.trainingSessionId}
            accessToken={accessToken}
            onClose={() => setSelectedExercise(null)}
            onLastSetCompleted={() =>
              handleBlockCompleted(selectedExercise.dayIsoDate, selectedExercise.block)
            }
          />
        )}
      </div>
    </div>
  )
}

function EditableDayRow({
  row,
  weekdayLabel,
  isToday,
  isPast,
  todayIso,
  onSelectType,
}: {
  row: DayRow
  weekdayLabel: string
  isToday: boolean
  // A past day's type is history, not a plan -- read-only regardless of
  // whether it was ever started (2026-08-29: "странно что можно
  // редактировать предыдущие дни"), same bar isPast uses everywhere else on
  // this page.
  isPast: boolean
  todayIso: string
  onSelectType: (type: DaySessionType) => void
}) {
  return (
    <div
      className={`flex flex-col gap-2 rounded-md ${CARD_BORDER} bg-dark-card p-3 ${
        isToday ? 'ring-1 ring-inset ring-accent-persimmon/40' : ''
      }`}
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-baseline gap-2">
          <span className="text-sm font-medium text-[#F5F7FA]">{weekdayLabel}</span>
          <span className="font-mono text-sm text-[#8A94A6]">{formatShortDate(row.date)}</span>
          {isToday && (
            <span className="rounded-full bg-accent-persimmon/15 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-accent-persimmon">
              Сегодня
            </span>
          )}
        </div>
        {isStarted(row) || isPast ? (
          <div className="flex items-center gap-2">
            <span className={`flex items-center gap-1.5 text-sm ${SESSION_TYPE_COLORS[row.sessionType]}`}>
              <i className={`ti ${SESSION_TYPE_ICONS[row.sessionType]}`} aria-hidden="true" />
              {DAY_SESSION_TYPE_LABELS[row.sessionType]}
            </span>
            {completionBadgeLabel(row, todayIso) !== undefined && (
              <span className="rounded border border-white/10 px-2 py-1 text-xs text-[#8A94A6]">
                {completionBadgeLabel(row, todayIso)}
              </span>
            )}
          </div>
        ) : (
          <div className="grid w-full grid-cols-2 gap-2 sm:flex sm:w-auto">
            {SESSION_TYPE_OPTIONS.map((option) => (
              <button
                key={option}
                type="button"
                onClick={() => onSelectType(option)}
                className={`flex items-center justify-center gap-1.5 rounded border px-3 py-1.5 text-sm font-medium transition-colors ${
                  row.sessionType === option
                    ? SESSION_TYPE_ACTIVE_CLASSES[option]
                    : 'border-white/15 text-[#8A94A6] hover:border-white/30 hover:text-[#F5F7FA]'
                }`}
              >
                <i className={`ti ${SESSION_TYPE_ICONS[option]}`} aria-hidden="true" />
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
  onSelectExercise: (block: SessionBlockRead) => void
}) {
  const warmup = trainingSession.blocks.filter((block) => block.phase === 'warmup')
  const main = trainingSession.blocks.filter((block) => block.phase === 'main')
  const cooldown = trainingSession.blocks.filter((block) => block.phase === 'cooldown')
  const puck = trainingSession.blocks.filter((block) => block.phase === 'puck')

  return (
    <div className="mt-1 flex flex-col gap-3 border-t border-white/5 pt-3">
      {warmup.length > 0 && (
        <StartedDayPhaseSection phase="warmup" blocks={warmup} onSelectExercise={onSelectExercise} />
      )}
      {main.length > 0 && (
        <StartedDayPhaseSection phase="main" blocks={main} onSelectExercise={onSelectExercise} />
      )}
      {cooldown.length > 0 && (
        <StartedDayPhaseSection phase="cooldown" blocks={cooldown} onSelectExercise={onSelectExercise} />
      )}
      {puck.length > 0 && (
        <StartedDayPhaseSection phase="puck" blocks={puck} onSelectExercise={onSelectExercise} />
      )}
    </div>
  )
}

// Same bounded-card treatment as DayPreviewPhaseSection, for the same
// reason -- a started/done day's own exercise list was the same
// undifferentiated wall of text otherwise. Collapsed by default (found
// 2026-08-27: a full off-ice day is 4 phases/18 exercises inline right in
// the week list -- tapping the day to "just check something" opened a wall
// of text regardless) -- the header's own icon/label/count is enough to
// scan without opening anything, and each phase opens independently.
function StartedDayPhaseSection({
  phase,
  blocks,
  onSelectExercise,
}: {
  phase: TrainingPhase
  blocks: SessionBlockRead[]
  onSelectExercise: (block: SessionBlockRead) => void
}) {
  const [expanded, setExpanded] = useState(false)
  // Skipped counts as resolved here too (media-player redesign, 2026-08-28)
  // -- same reasoning as completionStatusFromBlocks above.
  const doneCount = blocks.filter((block) => block.completed_at !== null || block.skipped_at !== null).length

  return (
    <div className={`overflow-hidden rounded-md ${CARD_BORDER} bg-dark-bg/40`}>
      <button
        type="button"
        onClick={() => setExpanded((value) => !value)}
        className="flex w-full items-center gap-2 px-3 pb-2 pt-2.5 text-left"
      >
        <i className={`ti ${PHASE_ICONS[phase]} text-sm text-accent-ice`} aria-hidden="true" />
        <p className="text-xs font-medium uppercase tracking-wide text-[#8A94A6]">{PHASE_LABELS[phase]}</p>
        <span className="ml-auto font-mono text-[11px] text-[#8A94A6]">
          {doneCount}/{blocks.length}
        </span>
        <i
          className={`ti ti-chevron-down text-xs text-[#8A94A6] transition-transform ${expanded ? 'rotate-180' : ''}`}
          aria-hidden="true"
        />
      </button>
      {expanded && (
        <div className="flex flex-col divide-y divide-white/5">
          {blocks.map((block) => {
            const volume = formatTargetVolume(block.exercise)
            return (
              <button
                key={block.id}
                type="button"
                onClick={() => onSelectExercise(block)}
                className="flex w-full items-center gap-3 px-3 py-2.5 text-left transition-colors hover:bg-white/5"
              >
                {block.skipped_at !== null ? (
                  <i className="ti ti-player-skip-forward shrink-0 text-xs text-[#8A94A6]" aria-hidden="true" />
                ) : (
                  block.completed_at !== null && (
                    <i className="ti ti-check shrink-0 text-xs text-accent-ice" aria-hidden="true" />
                  )
                )}
                <span className="line-clamp-2 min-w-0 flex-1 text-sm text-[#F5F7FA]">{block.exercise.name}</span>
                {volume !== null && (
                  <span className="shrink-0 whitespace-nowrap rounded bg-white/5 px-1.5 py-0.5 font-mono text-[11px] text-[#8A94A6]">
                    {volume}
                  </span>
                )}
              </button>
            )
          })}
        </div>
      )}
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
  return (
    <p className="text-xs text-[#8A94A6] opacity-55">
      {formatPhaseCounts(row.trainingSession)} · {formatEstimatedDuration(row.trainingSession.duration_seconds)}
    </p>
  )
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
  const puck = trainingSession.blocks.filter((block) => block.phase === 'puck')

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
      <div className="flex flex-col gap-3">
        {warmup.length > 0 && (
          <DayPreviewPhaseSection
            phase="warmup"
            blocks={warmup}
            expandedBlockId={expandedBlockId}
            onToggle={setExpandedBlockId}
          />
        )}
        {main.length > 0 && (
          <DayPreviewPhaseSection
            phase="main"
            blocks={main}
            expandedBlockId={expandedBlockId}
            onToggle={setExpandedBlockId}
          />
        )}
        {cooldown.length > 0 && (
          <DayPreviewPhaseSection
            phase="cooldown"
            blocks={cooldown}
            expandedBlockId={expandedBlockId}
            onToggle={setExpandedBlockId}
          />
        )}
        {puck.length > 0 && (
          <DayPreviewPhaseSection
            phase="puck"
            blocks={puck}
            expandedBlockId={expandedBlockId}
            onToggle={setExpandedBlockId}
          />
        )}
      </div>
    </Modal>
  )
}

// Each phase is its own bounded card (icon + label + count in the header,
// hairline-divided rows below) rather than a bare uppercase label floating
// over plain text -- with 15+ exercises across four phases on a full
// off_ice day, nothing previously separated one row from the next or one
// phase from another, so the whole modal read as one long, undifferentiated
// wall of text. Matches this app's existing CARD_BORDER (icy top-border)
// convention instead of introducing a one-off list style just for this
// modal.
// Collapsed by default, same reasoning as StartedDayPhaseSection -- a full
// day's preview is exactly as text-heavy before it's even started.
function DayPreviewPhaseSection({
  phase,
  blocks,
  expandedBlockId,
  onToggle,
}: {
  phase: TrainingPhase
  blocks: SessionBlockRead[]
  expandedBlockId: string | null
  onToggle: (blockId: string | null) => void
}) {
  const [expanded, setExpanded] = useState(false)

  return (
    <div className={`overflow-hidden rounded-md ${CARD_BORDER} bg-dark-bg/40`}>
      <button
        type="button"
        onClick={() => setExpanded((value) => !value)}
        className="flex w-full items-center gap-2 px-3 pb-2 pt-2.5 text-left"
      >
        <i className={`ti ${PHASE_ICONS[phase]} text-sm text-accent-ice`} aria-hidden="true" />
        <p className="text-xs font-medium uppercase tracking-wide text-[#8A94A6]">{PHASE_LABELS[phase]}</p>
        <span className="ml-auto font-mono text-[11px] text-[#8A94A6]">{blocks.length}</span>
        <i
          className={`ti ti-chevron-down text-xs text-[#8A94A6] transition-transform ${expanded ? 'rotate-180' : ''}`}
          aria-hidden="true"
        />
      </button>
      {expanded && (
      <div className="flex flex-col divide-y divide-white/5">
        {blocks.map((block) => {
          const volume = formatTargetVolume(block.exercise)
          // Only exercises with real technique content (video or
          // description) become clickable -- one with neither stays plain,
          // unclickable text, same as before this change, rather than
          // opening an empty detail panel.
          const clickable = hasExerciseTechnique(block.exercise)
          const techniqueExpanded = clickable && expandedBlockId === block.id

          return (
            <div key={block.id} className="px-3">
              {clickable ? (
                <button
                  type="button"
                  onClick={() => onToggle(techniqueExpanded ? null : block.id)}
                  className="flex w-full items-center gap-3 py-2.5 text-left transition-colors hover:bg-white/5"
                >
                  {/* line-clamp-2, not truncate -- a read-only preview row
                      has no checkbox/action competing for width the way
                      TrainingSessionPage's ExerciseRow does, so a long real
                      exercise name (there are several) can afford to wrap
                      once instead of losing its second half to an ellipsis. */}
                  <span className="line-clamp-2 min-w-0 flex-1 text-sm text-[#F5F7FA]">
                    {block.exercise.name}
                  </span>
                  <div className="flex shrink-0 items-center gap-2">
                    {volume !== null && (
                      <span className="whitespace-nowrap rounded bg-white/5 px-1.5 py-0.5 font-mono text-[11px] text-[#8A94A6]">
                        {volume}
                      </span>
                    )}
                    <i
                      className={`ti ti-chevron-down text-xs text-[#8A94A6] transition-transform ${
                        techniqueExpanded ? 'rotate-180' : ''
                      }`}
                      aria-hidden="true"
                    />
                  </div>
                </button>
              ) : (
                <div className="flex items-center gap-3 py-2.5">
                  <span className="line-clamp-2 min-w-0 flex-1 text-sm text-[#F5F7FA]">
                    {block.exercise.name}
                  </span>
                  {volume !== null && (
                    <span className="shrink-0 whitespace-nowrap rounded bg-white/5 px-1.5 py-0.5 font-mono text-[11px] text-[#8A94A6]">
                      {volume}
                    </span>
                  )}
                </div>
              )}
              {techniqueExpanded && (
                <div className={`mb-2.5 rounded-md ${CARD_BORDER} bg-dark-bg/60 p-3`}>
                  <ExerciseTechnique exercise={block.exercise} />
                </div>
              )}
            </div>
          )
        })}
      </div>
      )}
    </div>
  )
}
