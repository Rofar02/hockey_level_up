import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { BackLink } from '../components/ui/BackLink'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { Checkbox } from '../components/ui/Checkbox'
import { FormError } from '../components/ui/FormError'
import { IceGlowBackground } from '../components/ui/IceGlowBackground'
import { Modal } from '../components/ui/Modal'
import { TextField } from '../components/ui/TextField'
import * as authApi from '../api/auth'
import * as exercisesApi from '../api/exercises'
import * as progressApi from '../api/progress'
import * as scheduleApi from '../api/schedule'
import * as sessionBlocksApi from '../api/sessionBlocks'
import * as setCompletionsApi from '../api/setCompletions'
import { ApiError } from '../api/client'
import { useAuth } from '../hooks/useAuth'
import { TARGET_STAT_LABELS } from '../types/exercise'
import type { ExerciseRead, TargetStat } from '../types/exercise'
import type { TrainingStreakRead } from '../types/progress'
import type { SessionBlockRead, TrainingPhase } from '../types/schedule'
import { SET_FEEDBACK_LABELS, SET_FEEDBACK_OPTIONS } from '../types/setCompletion'
import type { SetCompletionRead, SetFeedback } from '../types/setCompletion'
import { toIsoDate } from '../utils/date'

const PHASE_LABELS: Record<TrainingPhase, string> = {
  warmup: 'Разминка',
  main: 'Основная часть',
  cooldown: 'Заминка',
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

  const [blocks, setBlocks] = useState<SessionBlockRead[] | null>(null)
  const [trainingSessionId, setTrainingSessionId] = useState<string | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [pendingIds, setPendingIds] = useState<Set<string>>(new Set())
  const [warmupExpanded, setWarmupExpanded] = useState(false)
  const [cooldownExpanded, setCooldownExpanded] = useState(false)
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
    scheduleApi
      .getCurrentWeeklyPlan(accessToken)
      .then((plan) => {
        if (cancelled) {
          return
        }
        const day = plan.day_plans.find((candidate) => candidate.id === dayPlanId)
        if (day?.training_session == null) {
          setLoadError('Тренировка не найдена.')
          return
        }
        setBlocks(day.training_session.blocks)
        setTrainingSessionId(day.training_session.id)
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

  return (
    <div className="relative min-h-svh overflow-hidden">
      <IceGlowBackground />
      <div className="relative z-[1] mx-auto flex max-w-2xl flex-col gap-6 px-4 py-10">
      <div className="flex flex-col gap-2">
        <BackLink />
        <h1 className="text-xl font-semibold">Тренировка дня</h1>
      </div>
      <FormError message={actionError} />

      {warmup.length > 0 && (
        <CollapsibleSection
          title={PHASE_LABELS.warmup}
          expanded={warmupExpanded}
          onToggle={() => setWarmupExpanded((value) => !value)}
        >
          {warmup.map((block) => (
            <ExerciseRow
              key={block.id}
              block={block}
              pending={pendingIds.has(block.id)}
              onComplete={() => handleComplete(block)}
              feedback={feedbackByBlockId[block.id]}
              onFeedbackDone={() => removeFeedback(block.id)}
              onOpenDetail={() => setSelectedExercise(block.exercise)}
            />
          ))}
        </CollapsibleSection>
      )}

      <Card>
        <h2 className="mb-4 text-sm font-medium text-text-secondary">{PHASE_LABELS.main}</h2>
        <div className="flex flex-col gap-3">
          {main.map((block) => (
            <ExerciseRow
              key={block.id}
              block={block}
              pending={pendingIds.has(block.id)}
              onComplete={() => handleComplete(block)}
              feedback={feedbackByBlockId[block.id]}
              onFeedbackDone={() => removeFeedback(block.id)}
              onOpenDetail={() => setSelectedExercise(block.exercise)}
              showTargetStat
            />
          ))}
        </div>
      </Card>

      {cooldown.length > 0 && (
        <CollapsibleSection
          title={PHASE_LABELS.cooldown}
          expanded={cooldownExpanded}
          onToggle={() => setCooldownExpanded((value) => !value)}
        >
          {cooldown.map((block) => (
            <ExerciseRow
              key={block.id}
              block={block}
              pending={pendingIds.has(block.id)}
              onComplete={() => handleComplete(block)}
              feedback={feedbackByBlockId[block.id]}
              onFeedbackDone={() => removeFeedback(block.id)}
              onOpenDetail={() => setSelectedExercise(block.exercise)}
            />
          ))}
        </CollapsibleSection>
      )}

      {selectedExercise !== null && trainingSessionId !== null && accessToken !== null && (
        <ExerciseDetailModal
          exercise={selectedExercise}
          trainingSessionId={trainingSessionId}
          accessToken={accessToken}
          onClose={() => setSelectedExercise(null)}
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

function CollapsibleSection({
  title,
  expanded,
  onToggle,
  children,
}: {
  title: string
  expanded: boolean
  onToggle: () => void
  children: ReactNode
}) {
  return (
    <Card>
      <button type="button" onClick={onToggle} className="flex w-full items-center justify-between text-left">
        <h2 className="text-sm font-medium text-text-secondary">{title}</h2>
        <span className="text-text-secondary">{expanded ? '−' : '+'}</span>
      </button>
      {expanded && <div className="mt-4 flex flex-col gap-3">{children}</div>}
    </Card>
  )
}

function ExerciseRow({
  block,
  pending,
  onComplete,
  feedback,
  onFeedbackDone,
  onOpenDetail,
  showTargetStat = false,
}: {
  block: SessionBlockRead
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
      className="-mx-2 flex cursor-pointer items-center justify-between gap-3 rounded px-2 py-1 transition-colors hover:bg-white/5"
    >
      <div className="flex items-center gap-3">
        {/* stopPropagation keeps ticking the checkbox from also opening the detail modal */}
        <span onClick={(event) => event.stopPropagation()}>
          <Checkbox checked={isCompleted} disabled={isCompleted || pending} onClick={onComplete} />
        </span>
        <div className="flex flex-col">
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

  return (
    <Modal title={exercise.name} onClose={onClose}>
      <div className="flex flex-col gap-4">
        {exercise.description !== null && (
          <p className="text-sm text-text-secondary">{exercise.description}</p>
        )}

        {targetVolume !== null && (
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

        {exercise.video_source_type === 'youtube' && exercise.video_source_id !== null ? (
          <div className="aspect-video overflow-hidden rounded-md">
            <iframe
              src={`https://www.youtube.com/embed/${exercise.video_source_id}`}
              title={exercise.name}
              className="h-full w-full"
              allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
              allowFullScreen
            />
          </div>
        ) : exercise.video_source_type === 'vk' ? (
          <p className="text-sm text-text-secondary">Embed для VK будет добавлен отдельно</p>
        ) : (
          <p className="text-sm text-text-secondary">Видео скоро появится</p>
        )}
      </div>
    </Modal>
  )
}

// Per-set logging layered on top of the exercise-level Checkbox in
// ExerciseRow: SessionBlock.completed_at (and the block_completed event that
// drives stat/XP gain) are untouched by any of this, this is purely the
// additional SetCompletion granularity.
//
// State is local to this component and does not survive the modal closing
// and reopening -- there is no GET endpoint yet to list a session's already-
// logged sets, only POST /set-completions and /set-completions/feedback, so
// there's nothing to rehydrate from on remount. Sets are still saved
// server-side each time, this only affects what the UI shows after a
// close/reopen.
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
  const [completedSets, setCompletedSets] = useState<Record<number, SetCompletionRead>>({})
  const [weightInput, setWeightInput] = useState('')
  const [repsInput, setRepsInput] = useState('')
  const [isSaving, setIsSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [feedback, setFeedback] = useState<SetFeedback | null>(null)
  const [isSavingFeedback, setIsSavingFeedback] = useState(false)
  const [feedbackError, setFeedbackError] = useState<string | null>(null)

  useEffect(() => {
    if (!exercise.tracks_weight) {
      return
    }
    let cancelled = false
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
    return () => {
      cancelled = true
    }
  }, [exercise.id, exercise.tracks_weight, accessToken])

  if (targetSets === null) {
    return null
  }

  const currentSetNumber = Object.keys(completedSets).length + 1
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

      <div className="flex flex-col gap-2">
        {Array.from({ length: targetSets }, (_, index) => index + 1).map((setNumber) => {
          const completed = completedSets[setNumber]

          if (completed !== undefined) {
            return (
              <div
                key={setNumber}
                className="flex items-center justify-between rounded border border-white/5 bg-dark-card px-3 py-2 text-sm"
              >
                <span className="text-text-secondary">Подход {setNumber}</span>
                <div className="flex items-center gap-2">
                  <span className="font-mono text-text-primary">
                    {exercise.tracks_weight && completed.weight_kg !== null
                      ? `${completed.weight_kg}×${completed.reps_completed ?? '—'}`
                      : (completed.reps_completed ?? '—')}
                  </span>
                  <i className="ti ti-check text-accent-ice" aria-hidden="true" />
                </div>
              </div>
            )
          }

          if (setNumber === currentSetNumber && !allSetsDone) {
            return (
              <div
                key={setNumber}
                className="flex flex-col gap-3 rounded border border-accent-persimmon bg-dark-card px-3 py-3"
              >
                <span className="text-sm font-medium text-text-primary">Подход {setNumber}</span>
                <div className="flex gap-3">
                  {exercise.tracks_weight && (
                    <div className="flex-1">
                      <TextField
                        label="Вес, кг"
                        numeric
                        type="number"
                        inputMode="decimal"
                        value={weightInput}
                        disabled={isLoadingSuggestion || isSaving}
                        onChange={(event) => setWeightInput(event.target.value)}
                      />
                      <span className="mt-1 block text-xs text-text-secondary">
                        {isLoadingSuggestion
                          ? 'Загрузка предложения...'
                          : suggestedWeightKg !== null
                            ? `Предложено системой: ${suggestedWeightKg} кг`
                            : 'Нет предложения — введите вес вручную'}
                      </span>
                    </div>
                  )}
                  <div className="flex-1">
                    <TextField
                      label="Повторы"
                      numeric
                      type="number"
                      inputMode="numeric"
                      value={repsInput}
                      disabled={isSaving}
                      onChange={(event) => setRepsInput(event.target.value)}
                    />
                  </div>
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
              className="flex items-center justify-between rounded border border-white/5 px-3 py-2 text-sm text-text-secondary/50"
            >
              <span>Подход {setNumber}</span>
            </div>
          )
        })}
      </div>

      {allSetsDone && (
        <div className="flex flex-col gap-2 border-t border-white/5 pt-3">
          <p className="text-xs font-medium uppercase tracking-wide text-text-secondary">Как ощущения?</p>
          <div className="flex flex-wrap gap-2">
            {SET_FEEDBACK_OPTIONS.map((option) => (
              <button
                key={option}
                type="button"
                disabled={isSavingFeedback}
                onClick={() => handleSaveFeedback(option)}
                className={`rounded border px-3 py-2 text-sm transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
                  feedback === option
                    ? 'border-accent-persimmon bg-accent-persimmon/10 text-accent-persimmon'
                    : 'border-white/10 text-text-secondary hover:border-white/30'
                }`}
              >
                {SET_FEEDBACK_LABELS[option]}
              </button>
            ))}
          </div>
          <FormError message={feedbackError} />
        </div>
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
