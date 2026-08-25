import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { BackLink } from '../components/ui/BackLink'
import { Button } from '../components/ui/Button'
import { Checkbox } from '../components/ui/Checkbox'
import { FormError } from '../components/ui/FormError'
import { IceGlowBackground } from '../components/ui/IceGlowBackground'
import { ExerciseDetailModal } from '../components/ExerciseDetailModal'
import * as authApi from '../api/auth'
import * as progressApi from '../api/progress'
import * as scheduleApi from '../api/schedule'
import * as sessionBlocksApi from '../api/sessionBlocks'
import * as trainingBlockApi from '../api/trainingBlock'
import * as trainingDiaryApi from '../api/trainingDiary'
import * as trainingSessionsApi from '../api/trainingSessions'
import { ApiError } from '../api/client'
import { useAuth } from '../hooks/useAuth'
import { TARGET_STAT_LABELS } from '../types/exercise'
import type { ExerciseRead, TargetStat } from '../types/exercise'
import type { TrainingStreakRead } from '../types/progress'
import { DAY_SESSION_TYPE_LABELS } from '../types/schedule'
import type { DayPlanRead, SessionBlockRead, TrainingPhase } from '../types/schedule'
import { BLOCK_PHASE_LABELS } from '../types/trainingBlock'
import type { TrainingBlockRead } from '../types/trainingBlock'
import { WEEKDAY_LABELS, parseIsoDate, toIsoDate } from '../utils/date'
import { loadOptional } from '../utils/loadOptional'

const PHASE_LABELS: Record<TrainingPhase, string> = {
  warmup: 'Разминка',
  main: 'Основная часть',
  cooldown: 'Заминка',
  puck: 'Владение шайбой',
}

// Rough estimate only -- nothing in the schema tracks actual elapsed time
// (no started_at/duration fields anywhere), so "time remaining" can't be
// measured. Duration-based exercises use their own target directly;
// set/rep exercises assume a flat per-rep tempo; anything with neither
// falls back to a flat guess rather than counting as zero.
const SECONDS_PER_REP_ESTIMATE = 4
const DEFAULT_EXERCISE_SECONDS_ESTIMATE = 60

function estimateExerciseSeconds(exercise: ExerciseRead): number {
  if (exercise.target_duration_seconds !== null) {
    return exercise.target_duration_seconds
  }
  if (exercise.target_sets !== null && exercise.rep_range_min !== null && exercise.rep_range_max !== null) {
    // Midpoint of the rep range (Phase: П.1 double progression) -- same
    // approach as the backend's app.core.session_duration.
    const avgReps = (exercise.rep_range_min + exercise.rep_range_max) / 2
    return exercise.target_sets * avgReps * SECONDS_PER_REP_ESTIMATE
  }
  return DEFAULT_EXERCISE_SECONDS_ESTIMATE
}

// A target_sets exercise counts as done once every set is logged (matches
// what SetLogger itself considers "all sets done") -- independent of
// SessionBlock.completed_at, which still separately drives block_completed
// and stays exactly as it was. An exercise with no target_sets has no other
// completion signal, so it falls back to completed_at.
function isExerciseDone(block: SessionBlockRead, setCounts: Record<string, number>): boolean {
  if (block.exercise.target_sets !== null) {
    return (setCounts[block.exercise.id] ?? 0) >= block.exercise.target_sets
  }
  return block.completed_at !== null
}

// How long the "+stat +XP" toast stays fully visible before it starts
// fading out (see CompletionToast's own fade-out duration on top of this).
const FEEDBACK_VISIBLE_MS = 2000

function formatTargetVolume(exercise: ExerciseRead): string | null {
  if (exercise.target_sets !== null && exercise.rep_range_min !== null && exercise.rep_range_max !== null) {
    return `${exercise.target_sets} × ${exercise.rep_range_min}-${exercise.rep_range_max}`
  }
  if (exercise.target_duration_seconds !== null) {
    return `${exercise.target_duration_seconds} сек`
  }
  return null
}

// Client-side optimistic mirror of stat_consumer/xp_consumer's gain formula
// (difficulty_level * 0.5 stat split evenly across the exercise's
// target_stats, difficulty_level * 10 XP -- see stat_consumer's base_gain)
// -- shown immediately on a 200 rather than waiting on a separate request,
// since the formula is already public knowledge and the real numbers land
// via the event pipeline moments later regardless.
function formatCompletionFeedback(exercise: ExerciseRead): string {
  const xpGain = exercise.difficulty_level * 10
  if (exercise.target_stats.length === 0) {
    return `+${xpGain} XP`
  }
  const statGain = (exercise.difficulty_level * 0.5) / exercise.target_stats.length
  const statsText = exercise.target_stats
    .map((stat) => `+${statGain} ${TARGET_STAT_LABELS[stat]}`)
    .join(' ')
  return `${statsText} +${xpGain} XP`
}

