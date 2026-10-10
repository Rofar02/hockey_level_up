import { useEffect, useState } from 'react'
import { HelpButton } from '../components/HelpButton'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { BackLink } from '../components/ui/BackLink'
import { Button } from '../components/ui/Button'
import { CARD_BORDER } from '../components/ui/cardStyle'
import { FormError } from '../components/ui/FormError'
import { IceGlowBackground } from '../components/ui/IceGlowBackground'
import { Modal } from '../components/ui/Modal'
import { ExerciseDetailModal } from '../components/ExerciseDetailModal'
import { TeamDayPlanModal, TeamDayWeekLine } from '../components/teamEvents/TeamDayWeekParts'
import { clearTeamEventCache } from '../hooks/useTeamEvent'
import { ExerciseTechnique } from '../components/ExerciseTechnique'
import * as scheduleApi from '../api/schedule'
import { ApiError } from '../api/client'
import { useAuth } from '../hooks/useAuth'
import { useCoachmarkStep } from '../hooks/useCoachmarkStep'
import type { ExerciseRead } from '../types/exercise'
import {
  DAY_SESSION_TYPE_LABELS,
  SESSION_TYPE_COLORS,
  SESSION_TYPE_ICONS,
} from '../types/schedule'
import type {
  DayPlanRead,
  DaySessionType,
  ExtraGymTime,
  SessionBlockRead,
  TrainingPhase,
  TrainingSessionRead,
  WeeklyPlanRead,
} from '../types/schedule'
import { WEEKDAY_LABELS, addDays, formatShortDate, getMondayOfCurrentWeek, parseIsoDate, toIsoDate } from '../utils/date'
import { hasExerciseTechnique } from '../utils/exerciseTechnique'
import { loadOptional } from '../utils/loadOptional'
import { WeekSkeleton } from '../components/ui/Skeleton'

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
  // Set while a team event the user said "going" to has taken the day over.
  teamEventId: string | null
  // What the day was before that team event (null otherwise).
  replacedSessionType: DaySessionType | null
  // Double day (step 6): a separate gym training on this ice/game day.
  extraGym: ExtraGymTime | null
  extraDay: DayPlanRead | null
}

const EXTRA_CAPABLE: DaySessionType[] = ['on_ice', 'game']

function extraGymFor(row: DayRow): ExtraGymTime | null {
  return EXTRA_CAPABLE.includes(row.sessionType) ? row.extraGym : null
}

// "Started" (in-progress or done) is what actually gates editing controls
// and which click-behavior a row gets -- the 3-way status only matters for
// which badge text to show.
function isStarted(row: DayRow): boolean {
  return row.completionStatus !== 'not-started'
}

function rowsFromPlan(plan: WeeklyPlanRead): DayRow[] {
  const extras = new Map(plan.day_plans.filter((day) => day.is_extra === true).map((day) => [day.date, day]))
  return plan.day_plans.filter((day) => day.is_extra !== true).map((day) => ({
    isoDate: day.date,
    date: parseIsoDate(day.date),
    sessionType: day.session_type,
    completionStatus: completionStatusFromBlocks(day.training_session?.blocks),
    trainingSession: day.training_session,
    teamEventId: day.team_event_id,
    replacedSessionType: day.replaced_session_type ?? null,
    extraGym: extras.get(day.date)?.time_of_day ?? null,
    extraDay: extras.get(day.date) ?? null,
  }))
}

function rowsForWeek(dates: Date[]): DayRow[] {
  return dates.map((date) => ({
    isoDate: toIsoDate(date),
    date,
    sessionType: 'rest',
    completionStatus: 'not-started',
    trainingSession: null,
    teamEventId: null,
    replacedSessionType: null,
    extraGym: null,
    extraDay: null,
  }))
}

