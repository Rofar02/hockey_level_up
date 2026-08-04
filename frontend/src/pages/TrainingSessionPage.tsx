import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { BackLink } from '../components/ui/BackLink'
import { Button } from '../components/ui/Button'
import { Checkbox } from '../components/ui/Checkbox'
import { FormError } from '../components/ui/FormError'
import { IceGlowBackground } from '../components/ui/IceGlowBackground'
import { Modal } from '../components/ui/Modal'
import * as authApi from '../api/auth'
import * as exercisesApi from '../api/exercises'
import * as progressApi from '../api/progress'
import * as scheduleApi from '../api/schedule'
import * as sessionBlocksApi from '../api/sessionBlocks'
import * as setCompletionsApi from '../api/setCompletions'
import * as trainingBlockApi from '../api/trainingBlock'
import * as trainingSessionsApi from '../api/trainingSessions'
import { ApiError } from '../api/client'
import { useAuth } from '../hooks/useAuth'
import { TARGET_STAT_LABELS } from '../types/exercise'
import type { ExerciseRead, TargetStat } from '../types/exercise'
import type { TrainingStreakRead } from '../types/progress'
import { DAY_SESSION_TYPE_LABELS } from '../types/schedule'
import type { DayPlanRead, SessionBlockRead, TrainingPhase } from '../types/schedule'
import { SET_FEEDBACK_LABELS, SET_FEEDBACK_OPTIONS } from '../types/setCompletion'
import type { SetCompletionSummary, SetFeedback } from '../types/setCompletion'
import { BLOCK_PHASE_LABELS } from '../types/trainingBlock'
import type { TrainingBlockRead } from '../types/trainingBlock'
import { WEEKDAY_LABELS, parseIsoDate, toIsoDate } from '../utils/date'
import { loadOptional } from '../utils/loadOptional'