// Same per-block formula as formatCompletionFeedback, summed across every
// block in the session (not just the one that just got checked) -- this is
// the whole-session total shown on SessionCompleteModal.
function computeSessionTotals(sessionBlocks: SessionBlockRead[]): {
  statTotals: Partial<Record<TargetStat, number>>
  xpTotal: number
} {
  const statTotals: Partial<Record<TargetStat, number>> = {}
  let xpTotal = 0
  for (const block of sessionBlocks) {
    const stats = block.exercise.target_stats
    if (stats.length > 0) {
      const share = (block.exercise.difficulty_level * 0.5) / stats.length
      for (const stat of stats) {
        statTotals[stat] = (statTotals[stat] ?? 0) + share
      }
    }
    xpTotal += block.exercise.difficulty_level * 10
  }
  return { statTotals, xpTotal }
}

export function TrainingSessionPage() {
  const { dayPlanId } = useParams<{ dayPlanId: string }>()
  const { accessToken } = useAuth()

  const [day, setDay] = useState<DayPlanRead | null>(null)
  const [blocks, setBlocks] = useState<SessionBlockRead[] | null>(null)
  const [trainingSessionId, setTrainingSessionId] = useState<string | null>(null)
  const [trainingBlock, setTrainingBlock] = useState<TrainingBlockRead | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [pendingIds, setPendingIds] = useState<Set<string>>(new Set())
  // Keyed by exercise id -- how many SetCompletion rows are logged for that
  // exercise in this session, used by isExerciseDone for target_sets
  // exercises. Populated in bulk once blocks load, then refreshed for a
  // single exercise when its detail modal (with SetLogger) closes.
  const [setCompletionCounts, setSetCompletionCounts] = useState<Record<string, number>>({})
  const [feedbackByBlockId, setFeedbackByBlockId] = useState<Record<string, string>>({})
  const [selectedExercise, setSelectedExercise] = useState<ExerciseRead | null>(null)
  const [sessionComplete, setSessionComplete] = useState<{
    statTotals: Partial<Record<TargetStat, number>>
    xpTotal: number
  } | null>(null)
  // Captured once, at page load -- SessionCompleteModal compares this against
  // a fresh /auth/me fetch taken after the session finishes to detect a
  // level-up. Reading it here (rather than off the cached AuthContext user)
  // guarantees it reflects this page visit, not a stale login-time snapshot.
  const [levelBeforeSession, setLevelBeforeSession] = useState<number | null>(null)

  useEffect(() => {
    if (accessToken === null || dayPlanId === undefined) {
      return
    }
    let cancelled = false
    Promise.all([
      scheduleApi.getCurrentWeeklyPlan(accessToken),
      // Same "optional, 404 means not declared yet" handling as HomePage --
      // a session can be viewed without an active periodization block.
      loadOptional(trainingBlockApi.getCurrentTrainingBlock(accessToken)),
    ])
      .then(([plan, block]) => {
        if (cancelled) {
          return
        }
        const foundDay = plan.day_plans.find((candidate) => candidate.id === dayPlanId)
        if (foundDay?.training_session == null) {
          setLoadError('Тренировка не найдена.')
          return
        }
        setDay(foundDay)
        setBlocks(foundDay.training_session.blocks)
        setTrainingSessionId(foundDay.training_session.id)
        setTrainingBlock(block)
      })
      .catch(() => {
        if (!cancelled) {
          setLoadError('Не удалось загрузить тренировку. Попробуйте ещё раз.')
        }
      })
    return () => {
      cancelled = true
    }
  }, [accessToken, dayPlanId])

  async function refreshSetCount(exerciseId: string) {
    if (accessToken === null || trainingSessionId === null) {
      return
    }
    try {
      const result = await trainingSessionsApi.getExerciseSets(trainingSessionId, exerciseId, accessToken)
      setSetCompletionCounts((previous) => ({ ...previous, [exerciseId]: result.sets.length }))
    } catch {
      // Best-effort -- progress display just keeps its last known count.
    }
  }

  useEffect(() => {
    if (accessToken === null || trainingSessionId === null || blocks === null) {
      return
    }
    let cancelled = false
    const targetSetsExerciseIds = [
      ...new Set(
        blocks.filter((block) => block.exercise.target_sets !== null).map((block) => block.exercise.id),
      ),
    ]
    Promise.all(
      targetSetsExerciseIds.map((exerciseId) =>
        trainingSessionsApi
          .getExerciseSets(trainingSessionId, exerciseId, accessToken)
          .then((result) => [exerciseId, result.sets.length] as const),
      ),
    )
      .then((entries) => {
        if (!cancelled) {
          setSetCompletionCounts(Object.fromEntries(entries))
        }
      })
      .catch(() => {
        // Best-effort -- worst case target_sets exercises show as "not
        // started" in the progress/block-grouping until a manual refresh.
      })
    return () => {
      cancelled = true
    }
    // Deliberately keyed on [accessToken, trainingSessionId], not `blocks`
    // -- this should run once when the session loads, not on every local
    // blocks update from handleComplete. refreshSetCount handles updating a
    // single exercise's count after its SetLogger session closes instead.
    // oxlint-disable-next-line react-hooks/exhaustive-deps
  }, [accessToken, trainingSessionId])

  useEffect(() => {
    if (accessToken === null) {
      return
    }
    let cancelled = false
    authApi
      .getCurrentUser(accessToken)
      .then((user) => {
        if (!cancelled) {
          setLevelBeforeSession(user.level)
        }
      })
      .catch(() => {
        // Best-effort -- if this fails, SessionCompleteModal just won't be
        // able to detect a level-up (levelBeforeSession stays null), which
        // it already handles by simply not showing that block.
      })
    return () => {
      cancelled = true
    }
  }, [accessToken])

  function removeFeedback(blockId: string) {
    setFeedbackByBlockId((previous) => {
      if (!(blockId in previous)) {
        return previous
      }
      const next = { ...previous }
      delete next[blockId]
      return next
    })
  }

  async function handleComplete(block: SessionBlockRead) {
    if (accessToken === null || block.completed_at !== null || pendingIds.has(block.id) || blocks === null) {
      return
    }
    setActionError(null)
    setPendingIds((previous) => new Set(previous).add(block.id))
    try {
      const updated = await sessionBlocksApi.completeSessionBlock(block.id, accessToken)
      const mergedBlocks = blocks.map((b) => (b.id === updated.id ? updated : b))
      setBlocks(mergedBlocks)

      if (mergedBlocks.every((b) => b.completed_at !== null)) {
        // The block that was just ticked is the last one in the whole
        // session -- a small inline toast would undersell that moment, so
        // skip it in favor of SessionCompleteModal.
        setSessionComplete(computeSessionTotals(mergedBlocks))
      } else {
        setFeedbackByBlockId((previous) => ({
          ...previous,
          [block.id]: formatCompletionFeedback(block.exercise),
        }))
      }
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        // Already completed server-side (e.g. double-click race) -- just
        // sync local state, no error banner for something the user didn't
        // do wrong, and no reward toast for a completion that didn't just
        // happen.
        setBlocks(
          (previous) =>
            previous?.map((b) =>
              b.id === block.id ? { ...b, completed_at: new Date().toISOString() } : b,
            ) ?? previous,
        )
      } else {
        setActionError(err instanceof ApiError ? err.message : 'Не удалось отметить упражнение.')
      }
    } finally {
      setPendingIds((previous) => {
        const next = new Set(previous)
        next.delete(block.id)
        return next
      })
    }
  }

  // Stage 1.5 (2026-08-20 planning session, "тренажёр занят"): the modal
  // itself owns the API call/loading/error state (see ExerciseDetailModal's
  // handleReplace) -- this just syncs the two bits of page state that need
  // to know the block's exercise changed: the block list behind the modal,
  // and selectedExercise so the open modal immediately shows the new
  // exercise's own name/technique/sets instead of the outgoing one's.
  function handleExerciseReplaced(updated: SessionBlockRead) {
    setBlocks((previous) => previous?.map((b) => (b.id === updated.id ? updated : b)) ?? previous)
    setSelectedExercise(updated.exercise)
  }

  if (loadError !== null) {
    return (
      <div className="relative min-h-svh overflow-hidden">
        <IceGlowBackground />
        <div className="relative z-[1] mx-auto flex max-w-2xl flex-col gap-6 px-4 py-10">
          <BackLink />
          <FormError message={loadError} />
        </div>
      </div>
    )
  }

  if (blocks === null) {
    return (
      <div className="relative min-h-svh overflow-hidden">
        <IceGlowBackground />
        <div className="relative z-[1] mx-auto flex max-w-2xl flex-col gap-6 px-4 py-10">
          <BackLink />
          <p className="text-sm text-text-secondary">Загрузка...</p>
        </div>
      </div>
    )
  }

  const warmup = blocks.filter((block) => block.phase === 'warmup')
  const main = blocks.filter((block) => block.phase === 'main')
  const cooldown = blocks.filter((block) => block.phase === 'cooldown')
  const puck = blocks.filter((block) => block.phase === 'puck')
  // Fixed workout-flow order regardless of the raw `order` column's exact
  // numbering -- warm up, then main, then cool down, then the optional
  // puck-module tail-on -- used to find the single "current" exercise
  // across the whole session.
  const orderedBlocks = [...warmup, ...main, ...cooldown, ...puck]

  const doneCount = blocks.filter((block) => isExerciseDone(block, setCompletionCounts)).length
  const totalCount = blocks.length
  const progressPercent = totalCount > 0 ? Math.round((doneCount / totalCount) * 100) : 0
  const remainingSeconds = orderedBlocks
    .filter((block) => !isExerciseDone(block, setCompletionCounts))
    .reduce((sum, block) => sum + estimateExerciseSeconds(block.exercise), 0)
  const remainingMinutes = Math.max(1, Math.round(remainingSeconds / 60))

  const currentExerciseId =
    orderedBlocks.find((block) => !isExerciseDone(block, setCompletionCounts))?.id ?? null

  // The SessionBlock behind the exercise currently open in
  // ExerciseDetailModal -- selectedExercise only stores the ExerciseRead
  // (see onOpenDetail below), so this is looked up by exercise id, same
  // simplification setCompletionCounts/isExerciseDone already make
  // elsewhere in this file (an exercise appearing twice in one session
  // would be ambiguous here too, pre-existing either way). Needed to build
  // onLastSetCompleted's closure over the right block for handleComplete.
  const selectedBlock =
    selectedExercise !== null
      ? (blocks.find((block) => block.exercise.id === selectedExercise.id) ?? null)
      : null

  const weekdayLabel = day !== null ? WEEKDAY_LABELS[(parseIsoDate(day.date).getDay() + 6) % 7] : null
  const eyebrow = [weekdayLabel, trainingBlock !== null ? BLOCK_PHASE_LABELS[trainingBlock.phase] : null]
    .filter(Boolean)
    .join(' · ')

  function handleCloseExerciseDetail() {
    // SetLogger tracks its own set counts internally -- this just tells the
    // page-level progress bar/block grouping to catch up after the fact,
    // without reaching into SetLogger's state at all.
    if (selectedExercise !== null && selectedExercise.target_sets !== null) {
      refreshSetCount(selectedExercise.id)
    }
    setSelectedExercise(null)
  }

  return (
    <div className="relative min-h-svh overflow-hidden">
      <IceGlowBackground />
      <div className="relative z-[1] mx-auto flex max-w-2xl flex-col gap-6 px-4 py-10">
      <div className="flex flex-col gap-2">
        <BackLink />
        <div className="flex flex-col gap-1">
          {eyebrow !== '' && <p className="text-xs uppercase tracking-wide text-text-secondary">{eyebrow}</p>}
          <h1 className="text-xl font-semibold">
            {day !== null ? DAY_SESSION_TYPE_LABELS[day.session_type] : 'Тренировка дня'}
          </h1>
        </div>
      </div>

      <div className={`flex flex-col gap-4 p-4 ${CARD_CLASS}`}>
        <div className="flex items-end justify-between">
          <div>
            <p className="mb-1 text-[11px] uppercase tracking-wide text-text-secondary">Прогресс тренировки</p>
            <p className="font-mono text-[28px] font-bold leading-none text-text-primary">
              {progressPercent}
              <span className="text-base text-text-secondary">%</span>
            </p>
          </div>
          <div className="text-right">
            {doneCount < totalCount && <p className="mb-1 text-[11px] text-text-secondary">осталось</p>}
            <p className="font-mono text-sm font-semibold text-text-primary">
              {doneCount < totalCount ? `~${remainingMinutes} мин` : 'Готово'}
            </p>
          </div>
        </div>
        <div className="relative h-[11px] rounded-full bg-white/10">
          <div
            className="absolute inset-y-0 left-0 overflow-hidden rounded-full bg-accent-persimmon transition-[width]"
            style={{ width: `${progressPercent}%` }}
          >
            <div className="animate-shimmer absolute inset-y-0 w-[40%] bg-gradient-to-r from-transparent via-white/35 to-transparent" />
          </div>
          <div
            className="absolute top-1/2 flex h-[18px] w-[18px] -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full border-2 border-accent-persimmon bg-dark-bg"
            style={{ left: `${progressPercent}%` }}
          >
            <svg width="9" height="9" viewBox="0 0 24 24" aria-hidden="true">
              <ellipse cx="12" cy="12" rx="10" ry="6" fill="#D7EFFF" />
            </svg>
          </div>
        </div>
      </div>

      <FormError message={actionError} />

      {warmup.length > 0 && (
        <PhaseBlock
          title={PHASE_LABELS.warmup}
          blocks={warmup}
          isActive={warmup.some((block) => block.id === currentExerciseId)}
          currentExerciseId={currentExerciseId}
          setCompletionCounts={setCompletionCounts}
          pendingIds={pendingIds}
          onComplete={handleComplete}
          feedbackByBlockId={feedbackByBlockId}
          onFeedbackDone={removeFeedback}
          onOpenDetail={setSelectedExercise}
        />
      )}

      {main.length > 0 && (
        <PhaseBlock
          title={PHASE_LABELS.main}
          blocks={main}
          isActive={main.some((block) => block.id === currentExerciseId)}
          currentExerciseId={currentExerciseId}
          setCompletionCounts={setCompletionCounts}
          pendingIds={pendingIds}
          onComplete={handleComplete}
          feedbackByBlockId={feedbackByBlockId}
          onFeedbackDone={removeFeedback}
          onOpenDetail={setSelectedExercise}
          showTargetStat
        />
      )}

      {cooldown.length > 0 && (
        <PhaseBlock
          title={PHASE_LABELS.cooldown}
          blocks={cooldown}
          isActive={cooldown.some((block) => block.id === currentExerciseId)}
          currentExerciseId={currentExerciseId}
          setCompletionCounts={setCompletionCounts}
          pendingIds={pendingIds}
          onComplete={handleComplete}
          feedbackByBlockId={feedbackByBlockId}
          onFeedbackDone={removeFeedback}
          onOpenDetail={setSelectedExercise}
        />
      )}

      {puck.length > 0 && (
        <PhaseBlock
          title={PHASE_LABELS.puck}
          blocks={puck}
          isActive={puck.some((block) => block.id === currentExerciseId)}
          currentExerciseId={currentExerciseId}
          setCompletionCounts={setCompletionCounts}
          pendingIds={pendingIds}
          onComplete={handleComplete}
          feedbackByBlockId={feedbackByBlockId}
          onFeedbackDone={removeFeedback}
          onOpenDetail={setSelectedExercise}
          variant="bonus"
        />
      )}

      {day !== null
        && (day.session_type === 'on_ice' || day.session_type === 'game')
        && trainingSessionId !== null
        && accessToken !== null && (
          <TrainingDiaryCard trainingSessionId={trainingSessionId} accessToken={accessToken} />
        )}

      {selectedExercise !== null && trainingSessionId !== null && accessToken !== null && (
        <ExerciseDetailModal
          exercise={selectedExercise}
          trainingSessionId={trainingSessionId}
          accessToken={accessToken}
          onClose={handleCloseExerciseDetail}
          // Only when the block is actually known and not already ticked --
          // handleComplete itself also no-ops on an already-completed block,
          // this just avoids constructing a callback that would immediately
          // no-op every time it's called.
          onLastSetCompleted={
            selectedBlock !== null && selectedBlock.completed_at === null
              ? () => handleComplete(selectedBlock)
              : undefined
          }
          blockId={
            selectedBlock !== null && selectedBlock.completed_at === null ? selectedBlock.id : undefined
          }
          onReplaced={
            selectedBlock !== null && selectedBlock.completed_at === null
              ? handleExerciseReplaced
              : undefined
          }
        />
      )}

      {sessionComplete !== null && accessToken !== null && (
        <SessionCompleteModal
          statTotals={sessionComplete.statTotals}
          xpTotal={sessionComplete.xpTotal}
          levelBeforeSession={levelBeforeSession}
          accessToken={accessToken}
        />
      )}
      </div>
    </div>
  )
}