export function NewSchedulePage() {
  const { accessToken } = useAuth()
  const navigate = useNavigate()

  // ?week=next -- the "plan next week" reminder on Сегодня lands straight on it.
  const [searchParams] = useSearchParams()
  const [selectedWeek, setSelectedWeek] = useState<WeekSlot>(searchParams.get('week') === 'next' ? 'next' : 'current')
  const [weekStatus, setWeekStatus] = useState<WeekStatus>('loading')
  const [rows, setRows] = useState<DayRow[]>([])
  // Double days (step 6) are behind a server switch; off -> no "+ зал".
  const [doubleDays, setDoubleDays] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  // Read-only day-plan preview modal -- stores the isoDate (not an index)
  // so it stays correct even if `rows` gets replaced (e.g. after
  // generating a plan), matching how ProfilePage tracks selectedSkillId by
  // id rather than by array position.
  const [previewIsoDate, setPreviewIsoDate] = useState<string | null>(null)
  // A team training day opens the coach's plan instead of the plain day
  // preview (which stays reachable from there as the app's warmup).
  const [teamPlanIsoDate, setTeamPlanIsoDate] = useState<string | null>(null)
  // Fresh team events on every visit (the coach may have published or
  // changed the plan since) -- in a state initializer so it runs before
  // the rows' own fetches, not after them like an effect would.
  useState(clearTeamEventCache)
  // null = view mode (read-only); non-null = editing, holding the
  // session_type each day had when editing started, so
  // handleSaveChanges can diff against it (rather than per-row original*
  // fields that view/plan mode would carry around for no reason) and
  // handleCancelEditing can revert to it exactly.
  const [editSnapshot, setEditSnapshot] = useState<Map<string, { sessionType: DaySessionType; extraGym: ExtraGymTime | null }> | null>(
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

  const dayListCoachmarkRef = useCoachmarkStep(
    'schedule-week-day-tap',
    'Нажмите на день, чтобы посмотреть его упражнения: ещё не начатый день откроет превью, а начатый или пройденный — список с результатами.',
    'ti-hand-click',
  )

  useEffect(() => {
    if (accessToken === null) {
      return
    }
    let cancelled = false
    scheduleApi
      .getScheduleFeatures(accessToken)
      .then((features) => {
        if (!cancelled) {
          setDoubleDays(features.double_days)
        }
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [accessToken])

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

  function setDayExtra(index: number, extra: ExtraGymTime | null) {
    setRows((previous) => previous.map((row, i) => (i === index ? { ...row, extraGym: extra } : row)))
  }

  // «Сухая + ещё и лёд»: the same double day the other way round -- the day
  // becomes ice at that time and the gym moves to the other half of it.
  function addIceToGymDay(index: number, iceTime: ExtraGymTime) {
    const gymTime: ExtraGymTime = iceTime === 'morning' ? 'evening' : 'morning'
    setRows((previous) =>
      previous.map((row, i) => (i === index ? { ...row, sessionType: 'on_ice', extraGym: gymTime } : row)),
    )
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
            extra_gym: extraGymFor(row),
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
    setEditSnapshot(new Map(rows.map((row) => [row.isoDate, { sessionType: row.sessionType, extraGym: row.extraGym }])))
  }

  function handleCancelEditing() {
    if (editSnapshot === null) {
      return
    }
    setRows((previous) =>
      previous.map((row) => {
        const original = editSnapshot.get(row.isoDate)
        return original === undefined ? row : { ...row, sessionType: original.sessionType, extraGym: original.extraGym }
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
      return (
        original === undefined ||
        original.sessionType !== row.sessionType ||
        extraGymFor({ ...row, extraGym: original.extraGym }) !== extraGymFor(row)
      )
    })
    if (changed.length === 0) {
      setEditSnapshot(null)
      return
    }
    // Only "Ещё и зал" changed: the days themselves are kept as they are
    // (the backend leaves a day of the same type alone), nothing to warn
    // about.
    const retyped = changed.filter((row) => editSnapshot.get(row.isoDate)?.sessionType !== row.sessionType)
    if (retyped.length === 0) {
      void performSaveChanges(changed)
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
          extra_gym: extraGymFor(row),
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
        setEditSnapshot(
          new Map(refreshedRows.map((row) => [row.isoDate, { sessionType: row.sessionType, extraGym: row.extraGym }])),
        )
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
  const teamPlanIndex = teamPlanIsoDate !== null ? rows.findIndex((row) => row.isoDate === teamPlanIsoDate) : -1
  const teamPlanRow = teamPlanIndex !== -1 ? rows[teamPlanIndex] : null
  const todayIso = toIsoDate(new Date())

  return (
    <div className="relative min-h-svh overflow-hidden">
      <IceGlowBackground />
      <div className="relative z-[1] mx-auto flex max-w-2xl flex-col gap-6 px-4 py-10">
        <div className="flex flex-col gap-3">
          <div className="flex items-center justify-between gap-3">
            <BackLink />
            <HelpButton topic="week" />
          </div>
          <div className="flex items-end justify-between gap-3">
            <div className="flex min-w-0 flex-col gap-0.5">
              <span className="font-mono text-[11px] uppercase tracking-[1.2px] text-text-secondary">
                {formatWeekRange(WEEK_START_DATES[selectedWeek])}
              </span>
              <span className="flex items-center gap-2">
                <h1 className="font-display text-[30px] font-semibold uppercase leading-none tracking-wide">Неделя</h1>
                {editSnapshot !== null && (
                  <span className="rounded-full bg-accent-persimmon/15 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-accent-persimmon">
                    правка
                  </span>
                )}
              </span>
            </div>
            <div className="flex shrink-0 rounded-lg border border-white/[0.08] bg-dark-card p-[3px]">
              <WeekTabButton active={selectedWeek === 'current'} onClick={() => setSelectedWeek('current')}>
                Эта
              </WeekTabButton>
              <WeekTabButton active={selectedWeek === 'next'} onClick={() => setSelectedWeek('next')}>
                Следующая
              </WeekTabButton>
            </div>
          </div>
        </div>

        <FormError message={loadError} />

        {weekStatus === 'loading' && <WeekSkeleton />}

        {weekStatus === 'plan' && loadError === null && (
          <>
            <p className="text-sm text-[#8A94A6]">
              Планируете неделю с {formatShortDate(WEEK_START_DATES[selectedWeek])}
            </p>
            <div className="flex flex-col gap-2">
              {rows.map((row, index) => (
                <EditableDayRow
                  key={row.isoDate}
                  row={row}
                  weekdayLabel={WEEKDAY_LABELS[index]}
                  isToday={row.isoDate === todayIso}
                  isPast={row.isoDate < todayIso}
                  todayIso={todayIso}
                  onSelectType={(type) => setDayType(index, type)}
                  doubleDays={doubleDays}
                  onSelectExtra={(extra) => setDayExtra(index, extra)}
                  onAddIce={(time) => addIceToGymDay(index, time)}
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
            <DisplacedGymWarning rows={rows} onAdjust={handleStartEditing} />
            <WeekSummary rows={rows} />
            <div className="flex flex-col gap-2">
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
                const isTeamTraining = row.teamEventId !== null && row.sessionType === 'on_ice'
                const isExpanded = isExpandable && expandedRowIsoDate === row.isoDate
                const openRow = () => {
                  if (isTeamTraining && !started) {
                    setTeamPlanIsoDate(row.isoDate)
                  } else if (isPreviewable) {
                    setPreviewIsoDate(row.isoDate)
                  } else if (isExpandable) {
                    setExpandedRowIsoDate(isExpanded ? null : row.isoDate)
                  }
                }
                const canOpen = isPreviewable || isExpandable
                const badgeLabel = completionBadgeLabel(row, todayIso)
                const isToday = row.isoDate === todayIso
                // Coachmark ref on today's row specifically, not the whole
                // list -- spotlighting all 7 rows at once read as "the
                // entire screen is selected" (found live-testing,
                // 2026-08-30).
                const rowRef = isToday ? dayListCoachmarkRef : undefined

                // A plain rest day is a slim line, not a card (2026-10-10
                // redesign): the week reads as its trainings.
                if (row.sessionType === 'rest' && row.extraDay === null && row.teamEventId === null) {
                  return (
                    <div
                      key={row.isoDate}
                      ref={rowRef}
                      className={`flex items-center gap-3 rounded-[10px] border border-dashed px-3 py-2.5 text-sm text-text-secondary ${
                        isToday ? 'border-accent-persimmon/50' : 'border-white/10'
                      }`}
                    >
                      <span className="w-12 font-mono text-[11px] uppercase">
                        {WEEKDAY_LABELS[index]} {row.date.getDate()}
                      </span>
                      <span className="flex items-center gap-1.5">
                        <i className={`ti ${SESSION_TYPE_ICONS.rest}`} aria-hidden="true" />
                        Отдых
                      </span>
                      {isToday && (
                        <span className="ml-auto text-[10px] font-bold uppercase tracking-wide text-accent-persimmon">
                          Сегодня
                        </span>
                      )}
                    </div>
                  )
                }

                const mainTitle =
                  row.teamEventId !== null
                    ? row.sessionType === 'game'
                      ? 'Командная игра'
                      : 'Командная тренировка'
                    : DAY_SESSION_TYPE_LABELS[row.sessionType]
                const mainIcon = row.teamEventId !== null ? 'ti-users-group' : SESSION_TYPE_ICONS[row.sessionType]
                const extra = row.extraDay
                const extraStatus = extra !== null ? completionStatusFromBlocks(extra.training_session?.blocks) : null
                const mainSlot = (
                  <DaySlot
                    label={extra !== null ? (extra.time_of_day === 'morning' ? 'вечер' : 'утро') : null}
                    icon={mainIcon}
                    colorClass={SESSION_TYPE_COLORS[row.sessionType]}
                    title={mainTitle}
                    detail={extra === null && row.teamEventId === null && trainingSession !== null ? formatDayShort(trainingSession) : null}
                    status={badgeLabel ?? null}
                    onOpen={canOpen ? openRow : undefined}
                    chevron={isExpandable ? (isExpanded ? 'up' : 'down') : isPreviewable && extra === null ? 'right' : null}
                  />
                )
                const extraSlot =
                  extra !== null ? (
                    <DaySlot
                      label={extra.time_of_day === 'morning' ? 'утро' : 'вечер'}
                      icon={SESSION_TYPE_ICONS.off_ice}
                      colorClass={SESSION_TYPE_COLORS.off_ice}
                      title={DAY_SESSION_TYPE_LABELS.off_ice}
                      detail={null}
                      status={
                        extraStatus === 'done'
                          ? '✓ пройдено'
                          : extraStatus === 'in-progress'
                            ? 'начато'
                            : `${extra.training_session?.blocks.length ?? 0} упр.`
                      }
                      onOpen={() => navigate(`/training/${extra.id}`)}
                      chevron={null}
                    />
                  ) : null

                return (
                  <div
                    key={row.isoDate}
                    ref={rowRef}
                    className={`flex gap-3 rounded-[10px] border bg-dark-card p-3 ${
                      isToday
                        ? 'border-accent-persimmon/55 shadow-[0_0_0_3px_rgba(255,92,52,0.10)]'
                        : 'border-white/[0.07]'
                    }`}
                  >
                    <div className="flex w-10 shrink-0 flex-col items-center gap-0.5 pt-0.5">
                      <span
                        className={`text-[11px] uppercase ${isToday ? 'font-semibold text-accent-persimmon' : 'text-text-secondary'}`}
                      >
                        {WEEKDAY_LABELS[index]}
                      </span>
                      <span className="font-display text-xl font-semibold leading-none">{row.date.getDate()}</span>
                      {isToday && (
                        <span className="mt-1 text-[9px] font-bold uppercase tracking-wide text-accent-persimmon">
                          сегодня
                        </span>
                      )}
                    </div>
                    <div className="flex min-w-0 flex-1 flex-col gap-2">
                      {extraSlot !== null ? (
                        <div className="flex flex-col divide-y divide-white/[0.07]">
                          {extra?.time_of_day === 'morning' ? (
                            <>
                              {extraSlot}
                              {mainSlot}
                            </>
                          ) : (
                            <>
                              {mainSlot}
                              {extraSlot}
                            </>
                          )}
                        </div>
                      ) : (
                        mainSlot
                      )}
                      {row.teamEventId !== null && row.replacedSessionType === 'off_ice' && !started && (
                        <span className="w-fit rounded-full bg-accent-persimmon/15 px-2 py-0.5 text-[10px] font-medium text-accent-persimmon">
                          Было: зал
                        </span>
                      )}
                      {row.teamEventId !== null && (
                        <div className="flex flex-col gap-2">
                          <TeamDayWeekLine eventId={row.teamEventId} />
                          {isTeamTraining && (
                            <button
                              type="button"
                              onClick={() => setTeamPlanIsoDate(row.isoDate)}
                              className="flex min-h-11 items-center justify-center gap-1.5 rounded-xl border border-accent-ice/30 bg-accent-ice/10 text-sm font-medium text-accent-ice transition-colors hover:bg-accent-ice/15"
                            >
                              <i className="ti ti-clipboard-list" aria-hidden="true" />
                              План тренировки
                            </button>
                          )}
                        </div>
                      )}
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
            <Button variant="neutral" onClick={handleStartEditing} className="w-full">
              <span className="flex items-center justify-center gap-2">
                <i className="ti ti-pencil" aria-hidden="true" />
                Изменить неделю
              </span>
            </Button>
          </>
        )}

        {weekStatus === 'view' && loadError === null && editSnapshot !== null && (
          <>
            <div className="flex flex-col gap-2">
              {rows.map((row, index) => (
                <EditableDayRow
                  key={row.isoDate}
                  row={row}
                  weekdayLabel={WEEKDAY_LABELS[index]}
                  isToday={row.isoDate === todayIso}
                  isPast={row.isoDate < todayIso}
                  todayIso={todayIso}
                  onSelectType={(type) => setDayType(index, type)}
                  doubleDays={doubleDays}
                  onSelectExtra={(extra) => setDayExtra(index, extra)}
                  onAddIce={(time) => addIceToGymDay(index, time)}
                />
              ))}
            </div>
            <FormError message={submitError} />
            <div className="grid grid-cols-[1fr_2fr] gap-2.5">
              <Button variant="neutral" onClick={handleCancelEditing}>
                Отмена
              </Button>
              <Button onClick={handleSaveChanges} isLoading={isSubmitting}>
                Сохранить
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
                {pendingRegeneration
                  .filter((row) => editSnapshot?.get(row.isoDate)?.sessionType !== row.sessionType)
                  .map((row) => (
                  <li key={row.isoDate}>
                    {formatShortDate(row.date)} — {DAY_SESSION_TYPE_LABELS[row.sessionType]}
                    {editSnapshot?.get(row.isoDate)?.sessionType === 'off_ice' && extraGymFor(row) !== null && (
                      <span className="text-[#8A94A6]"> (зал останется прежним)</span>
                    )}
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

        {teamPlanRow !== null && teamPlanRow.teamEventId !== null && (
          <TeamDayPlanModal
            title={`${WEEKDAY_LABELS[teamPlanIndex]}, ${formatShortDate(teamPlanRow.date)} — командная тренировка`}
            eventId={teamPlanRow.teamEventId}
            onClose={() => setTeamPlanIsoDate(null)}
            onOpenWarmup={
              teamPlanRow.trainingSession !== null && !isStarted(teamPlanRow)
                ? () => {
                    setTeamPlanIsoDate(null)
                    setPreviewIsoDate(teamPlanRow.isoDate)
                  }
                : null
            }
          />
        )}

        {selectedExercise !== null && accessToken !== null && (
          <ExerciseDetailModal
            exercise={selectedExercise.block.exercise}
            trainingSessionId={selectedExercise.trainingSessionId}
            accessToken={accessToken}
            onClose={() => setSelectedExercise(null)}
            readOnly
          />
        )}
      </div>
    </div>
  )
}

// The edit row's type order and selected looks (2026-10-10 redesign): one
// segmented control per day.
const EDIT_TYPE_ORDER: DaySessionType[] = ['on_ice', 'off_ice', 'game', 'rest']
const EDIT_TYPE_ACTIVE_CLASSES: Record<DaySessionType, string> = {
  on_ice: 'bg-accent-ice/25 font-semibold text-accent-ice ring-1 ring-inset ring-accent-ice/40',
  off_ice: 'bg-white/10 font-semibold text-text-primary',
  game: 'bg-accent-persimmon/15 font-semibold text-accent-persimmon',
  rest: 'bg-white/[0.06] font-semibold text-text-primary',
}

// "+ зал" on an ice/game day, "+ лёд" on a gym day: none / morning / evening.
function SecondTrainingPicker({
  label,
  value,
  activeClass,
  onSelect,
  noneLabel = 'Нет',
}: {
  label: string
  value: ExtraGymTime | null
  activeClass: string
  onSelect: (time: ExtraGymTime | null) => void
  noneLabel?: string
}) {
  return (
    <div className="flex items-center gap-1.5 pl-[50px]">
      <span className="flex-1 text-xs text-text-secondary">{label}</span>
      {([null, 'morning', 'evening'] as const).map((option) => (
        <button
          key={option ?? 'none'}
          type="button"
          onClick={() => onSelect(option)}
          aria-pressed={value === option}
          className={`rounded-full border px-2.5 py-1 text-xs transition-colors ${
            value === option
              ? `${activeClass} font-semibold`
              : 'border-white/10 font-medium text-text-secondary hover:border-white/30 hover:text-text-primary'
          }`}
        >
          {option === null ? noneLabel : option === 'morning' ? 'Утром' : 'Вечером'}
        </button>
      ))}
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
  doubleDays,
  onSelectExtra,
  onAddIce,
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
  doubleDays: boolean
  onSelectExtra: (extra: ExtraGymTime | null) => void
  onAddIce: (iceTime: ExtraGymTime) => void
}) {
  const isDouble = extraGymFor(row) !== null
  const canAddGym = doubleDays && !isStarted(row) && !isPast && EXTRA_CAPABLE.includes(row.sessionType) && !isDouble
  const canAddIce = doubleDays && !isStarted(row) && !isPast && row.sessionType === 'off_ice'
  const isLocked = isStarted(row) || isPast

  // A past or started day is history: one quiet line (2026-10-10 redesign).
  if (isLocked) {
    return (
      <div className="flex items-center gap-3 rounded-[10px] border border-white/5 bg-dark-card/55 px-3 py-2.5 text-text-secondary">
        <span className="w-12 shrink-0 font-mono text-[11px] uppercase">
          {weekdayLabel} {row.date.getDate()}
        </span>
        <span className="flex min-w-0 flex-1 items-center gap-1.5 text-[13px]">
          <i className={`ti ${SESSION_TYPE_ICONS[row.sessionType]}`} aria-hidden="true" />
          {DAY_SESSION_TYPE_LABELS[row.sessionType]}
          {completionBadgeLabel(row, todayIso) !== undefined && <span>· {completionBadgeLabel(row, todayIso)}</span>}
        </span>
        <i className="ti ti-lock text-sm text-text-secondary/60" aria-hidden="true" />
      </div>
    )
  }

  return (
    <div
      className={`flex flex-col gap-2.5 rounded-[10px] border bg-dark-card p-3 ${
        isToday ? 'border-accent-persimmon/45' : 'border-white/[0.07]'
      }`}
    >
      <div className="flex items-center gap-2.5">
        <span className="flex w-10 shrink-0 flex-col">
          <span className={`text-[11px] uppercase ${isToday ? 'font-semibold text-accent-persimmon' : 'text-text-secondary'}`}>
            {weekdayLabel}
          </span>
          <span className="font-display text-lg font-semibold leading-none">{row.date.getDate()}</span>
        </span>
        <div className="grid flex-1 grid-cols-4 gap-1 rounded-lg bg-[#0F1626] p-[3px]">
          {EDIT_TYPE_ORDER.map((option) => (
            <button
              key={option}
              type="button"
              onClick={() => onSelectType(option)}
              aria-pressed={row.sessionType === option || (isDouble && option === 'off_ice')}
              className={`flex min-h-9 items-center justify-center gap-1 rounded-md text-xs transition-colors ${
                // A double day lights both its types -- whichever side it
                // was built from (2026-10-10: "+ лёд" on a gym day used to
                // look like the gym had turned into ice).
                row.sessionType === option || (isDouble && option === 'off_ice')
                  ? EDIT_TYPE_ACTIVE_CLASSES[option]
                  : 'font-medium text-text-secondary hover:text-text-primary'
              }`}
            >
              <i className={`ti ${SESSION_TYPE_ICONS[option]} text-sm`} aria-hidden="true" />
              <span className="hidden min-[380px]:inline">{DAY_SESSION_TYPE_LABELS[option]}</span>
            </button>
          ))}
        </div>
      </div>
      {isDouble && (
        <>
          <SecondTrainingPicker
            label="Сухая:"
            value={row.extraGym}
            activeClass="border-white/50 bg-white/10 text-text-primary"
            onSelect={onSelectExtra}
            noneLabel="Убрать"
          />
          <p className="pl-[50px] text-[11px] text-text-secondary">
            {row.extraGym === 'morning'
              ? `Утро — сухая, вечер — ${row.sessionType === 'game' ? 'игра' : 'лёд'}`
              : `Утро — ${row.sessionType === 'game' ? 'игра' : 'лёд'}, вечер — сухая`}
          </p>
        </>
      )}
      {canAddGym && (
        <SecondTrainingPicker
          label="+ сухая"
          value={row.extraGym}
          activeClass="border-white/50 bg-white/10 text-text-primary"
          onSelect={onSelectExtra}
        />
      )}
      {canAddIce && (
        <SecondTrainingPicker
          label="+ лёд"
          value={null}
          activeClass="border-accent-ice/60 bg-accent-ice/10 text-accent-ice"
          onSelect={(time) => (time !== null ? onAddIce(time) : undefined)}
        />
      )}
    </div>
  )
}

const SUMMARY_SEGMENT_COLORS: Record<DaySessionType, string> = {
  on_ice: '#7CC4F5',
  off_ice: '#F2F5F8',
  game: '#FF5C34',
  rest: 'rgba(255,255,255,0.10)',
}

// "15 упражнений · основная часть 6" -- the week list's one line per day.
function formatDayShort(trainingSession: TrainingSessionRead): string {
  const total = trainingSession.blocks.length
  const main = trainingSession.blocks.filter((block) => block.phase === 'main').length
  const head = `${total} ${plural(total, 'упражнение', 'упражнения', 'упражнений')}`
  return main > 0 ? `${head} · основная часть ${main}` : head
}

function formatWeekRange(monday: Date): string {
  const sunday = new Date(monday)
  sunday.setDate(monday.getDate() + 6)
  const month = (date: Date) => date.toLocaleDateString('ru-RU', { month: 'long', day: 'numeric' })
  return monday.getMonth() === sunday.getMonth()
    ? `${monday.getDate()} — ${month(sunday)}`
    : `${month(monday)} — ${month(sunday)}`
}

function plural(n: number, one: string, few: string, many: string): string {
  if (n % 10 === 1 && n % 100 !== 11) return one
  if (n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 12 || n % 100 > 14)) return few
  return many
}

// The week at a glance (2026-10-10 redesign): a strip of the seven days
// (a double day split in two) and how many of each.
function WeekSummary({ rows }: { rows: DayRow[] }) {
  const ice = rows.filter((row) => row.sessionType === 'on_ice').length
  const gym = rows.filter((row) => row.sessionType === 'off_ice').length + rows.filter((row) => row.extraDay !== null).length
  const games = rows.filter((row) => row.sessionType === 'game').length
  const rest = rows.filter((row) => row.sessionType === 'rest').length
  const items: { color: string; count: number; label: string }[] = [
    { color: SUMMARY_SEGMENT_COLORS.on_ice, count: ice, label: plural(ice, 'лёд', 'льда', 'льдов') },
    { color: SUMMARY_SEGMENT_COLORS.off_ice, count: gym, label: plural(gym, 'зал', 'зала', 'залов') },
    { color: SUMMARY_SEGMENT_COLORS.game, count: games, label: plural(games, 'игра', 'игры', 'игр') },
    { color: 'rgba(255,255,255,0.25)', count: rest, label: plural(rest, 'отдых', 'отдыха', 'отдыха') },
  ]
  return (
    <div className="flex flex-col gap-2.5 rounded-[10px] border border-white/[0.07] bg-dark-card p-3.5">
      <div className="grid grid-cols-7 gap-1" aria-hidden="true">
        {rows.map((row) => {
          const main = SUMMARY_SEGMENT_COLORS[row.sessionType]
          const gymColor = SUMMARY_SEGMENT_COLORS.off_ice
          const background =
            row.extraDay === null
              ? main
              : row.extraDay.time_of_day === 'morning'
                ? `linear-gradient(90deg, ${gymColor} 50%, ${main} 50%)`
                : `linear-gradient(90deg, ${main} 50%, ${gymColor} 50%)`
          return <span key={row.isoDate} className="h-1.5 rounded-full" style={{ background }} />
        })}
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-text-secondary">
        {items.filter((item) => item.count > 0).map((item) => (
          <span key={item.label} className="flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full" style={{ background: item.color }} aria-hidden="true" />
            <b className="font-semibold text-text-primary">{item.count}</b> {item.label}
          </span>
        ))}
      </div>
    </div>
  )
}

// One training of a day: its half of the day on a double day, what it is,
// a short detail line and its status. Tappable when it opens something.
function DaySlot({
  label,
  icon,
  colorClass,
  title,
  detail,
  status,
  onOpen,
  chevron,
}: {
  label: string | null
  icon: string
  colorClass: string
  title: string
  detail: string | null
  status: string | null
  onOpen?: () => void
  chevron: 'right' | 'down' | 'up' | null
}) {
  const content = (
    <>
      {label !== null && (
        <span className="w-11 shrink-0 font-mono text-[10px] uppercase text-text-secondary">{label}</span>
      )}
      <span className="flex min-w-0 flex-1 flex-col gap-0.5">
        <span className="flex items-center gap-1.5 text-[15px] font-semibold text-text-primary">
          <i className={`ti ${icon} ${colorClass}`} aria-hidden="true" />
          {title}
        </span>
        {detail !== null && <span className="text-xs text-text-secondary">{detail}</span>}
      </span>
      {status !== null && <span className="shrink-0 text-[11px] text-text-secondary">{status}</span>}
      {chevron !== null && (
        <i
          className={`ti ${chevron === 'right' ? 'ti-chevron-right' : chevron === 'up' ? 'ti-chevron-up' : 'ti-chevron-down'} shrink-0 text-text-secondary/70`}
          aria-hidden="true"
        />
      )}
    </>
  )
  const className = `flex w-full items-center gap-2.5 py-2 text-left first:pt-0 last:pb-0 ${label === null ? 'py-0' : ''}`
  return onOpen !== undefined ? (
    <button type="button" onClick={onOpen} className={`${className} cursor-pointer`}>
      {content}
    </button>
  ) : (
    <div className={className}>{content}</div>
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
      aria-pressed={active}
      className={`rounded-md px-3 py-1.5 text-xs transition-colors ${
        active ? 'bg-[#24304A] font-semibold text-text-primary' : 'font-medium text-text-secondary hover:text-text-primary'
      }`}
    >
      {children}
    </button>
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

const DISMISSED_KEY_PREFIX = 'displaced-gym-dismissed:'
// "в пятницу", "на воскресенье" -- Monday first.
const WEEKDAY_ACCUSATIVE = ['понедельник', 'вторник', 'среду', 'четверг', 'пятницу', 'субботу', 'воскресенье']

function readDismissed(dayIds: string[]): boolean {
  try {
    return dayIds.every((id) => window.localStorage.getItem(DISMISSED_KEY_PREFIX + id) !== null)
  } catch {
    return false
  }
}

// 2026-10-08: "going" to a team event turns that day into ice/a game, and a
// gym workout planned there simply drops out of the week -- nothing moves it
// elsewhere. This says so and offers the week editor, pointing at the first
// free (rest) day after it. "Оставить" hides it for those days on this
// device (a per-viewer convenience, the week itself is unchanged).
function DisplacedGymWarning({ rows, onAdjust }: { rows: DayRow[]; onAdjust: () => void }) {
  const todayIso = toIsoDate(new Date())
  const displaced = rows.filter(
    (row) =>
      row.teamEventId !== null &&
      row.replacedSessionType === 'off_ice' &&
      row.isoDate >= todayIso &&
      !isStarted(row),
  )
  const dayIds = displaced.map((row) => row.isoDate)
  const [dismissed, setDismissed] = useState(() => readDismissed(dayIds))
  if (displaced.length === 0 || dismissed) {
    return null
  }

  const first = displaced[0]
  const freeDay = rows.find((row) => row.isoDate > first.isoDate && row.sessionType === 'rest' && !isStarted(row))
  const weekday = (row: DayRow) => WEEKDAY_ACCUSATIVE[(row.date.getDay() + 6) % 7]
  const what = first.sessionType === 'game' ? 'командную игру' : 'лёд с командой'

  function dismiss() {
    try {
      dayIds.forEach((id) => window.localStorage.setItem(DISMISSED_KEY_PREFIX + id, '1'))
    } catch {
      // Private mode etc. -- hidden for this visit only.
    }
    setDismissed(true)
  }

  return (
    <div className="mb-4 rounded-2xl border border-accent-persimmon/45 bg-accent-persimmon/10 p-4">
      <div className="flex gap-3">
        <i className="ti ti-alert-triangle mt-0.5 text-xl text-accent-persimmon" aria-hidden="true" />
        <div className="flex flex-col gap-1">
          <p className="text-sm font-semibold text-text-primary">
            {displaced.length === 1 ? 'Командный лёд занял день зала' : 'Командные дни заняли дни зала'}
          </p>
          <p className="text-sm leading-relaxed text-[#B7C2D4]">
            {displaced.length === 1
              ? `В ${weekday(first)} у вас ${what}, и тренировка в зале на этой неделе пропала.`
              : `На этой неделе пропало тренировок в зале: ${displaced.length}.`}{' '}
            {freeDay !== undefined
              ? `Перенесите её на свободный день — например, на ${weekday(freeDay)}.`
              : 'Перенесите её на свободный день, чтобы не потерять.'}
          </p>
        </div>
      </div>
      <div className="mt-3 flex gap-2">
        <Button onClick={onAdjust} className="flex-1">
          Скорректировать неделю
        </Button>
        <Button variant="neutral" onClick={dismiss}>
          Оставить
        </Button>
      </div>
    </div>
  )
}