const PHASE_LABELS: Record<TrainingPhase, string> = {
  warmup: 'Разминка',
  main: 'Основная часть',
  cooldown: 'Заминка',
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
  if (exercise.target_sets !== null && exercise.target_reps !== null) {
    return exercise.target_sets * exercise.target_reps * SECONDS_PER_REP_ESTIMATE
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
  if (exercise.target_sets !== null && exercise.target_reps !== null) {
    return `${exercise.target_sets} × ${exercise.target_reps}`
  }
  if (exercise.target_duration_seconds !== null) {
    return `${exercise.target_duration_seconds} сек`
  }
  return null
}

// Client-side optimistic mirror of stat_consumer/xp_consumer's gain formula
// (difficulty_level * 0.5 stat, difficulty_level * 10 XP) -- shown
// immediately on a 200 rather than waiting on a separate request, since the
// formula is already public knowledge and the real numbers land via the
// event pipeline moments later regardless.
function formatCompletionFeedback(exercise: ExerciseRead): string {
  const statGain = exercise.difficulty_level * 0.5
  const xpGain = exercise.difficulty_level * 10
  return `+${statGain} ${TARGET_STAT_LABELS[exercise.target_stat]} +${xpGain} XP`
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
    const stat = block.exercise.target_stat
    statTotals[stat] = (statTotals[stat] ?? 0) + block.exercise.difficulty_level * 0.5
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
  // Fixed workout-flow order regardless of the raw `order` column's exact
  // numbering -- warm up, then main, then cool down -- used to find the
  // single "current" exercise across the whole session.
  const orderedBlocks = [...warmup, ...main, ...cooldown]

  const doneCount = blocks.filter((block) => isExerciseDone(block, setCompletionCounts)).length
  const totalCount = blocks.length
  const progressPercent = totalCount > 0 ? Math.round((doneCount / totalCount) * 100) : 0
  const remainingSeconds = orderedBlocks
    .filter((block) => !isExerciseDone(block, setCompletionCounts))
    .reduce((sum, block) => sum + estimateExerciseSeconds(block.exercise), 0)
  const remainingMinutes = Math.max(1, Math.round(remainingSeconds / 60))

  const currentExerciseId =
    orderedBlocks.find((block) => !isExerciseDone(block, setCompletionCounts))?.id ?? null

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

      <div className="flex flex-col gap-2">
        <div className="flex items-center justify-between text-sm">
          <span className="text-text-secondary">{progressPercent}% тренировки</span>
          <span className="text-text-secondary">
            {doneCount < totalCount ? `~${remainingMinutes} мин осталось` : 'Готово'}
          </span>
        </div>
        <div className="h-1.5 w-full overflow-hidden rounded-full bg-white/10">
          <div
            className="h-full rounded-full bg-accent-persimmon transition-[width]"
            style={{ width: `${progressPercent}%` }}
          />
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

      {selectedExercise !== null && trainingSessionId !== null && accessToken !== null && (
        <ExerciseDetailModal
          exercise={selectedExercise}
          trainingSessionId={trainingSessionId}
          accessToken={accessToken}
          onClose={handleCloseExerciseDetail}
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
}) {
  // Starts collapsed regardless of done/not-started state -- only the
  // active block forces itself open (see `expanded` below).
  const [manualExpanded, setManualExpanded] = useState(false)
  const expanded = isActive || manualExpanded

  const doneCount = blocks.filter((block) => isExerciseDone(block, setCompletionCounts)).length
  const total = blocks.length
  const fullyDone = total > 0 && doneCount === total

  return (
    <div className={CARD_CLASS}>
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
        <span className="text-sm font-medium text-text-primary">{title}</span>
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
        isCurrent ? 'border-2 border-accent-persimmon' : 'border-2 border-transparent'
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
      {showTargetStat && (
        <span className="shrink-0 text-xs text-text-secondary">
          {TARGET_STAT_LABELS[block.exercise.target_stat]}
        </span>
      )}
    </div>
  )
}

function ExerciseDetailModal({
  exercise,
  trainingSessionId,
  accessToken,
  onClose,
}: {
  exercise: ExerciseRead
  trainingSessionId: string
  accessToken: string
  onClose: () => void
}) {
  const targetVolume = formatTargetVolume(exercise)
  // The set-by-set logger already shows/asks for reps per set (via the reps
  // field's placeholder, see SetLogger) -- repeating the same "3 × 8" as a
  // separate summary line above it is pure redundancy, so it's only shown
  // when there's no logger to carry that context instead.
  const showVolumeSummary = targetVolume !== null && exercise.target_sets === null
  const hasRealVideo =
    (exercise.video_source_type === 'youtube' || exercise.video_source_type === 'vk') &&
    exercise.video_source_id !== null

  return (
    <Modal title={exercise.name} onClose={onClose}>
      <div className="flex flex-col gap-3">
        {exercise.description !== null && (
          <p className="text-sm text-text-secondary">{exercise.description}</p>
        )}

        {showVolumeSummary && (
          <div className="flex items-center justify-between text-sm">
            <span className="text-text-secondary">Объём</span>
            <span className="font-mono text-text-primary">{targetVolume}</span>
          </div>
        )}

        {exercise.target_sets !== null && (
          <SetLogger
            exercise={exercise}
            trainingSessionId={trainingSessionId}
            accessToken={accessToken}
          />
        )}

        {/* No "video coming soon" placeholder -- an empty promise of future
            content is just clutter in an already content-heavy modal. */}
        {exercise.video_source_type === 'youtube' && exercise.video_source_id !== null && (
          <div className="aspect-video overflow-hidden rounded-md">
            <iframe
              src={`https://www.youtube.com/embed/${exercise.video_source_id}`}
              title={exercise.name}
              className="h-full w-full"
              allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
              allowFullScreen
            />
          </div>
        )}
        {exercise.video_source_type === 'vk' && exercise.video_source_id !== null && (
          <p className="text-sm text-text-secondary">Embed для VK будет добавлен отдельно</p>
        )}
        {!hasRealVideo && exercise.target_sets === null && (
          <p className="text-sm text-text-secondary">Видео скоро появится</p>
        )}
      </div>
    </Modal>
  )
}

// Compact label+input+unit field for weight/reps -- stacked one-per-line in
// the current-set row rather than side by side, so neither the label nor
// the input ever has to shrink to fit a narrow modal (see the width budget
// in SetLogger's current-set row comment below).
function CompactNumberField({
  label,
  unit,
  value,
  placeholder,
  disabled,
  onChange,
}: {
  label: string
  unit?: string
  value: string
  placeholder?: string
  disabled?: boolean
  onChange: (value: string) => void
}) {
  return (
    <div className="flex min-w-0 items-center gap-2">
      {/* Natural content width, not a fixed one -- a fixed width tight
          enough to matter (e.g. w-14) risks "Повторы" visually overflowing
          its own box on narrow screens; letting it size to its text is both
          simpler and safer. */}
      <span className="shrink-0 whitespace-nowrap text-xs text-text-secondary">{label}</span>
      <input
        type="number"
        inputMode={unit !== undefined ? 'decimal' : 'numeric'}
        className="w-16 shrink-0 rounded border border-white/10 bg-dark-bg px-2 py-1.5 font-mono text-sm text-text-primary placeholder:text-text-secondary/60 focus:border-accent-ice focus:outline-none disabled:opacity-50"
        value={value}
        placeholder={placeholder}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
      />
      {unit !== undefined && <span className="shrink-0 text-xs text-text-secondary">{unit}</span>}
    </div>
  )
}

// Per-set logging layered on top of the exercise-level Checkbox in
// ExerciseRow: SessionBlock.completed_at (and the block_completed event that
// drives stat/XP gain) are untouched by any of this, this is purely the
// additional SetCompletion granularity.
//
// On mount, GET /training-sessions/{id}/exercises/{id}/sets rehydrates
// already-logged sets (and any saved feedback) so reopening the exercise
// modal doesn't lose progress -- the "current" set is the first set_number
// with no record yet, not just count+1, in case sets were ever logged
// out of order.
function SetLogger({
  exercise,
  trainingSessionId,
  accessToken,
}: {
  exercise: ExerciseRead
  trainingSessionId: string
  accessToken: string
}) {
  const targetSets = exercise.target_sets
  const [suggestedWeightKg, setSuggestedWeightKg] = useState<number | null>(null)
  const [isLoadingSuggestion, setIsLoadingSuggestion] = useState(exercise.tracks_weight)
  const [isLoadingSets, setIsLoadingSets] = useState(true)
  const [completedSets, setCompletedSets] = useState<
    Record<number, Pick<SetCompletionSummary, 'weight_kg' | 'reps_completed'>>
  >({})
  const [weightInput, setWeightInput] = useState('')
  const [repsInput, setRepsInput] = useState('')
  const [isSaving, setIsSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [feedback, setFeedback] = useState<SetFeedback | null>(null)
  const [isSavingFeedback, setIsSavingFeedback] = useState(false)
  const [feedbackError, setFeedbackError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false

    if (exercise.tracks_weight) {
      exercisesApi
        .getSuggestedWeight(exercise.id, accessToken)
        .then((result) => {
          if (cancelled) {
            return
          }
          setSuggestedWeightKg(result.suggested_weight_kg)
          if (result.suggested_weight_kg !== null) {
            setWeightInput(String(result.suggested_weight_kg))
          }
        })
        .catch(() => {
          // Best-effort -- the weight input just starts empty if this fails,
          // the user can still type a value in manually.
        })
        .finally(() => {
          if (!cancelled) {
            setIsLoadingSuggestion(false)
          }
        })
    }

    trainingSessionsApi
      .getExerciseSets(trainingSessionId, exercise.id, accessToken)
      .then((result) => {
        if (cancelled) {
          return
        }
        const bySetNumber: Record<number, Pick<SetCompletionSummary, 'weight_kg' | 'reps_completed'>> = {}
        for (const set of result.sets) {
          bySetNumber[set.set_number] = { weight_kg: set.weight_kg, reps_completed: set.reps_completed }
        }
        setCompletedSets(bySetNumber)
        setFeedback(result.feedback)
      })
      .catch(() => {
        // Best-effort -- worst case the logger just starts from "no sets
        // logged yet" instead of showing prior progress.
      })
      .finally(() => {
        if (!cancelled) {
          setIsLoadingSets(false)
        }
      })

    return () => {
      cancelled = true
    }
  }, [exercise.id, exercise.tracks_weight, trainingSessionId, accessToken])

  if (targetSets === null) {
    return null
  }

  // First set_number (1..targetSets) without a logged record -- not just
  // Object.keys(completedSets).length + 1, in case rehydrated sets have a
  // gap.
  let currentSetNumber = targetSets + 1
  for (let setNumber = 1; setNumber <= targetSets; setNumber += 1) {
    if (completedSets[setNumber] === undefined) {
      currentSetNumber = setNumber
      break
    }
  }
  const allSetsDone = currentSetNumber > targetSets

  async function handleSaveSet() {
    const reps = repsInput.trim() === '' ? null : Number(repsInput)
    const weight = exercise.tracks_weight ? (weightInput.trim() === '' ? null : Number(weightInput)) : null

    setSaveError(null)
    setIsSaving(true)
    try {
      const result = await setCompletionsApi.saveSet(
        {
          exercise_id: exercise.id,
          training_session_id: trainingSessionId,
          set_number: currentSetNumber,
          weight_kg: weight,
          reps_completed: reps,
        },
        accessToken,
      )
      setCompletedSets((previous) => ({ ...previous, [currentSetNumber]: result }))
      setWeightInput(result.suggested_weight_kg !== null ? String(result.suggested_weight_kg) : '')
      setRepsInput('')
    } catch (err) {
      if (err instanceof ApiError && err.status === 400) {
        // The specific case the backend's >3x sanity check guards against --
        // a typo like 500 instead of 50 -- gets this friendlier copy instead
        // of the raw server message.
        setSaveError('Проверьте вес — сильно отличается от обычного.')
      } else {
        setSaveError(err instanceof ApiError ? err.message : 'Не удалось сохранить подход.')
      }
    } finally {
      setIsSaving(false)
    }
  }

  async function handleSaveFeedback(value: SetFeedback) {
    setFeedbackError(null)
    setIsSavingFeedback(true)
    try {
      await setCompletionsApi.saveFeedback(
        { exercise_id: exercise.id, training_session_id: trainingSessionId, feedback: value },
        accessToken,
      )
      setFeedback(value)
    } catch (err) {
      setFeedbackError(err instanceof ApiError ? err.message : 'Не удалось сохранить оценку.')
    } finally {
      setIsSavingFeedback(false)
    }
  }

  return (
    <div className="flex flex-col gap-3 rounded-md border-t border-[rgba(215,239,255,0.35)] bg-dark-bg/40 p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-text-secondary">Подходы</p>

      {isLoadingSets && <p className="text-sm text-text-secondary">Загрузка...</p>}

      {!isLoadingSets && (
      <div className="flex flex-col gap-2">
        {Array.from({ length: targetSets }, (_, index) => index + 1).map((setNumber) => {
          const completed = completedSets[setNumber]

          if (completed !== undefined) {
            return (
              <div
                key={setNumber}
                className="flex min-w-0 items-center gap-2 rounded border border-white/5 bg-dark-card px-3 py-2 text-sm"
              >
                <i className="ti ti-check shrink-0 text-accent-ice" aria-hidden="true" />
                <span className="min-w-0 truncate text-text-secondary">Подход {setNumber}</span>
                <span className="ml-auto shrink-0 whitespace-nowrap font-mono text-text-primary">
                  {exercise.tracks_weight && completed.weight_kg !== null
                    ? `${completed.weight_kg}кг × ${completed.reps_completed ?? '—'}`
                    : (completed.reps_completed ?? '—')}
                </span>
              </div>
            )
          }

          // Current set: a plain 2px persimmon outline around the row (dark
          // fill unchanged) plus a text "Сейчас" label -- no filled/colored
          // block. Width budget at the narrowest supported viewport (320px):
          //   320 backdrop(-32, p-4×2) -> 288 card
          //   288 border(-2)           -> 286 modal body
          //   286 body p-6(-48)        -> 238 SetLogger p-4(-32) -> 206
          //   206 this row border-2(-4) + px-3×2(-24) -> 178px content
          // Each CompactNumberField (label ~30px + gap 8 + w-16 input 64px +
          // gap 8 + optional unit ~16px) tops out around 126px -- comfortably
          // under 178px stacked one per line. Side-by-side would need
          // ~126 + 12(gap) + ~96 =~ 234px, which does NOT fit -- that's why
          // weight and reps are stacked instead of in a row.
          if (setNumber === currentSetNumber && !allSetsDone) {
            return (
              <div
                key={setNumber}
                className="flex min-w-0 flex-col gap-3 rounded border-2 border-accent-persimmon bg-dark-card px-3 py-3"
              >
                <div className="flex min-w-0 items-center justify-between gap-2">
                  <span className="min-w-0 truncate text-sm font-medium text-text-primary">
                    Подход {setNumber}
                  </span>
                  <span className="shrink-0 text-xs font-medium uppercase tracking-wide text-accent-persimmon">
                    Сейчас
                  </span>
                </div>

                <div className="flex flex-col gap-2">
                  {exercise.tracks_weight && (
                    <div className="flex flex-col gap-1">
                      <CompactNumberField
                        label="Вес"
                        unit="кг"
                        value={weightInput}
                        disabled={isLoadingSuggestion || isSaving}
                        onChange={setWeightInput}
                      />
                      <span className="text-xs text-text-secondary">
                        {isLoadingSuggestion
                          ? 'Загрузка предложения...'
                          : suggestedWeightKg !== null
                            ? `Предложено системой: ${suggestedWeightKg} кг`
                            : 'Нет предложения — введите вес вручную'}
                      </span>
                    </div>
                  )}
                  <CompactNumberField
                    label="Повторы"
                    value={repsInput}
                    placeholder={exercise.target_reps !== null ? String(exercise.target_reps) : undefined}
                    disabled={isSaving}
                    onChange={setRepsInput}
                  />
                </div>

                <FormError message={saveError} />
                <Button onClick={handleSaveSet} isLoading={isSaving} className="self-start">
                  Готово
                </Button>
              </div>
            )
          }

          return (
            <div
              key={setNumber}
              className="flex min-w-0 items-center rounded border border-white/5 px-3 py-2 text-sm text-text-secondary/50"
            >
              <span className="min-w-0 truncate">Подход {setNumber}</span>
            </div>
          )
        })}
      </div>
      )}

      {feedback !== null ? (
        <div className="flex items-center justify-between gap-2 border-t border-white/5 pt-3 text-sm">
          <span className="text-text-secondary">Как ощущения?</span>
          <span className="flex items-center gap-1.5 font-medium text-accent-persimmon">
            <i className="ti ti-check" aria-hidden="true" />
            {SET_FEEDBACK_LABELS[feedback]}
          </span>
        </div>
      ) : (
        !isLoadingSets &&
        allSetsDone && (
          <div className="flex flex-col gap-2 border-t border-white/5 pt-3">
            <p className="text-xs font-medium uppercase tracking-wide text-text-secondary">Как ощущения?</p>
            <div className="flex flex-wrap gap-2">
              {SET_FEEDBACK_OPTIONS.map((option) => (
                <button
                  key={option}
                  type="button"
                  disabled={isSavingFeedback}
                  onClick={() => handleSaveFeedback(option)}
                  className="rounded border border-white/10 px-3 py-2 text-sm text-text-secondary transition-colors hover:border-white/30 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {SET_FEEDBACK_LABELS[option]}
                </button>
              ))}
            </div>
            <FormError message={feedbackError} />
          </div>
        )
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
      className={`text-xs font-medium text-accent-ice transition-opacity duration-300 ${
        visible ? 'opacity-100' : 'opacity-0'
      }`}
    >
      {message}
    </span>
  )
}