// Card surface shared by the three phase blocks below -- dark-card fill with
// a thin icy top border, matching the convention already established on
// Home/Profile.
const CARD_CLASS = 'rounded-md border-t border-[rgba(215,239,255,0.35)] bg-dark-card'

// The optional "Владение шайбой" block is content the player unlocked (owns
// a stick in inventory) rather than a required phase like the other three --
// a dashed border + "БОНУС" tag marks that distinction instead of it looking
// like just a fourth mandatory block.
const BONUS_CARD_CLASS = 'rounded-md border border-dashed border-white/20 bg-dark-card/60'

// ON_ICE/GAME only (gated by the caller) -- the app has no structured
// content for either (see ScheduleService._build_on_ice_day_session /
// _build_game_day_session), so free text is the only way the player
// records what actually happened, in their own words. Always editable,
// not just once at session-completion -- a real athlete's notebook gets
// revisited, not filled in exactly once.
function TrainingDiaryCard({
  trainingSessionId,
  accessToken,
}: {
  trainingSessionId: string
  accessToken: string
}) {
  const [isLoaded, setIsLoaded] = useState(false)
  const [note, setNote] = useState('')
  const [isSaving, setIsSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [justSaved, setJustSaved] = useState(false)

  useEffect(() => {
    let cancelled = false
    setIsLoaded(false)
    trainingDiaryApi
      .getDiaryEntry(trainingSessionId, accessToken)
      .then((entry) => {
        if (cancelled) {
          return
        }
        setNote(entry?.note ?? '')
        setIsLoaded(true)
      })
      .catch(() => {
        // Best-effort -- worst case the card just starts empty instead of
        // pre-filled with whatever was saved before.
        if (!cancelled) {
          setIsLoaded(true)
        }
      })
    return () => {
      cancelled = true
    }
  }, [trainingSessionId, accessToken])

  async function handleSave() {
    setSaveError(null)
    setJustSaved(false)
    setIsSaving(true)
    try {
      await trainingDiaryApi.saveDiaryEntry(
        trainingSessionId,
        { note: note.trim() === '' ? null : note },
        accessToken,
      )
      setJustSaved(true)
    } catch (err) {
      setSaveError(err instanceof ApiError ? err.message : 'Не удалось сохранить запись.')
    } finally {
      setIsSaving(false)
    }
  }

  if (!isLoaded) {
    return null
  }

  return (
    <div className={CARD_CLASS}>
      <div className="flex flex-col gap-3 p-4">
        <span className="text-sm font-medium text-text-primary">Дневник</span>
        <textarea
          value={note}
          onChange={(event) => {
            setJustSaved(false)
            setNote(event.target.value)
          }}
          placeholder="Что получилось, что нет..."
          rows={3}
          maxLength={2000}
          className="resize-none rounded border border-white/10 bg-dark-bg px-3 py-2 text-sm text-text-primary placeholder:text-text-secondary/60 focus:border-accent-ice focus:outline-none"
        />
        <FormError message={saveError} />
        <div className="flex items-center justify-end gap-3">
          {justSaved && <span className="text-xs text-text-secondary">Сохранено</span>}
          <Button variant="neutral" onClick={handleSave} isLoading={isSaving} className="self-end">
            Сохранить
          </Button>
        </div>
      </div>
    </div>
  )
}

function PhaseBlock({
  title,
  blocks,
  isActive,
  currentExerciseId,
  setCompletionCounts,
  pendingIds,
  onComplete,
  feedbackByBlockId,
  onFeedbackDone,
  onOpenDetail,
  showTargetStat = false,
  variant = 'default',
}: {
  title: string
  blocks: SessionBlockRead[]
  isActive: boolean
  currentExerciseId: string | null
  setCompletionCounts: Record<string, number>
  pendingIds: Set<string>
  onComplete: (block: SessionBlockRead) => void
  feedbackByBlockId: Record<string, string>
  onFeedbackDone: (blockId: string) => void
  onOpenDetail: (exercise: ExerciseRead) => void
  showTargetStat?: boolean
  variant?: 'default' | 'bonus'
}) {
  // Starts collapsed regardless of done/not-started state -- only the
  // active block forces itself open (see `expanded` below).
  const [manualExpanded, setManualExpanded] = useState(false)
  const expanded = isActive || manualExpanded

  const doneCount = blocks.filter((block) => isExerciseDone(block, setCompletionCounts)).length
  const total = blocks.length
  const fullyDone = total > 0 && doneCount === total

  return (
    <div className={variant === 'bonus' ? BONUS_CARD_CLASS : CARD_CLASS}>
      <button
        type="button"
        onClick={() => {
          if (!isActive) {
            setManualExpanded((value) => !value)
          }
        }}
        disabled={isActive}
        className={`flex w-full items-center justify-between gap-3 p-4 text-left ${
          isActive ? 'cursor-default' : ''
        }`}
      >
        <span className="flex items-center gap-2 text-sm font-medium text-text-primary">
          {title}
          {variant === 'bonus' && (
            <span className="rounded-full border border-white/15 px-1.5 py-0.5 font-mono text-[9px] font-bold tracking-wide text-text-secondary">
              БОНУС
            </span>
          )}
        </span>
        <div className="flex items-center gap-2">
          <span className="font-mono text-xs text-text-secondary">
            {doneCount}/{total}
          </span>
          {!isActive && (
            <i
              className={`ti ti-chevron-down text-text-secondary transition-transform duration-200 ${
                expanded ? 'rotate-180' : ''
              }`}
              aria-hidden="true"
            />
          )}
        </div>
      </button>

      {!expanded && fullyDone && (
        <p className="px-4 pb-4 text-xs text-text-secondary opacity-55">
          {blocks.map((block) => block.exercise.name).join(', ')}
        </p>
      )}

      {expanded && (
        <div className="flex flex-col gap-3 px-4 pb-4">
          {blocks.map((block) => (
            <ExerciseRow
              key={block.id}
              block={block}
              isCurrent={block.id === currentExerciseId}
              isDone={isExerciseDone(block, setCompletionCounts)}
              pending={pendingIds.has(block.id)}
              onComplete={() => onComplete(block)}
              feedback={feedbackByBlockId[block.id]}
              onFeedbackDone={() => onFeedbackDone(block.id)}
              onOpenDetail={() => onOpenDetail(block.exercise)}
              showTargetStat={showTargetStat}
            />
          ))}
        </div>
      )}
    </div>
  )
}

function ExerciseRow({
  block,
  isCurrent,
  isDone,
  pending,
  onComplete,
  feedback,
  onFeedbackDone,
  onOpenDetail,
  showTargetStat = false,
}: {
  block: SessionBlockRead
  isCurrent: boolean
  isDone: boolean
  pending: boolean
  onComplete: () => void
  feedback?: string
  onFeedbackDone: () => void
  onOpenDetail: () => void
  showTargetStat?: boolean
}) {
  const isCompleted = block.completed_at !== null
  const targetVolume = formatTargetVolume(block.exercise)

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onOpenDetail}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault()
          onOpenDetail()
        }
      }}
      className={`-mx-2 flex cursor-pointer items-center justify-between gap-3 rounded px-2 py-1.5 transition-colors hover:bg-white/5 ${
        isCurrent ? 'animate-pulse-glow border-2 border-accent-persimmon' : 'border-2 border-transparent'
      } ${isDone && !isCurrent ? 'opacity-55' : ''}`}
    >
      <div className="flex items-center gap-3">
        {/* stopPropagation keeps ticking the checkbox from also opening the detail modal */}
        <span onClick={(event) => event.stopPropagation()}>
          <Checkbox checked={isCompleted} disabled={isCompleted || pending} onClick={onComplete} />
        </span>
        <div className="flex flex-col">
          <div className="flex items-center gap-2">
            {isCurrent && (
              <span className="rounded-full bg-accent-persimmon/15 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-accent-persimmon">
                Сейчас
              </span>
            )}
            {isDone && !isCompleted && (
              <i className="ti ti-check text-xs text-accent-ice" aria-hidden="true" />
            )}
          </div>
          <span className={`text-sm ${isCompleted ? 'text-text-secondary line-through' : 'text-text-primary'}`}>
            {block.exercise.name}
          </span>
          {targetVolume !== null && (
            <span className="text-xs text-text-secondary">{targetVolume}</span>
          )}
          {feedback !== undefined && (
            <CompletionToast message={feedback} onDone={onFeedbackDone} />
          )}
        </div>
      </div>
      {showTargetStat && block.exercise.target_stats.length > 0 && (
        <span className="shrink-0 text-xs text-text-secondary">
          {block.exercise.target_stats.map((stat) => TARGET_STAT_LABELS[stat]).join(', ')}
        </span>
      )}
    </div>
  )
}


// The outbox relay that carries block_completed events to the streak/xp
// consumers polls every 1.5s (see app/events/outbox_relay.py), so a fetch
// made right after the last block's completion can easily race ahead of the
// server actually having applied it. Poll a few times with growing
// confidence instead of trusting a single fetch -- stops early once the
// streak shows today's activity, which only happens after its event has
// actually been consumed.
const SERVER_STATE_POLL_DELAYS_MS = [1600, 1200, 1200]

function SessionCompleteModal({
  statTotals,
  xpTotal,
  levelBeforeSession,
  accessToken,
}: {
  statTotals: Partial<Record<TargetStat, number>>
  xpTotal: number
  levelBeforeSession: number | null
  accessToken: string
}) {
  const navigate = useNavigate()

  const [streak, setStreak] = useState<TrainingStreakRead | null>(null)
  const [freshLevel, setFreshLevel] = useState<number | null>(null)
  const [isLoadingServerState, setIsLoadingServerState] = useState(true)
  const [serverStateError, setServerStateError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    const todayIso = toIsoDate(new Date())

    async function pollServerState() {
      for (const delayMs of SERVER_STATE_POLL_DELAYS_MS) {
        await new Promise((resolve) => setTimeout(resolve, delayMs))
        if (cancelled) {
          return
        }
        try {
          const [streakResult, userResult] = await Promise.all([
            progressApi.getMyStreak(accessToken),
            authApi.getCurrentUser(accessToken),
          ])
          if (cancelled) {
            return
          }
          setStreak(streakResult)
          setFreshLevel(userResult.level)
          setServerStateError(null)
          if (streakResult.last_activity_date === todayIso) {
            break
          }
        } catch (err) {
          if (!cancelled) {
            setServerStateError(
              err instanceof ApiError ? err.message : 'Не удалось получить актуальные данные.',
            )
          }
        }
      }
      if (!cancelled) {
        setIsLoadingServerState(false)
      }
    }

    pollServerState()
    return () => {
      cancelled = true
    }
  }, [accessToken])

  const leveledUp =
    !isLoadingServerState &&
    freshLevel !== null &&
    levelBeforeSession !== null &&
    freshLevel > levelBeforeSession

  return (
    <div className="fixed inset-0 z-50 flex flex-col items-center overflow-y-auto bg-dark-bg px-4 py-10">
      <div className="flex w-full max-w-sm flex-col items-center gap-6">
        <div className="flex flex-col items-center gap-2 text-center">
          <i className="ti ti-check text-5xl text-accent-ice" aria-hidden="true" />
          <h1 className="text-2xl font-semibold text-text-primary">Тренировка завершена</h1>
        </div>

        <div className="flex w-full flex-col gap-2 rounded-md border border-white/5 bg-dark-card p-5">
          <p className="text-xs font-medium uppercase tracking-wide text-text-secondary">
            Прирост характеристик
          </p>
          {Object.entries(statTotals).map(([stat, value]) => (
            <div key={stat} className="flex items-center justify-between text-sm">
              <span className="text-text-primary">{TARGET_STAT_LABELS[stat as TargetStat]}</span>
              <span className="font-mono text-accent-ice">+{value}</span>
            </div>
          ))}
          <div className="mt-2 flex items-center justify-between border-t border-white/5 pt-2 text-sm">
            <span className="text-text-secondary">XP за тренировку</span>
            <span className="font-mono text-text-primary">+{xpTotal}</span>
          </div>
        </div>

        <div className="flex w-full flex-col gap-2 rounded-md border border-white/5 bg-dark-card p-5">
          <p className="text-xs font-medium uppercase tracking-wide text-text-secondary">
            Серия тренировок
          </p>
          {isLoadingServerState && <p className="text-sm text-text-secondary">Загрузка...</p>}
          <FormError message={serverStateError} />
          {!isLoadingServerState && streak !== null && (
            <div className="flex items-center gap-2">
              <i className="ti ti-flame text-accent-persimmon" aria-hidden="true" />
              <span className="font-mono text-xl text-text-primary">{streak.current_streak}</span>
              <span className="text-sm text-text-secondary">дней подряд</span>
            </div>
          )}
        </div>

        {leveledUp && (
          <div className="flex w-full flex-col items-center gap-1 rounded-md border border-accent-persimmon/40 bg-accent-persimmon/10 p-5 text-center">
            <p className="text-sm font-medium text-accent-persimmon">Новый уровень!</p>
            <p className="font-mono text-3xl font-bold text-accent-persimmon">{freshLevel}</p>
          </div>
        )}

        <Button onClick={() => navigate('/', { replace: true })} className="w-full">
          На главную
        </Button>
      </div>
    </div>
  )
}

function CompletionToast({ message, onDone }: { message: string; onDone: () => void }) {
  const [visible, setVisible] = useState(false)
  const onDoneRef = useRef(onDone)
  onDoneRef.current = onDone

  useEffect(() => {
    const frame = requestAnimationFrame(() => setVisible(true))
    const hideTimer = setTimeout(() => setVisible(false), FEEDBACK_VISIBLE_MS)
    // Fires after the fade-out transition (duration-300) has had time to
    // finish, so the element only ever gets removed once fully transparent.
    const removeTimer = setTimeout(() => onDoneRef.current(), FEEDBACK_VISIBLE_MS + 300)
    return () => {
      cancelAnimationFrame(frame)
      clearTimeout(hideTimer)
      clearTimeout(removeTimer)
    }
  }, [])

  return (
    <span
      className={`mt-0.5 inline-flex w-fit items-center gap-1 rounded bg-accent-ice/10 px-1.5 py-0.5 text-[11px] font-semibold text-accent-ice transition-opacity duration-300 ${
        visible ? 'opacity-100' : 'opacity-0'
      }`}
    >
      <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
        <path d="M13 2 L4 14h6l-1 8 9-12h-6l1-8z" />
      </svg>
      {message}
    </span>
  )
}
