import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { Button } from './ui/Button'
import { CARD_BORDER } from './ui/cardStyle'
import { CountdownRing } from './ui/CountdownRing'
import { FormError } from './ui/FormError'
import { Modal } from './ui/Modal'
import { Stepper } from './ui/Stepper'
import { ExerciseTechnique } from './ExerciseTechnique'
import { TimerPlayer } from './TimerPlayer'
import * as exercisesApi from '../api/exercises'
import * as progressApi from '../api/progress'
import * as sessionBlocksApi from '../api/sessionBlocks'
import * as setCompletionsApi from '../api/setCompletions'
import * as trainingSessionsApi from '../api/trainingSessions'
import * as usersApi from '../api/users'
import { ApiError } from '../api/client'
import { useAuth } from '../hooks/useAuth'
import type { ExerciseRead } from '../types/exercise'
import type { SessionBlockRead } from '../types/schedule'
import { SET_FEEDBACK_LABELS, SET_FEEDBACK_OPTIONS } from '../types/setCompletion'
import type { SetCompletionSummary, SetFeedback } from '../types/setCompletion'
import { exercisePlayerMode } from '../utils/exercisePlayerMode'
import { hasExerciseDescription, hasExerciseTechnique } from '../utils/exerciseTechnique'
import {
  ensureNotificationPermission,
  scheduleRestDoneNotification,
  type ScheduledRestNotification,
} from '../utils/restNotification'

// Same volume formatting as NewSchedulePage's own (page-local there, for
// its own unrelated display) -- duplicated rather than imported, matching
// this codebase's convention of duplicating small stable helpers per call
// site instead of centralizing every one of them.
function formatTargetVolume(exercise: ExerciseRead): string | null {
  if (exercise.target_sets !== null && exercise.rep_range_min !== null && exercise.rep_range_max !== null) {
    return `${exercise.target_sets} × ${exercise.rep_range_min}-${exercise.rep_range_max}`
  }
  if (exercise.target_duration_seconds !== null) {
    return `${exercise.target_duration_seconds} сек`
  }
  return null
}

type ExerciseModalTab = 'sets' | 'technique'

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean
  onClick: () => void
  children: ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex-1 border-b-2 px-4 py-2.5 text-sm font-medium transition-colors ${
        active ? 'border-accent-persimmon text-text-primary' : 'border-transparent text-[#8A94A6] hover:text-text-primary'
      }`}
    >
      {children}
    </button>
  )
}

// The boxed-modal shell -- used by NewSchedulePage (an already-started/
// completed day viewed from the weekly schedule, not the live session).
// TrainingSessionPage's own live flow uses ExerciseFocusScreen instead
// (full-screen, not boxed), which wraps the same ExerciseDetailBody below
// rather than duplicating it.
export function ExerciseDetailModal(props: ExerciseDetailBodyProps) {
  return (
    <Modal title={props.exercise.name} onClose={props.onClose}>
      <ExerciseDetailBody {...props} />
    </Modal>
  )
}

export interface ExerciseDetailBodyProps {
  exercise: ExerciseRead
  trainingSessionId: string
  accessToken: string
  onClose: () => void
  // Fires once, right after the set that reaches target_sets is saved --
  // undefined in read-only contexts (e.g. NewSchedulePage's view of an
  // already-started/completed day), where auto-completing a block would be
  // wrong. Just forwarded to SetLogger as-is; this component's own logic
  // doesn't otherwise change.
  onLastSetCompleted?: () => void
  // Fires once the post-completion feedback prompt is answered
  // (icelevel_player_master_prompt.md, 2026-08-28) -- ExerciseFocusScreen
  // uses this to auto-advance to the next exercise in the phase. Distinct
  // from onLastSetCompleted (which fires earlier, the moment the block
  // itself is done, before feedback is even asked). Undefined wherever
  // onLastSetCompleted is undefined -- same read-only/already-done gate.
  onSettled?: () => void
  // Stage 1.5 (2026-08-20 planning session, "тренажёр занят"): both must be
  // supplied together to show the "Заменить упражнение" button -- omitted
  // by NewSchedulePage's call site for now (a started day viewed from the
  // weekly schedule isn't necessarily *today*, and that page's more nested
  // state doesn't yet have a place to route the update), so the button
  // simply doesn't render there rather than needing a second wiring pass.
  blockId?: string
  onReplaced?: (updated: SessionBlockRead) => void
  // Warmup/cooldown-only (media-player redesign, 2026-08-28) -- undefined
  // whenever the block isn't a skippable phase, is already resolved, or
  // this is a read-only context, same gating style as onReplaced/blockId.
  // The actual API call + blocks-state merge + auto-advance lives in
  // TrainingSessionPage.handleSkip; this component only renders the
  // confirm affordance and calls onSkip() once confirmed.
  onSkip?: () => void
  // 'modal' (default): boxed Modal above supplies p-6 padding, so the tab
  // bar bleeds -mx-6/-mt-6 to sit flush with the modal's own edges, and the
  // no-target_sets fallback is the original plain "Объём: N сек" +
  // "Выполнено" row. 'focus': ExerciseFocusScreen's parent card pads with
  // p-4 instead (a -mx-6 there overflowed the card by 8px each side, found
  // 2026-08-28 screenshotting this), and the no-target_sets case is the
  // tactile Нужно/Старт/Подходы cluster (plan item 1a). SetLogger itself
  // (the target_sets branch) is identical either way.
  variant?: 'modal' | 'focus'
}

// "Подходы" (SetLogger: suggested weight, per-set logging, feedback, state
// recovery) + "Техника" (video/description via the shared ExerciseTechnique).
// Both cases need the real logged data, not just the plan, which is what
// distinguishes this from NewSchedulePage's separate, genuinely read-only
// DayPreviewModal for not-yet-started future days.
export function ExerciseDetailBody({
  exercise,
  trainingSessionId,
  accessToken,
  onClose,
  onLastSetCompleted,
  onSettled,
  blockId,
  onReplaced,
  onSkip,
  variant = 'modal',
}: ExerciseDetailBodyProps) {
  const [activeTab, setActiveTab] = useState<ExerciseModalTab>('sets')
  const [isReplacing, setIsReplacing] = useState(false)
  const [replaceError, setReplaceError] = useState<string | null>(null)
  const [isSkipConfirming, setIsSkipConfirming] = useState(false)
  const [isSkipping, setIsSkipping] = useState(false)

  const targetVolume = formatTargetVolume(exercise)
  const mode = exercisePlayerMode(exercise)
  // 'focus' hides the video here (ExerciseFocusScreen already shows it
  // above the tabs) -- gate on the description alone then, or a
  // video-only exercise would show an empty tab instead of either the
  // video or the "not added yet" fallback below.
  const hasTechnique =
    variant === 'focus' ? hasExerciseDescription(exercise) : hasExerciseTechnique(exercise)
  const canReplace = blockId !== undefined && onReplaced !== undefined

  async function handleReplace() {
    if (blockId === undefined || onReplaced === undefined || isReplacing) {
      return
    }
    setIsReplacing(true)
    setReplaceError(null)
    try {
      const updated = await sessionBlocksApi.replaceSessionBlockExercise(blockId, accessToken)
      onReplaced(updated)
    } catch (err) {
      setReplaceError(
        err instanceof ApiError && err.status === 409
          ? 'Нет доступной замены для этого упражнения.'
          : err instanceof ApiError
            ? err.message
            : 'Не удалось заменить упражнение.',
      )
    } finally {
      setIsReplacing(false)
    }
  }

  function handleSkipClick() {
    if (onSkip === undefined || isSkipping) {
      return
    }
    if (!isSkipConfirming) {
      setIsSkipConfirming(true)
      return
    }
    setIsSkipping(true)
    onSkip()
  }

  // Both tabs always show, on every exercise -- this is the app's standard
  // exercise-modal shape now, not conditional on which exercises happen to
  // have content filled in yet. Each tab falls back to an honest "not set
  // up yet" line instead of hiding itself when its exercise is missing
  // data (e.g. target_sets or description) -- catalog content gets filled
  // in separately (exercise admin edit), not invented here.
  return (
      <div className="flex flex-col gap-3">
        <div
          className={`flex border-b border-white/5 bg-dark-card ${
            // 'focus': ExerciseDetailBody isn't the first thing in its
            // parent card (the video block/skills line sit above it), so
            // only the horizontal bleed matters here -- -mt-6 would just
            // collapse the gap-4 spacing above it, not reach any edge.
            // 'modal': ExerciseDetailBody IS the first child inside
            // Modal's own p-6 body, so -mt-6 cancels that top padding to
            // sit flush under the modal's title bar.
            variant === 'focus' ? '-mx-4' : '-mx-6 -mt-6'
          }`}
        >
          <TabButton active={activeTab === 'sets'} onClick={() => setActiveTab('sets')}>
            {mode === 'duration' ? 'Выполнение' : 'Подходы'}
          </TabButton>
          <TabButton active={activeTab === 'technique'} onClick={() => setActiveTab('technique')}>
            Техника
          </TabButton>
        </div>

        {activeTab === 'sets' &&
          (mode === 'sets_reps' ? (
            <SetLogger
              exercise={exercise}
              trainingSessionId={trainingSessionId}
              accessToken={accessToken}
              onLastSetCompleted={onLastSetCompleted}
              onSettled={onSettled}
            />
          ) : mode === 'duration' ? (
            <TimerPlayer
              exercise={exercise}
              trainingSessionId={trainingSessionId}
              accessToken={accessToken}
              durationSeconds={exercise.target_duration_seconds!}
              rounds={exercise.target_sets ?? 1}
              isDone={onLastSetCompleted === undefined}
              onComplete={onLastSetCompleted}
              onSettled={onSettled}
            />
          ) : (
            <div className="flex flex-col gap-3">
              {targetVolume !== null ? (
                <div className="flex items-center justify-between text-sm">
                  <span className="text-text-secondary">Объём</span>
                  <span className="font-mono text-text-primary">{targetVolume}</span>
                </div>
              ) : (
                <p className="text-sm text-text-secondary">
                  Количество подходов для этого упражнения ещё не задано.
                </p>
              )}
              {/* Neither TimerPlayer nor SetLogger auto-completes this case
                  -- previously the only way to mark this exercise done was
                  to close the modal and tap the row's own checkbox
                  separately, an inconsistent extra step the other two modes
                  don't need. onLastSetCompleted undefined means the same
                  thing it does for both of those -- read-only context
                  (NewSchedulePage) or already completed -- so this mirrors
                  that guard exactly. No feedback prompt for this fallback
                  (there's nothing real logged to attach it to) -- 'focus'
                  goes straight to onSettled (auto-advance) instead of
                  onClose, which would otherwise return to the list instead
                  of moving to the next exercise like the other two modes do. */}
              {onLastSetCompleted !== undefined && (
                <Button
                  onClick={() => {
                    onLastSetCompleted()
                    if (variant === 'focus') {
                      onSettled?.()
                    } else {
                      onClose()
                    }
                  }}
                  className="self-start"
                >
                  Выполнено
                </Button>
              )}
            </div>
          ))}

        {activeTab === 'technique' &&
          (hasTechnique ? (
            <ExerciseTechnique exercise={exercise} hideVideo={variant === 'focus'} />
          ) : (
            <p className="text-sm text-text-secondary">Описание техники пока не добавлено.</p>
          ))}

        {(canReplace || onSkip !== undefined) && (
          <div className="flex flex-col gap-1.5 border-t border-white/5 pt-3">
            {canReplace && (
              <button
                type="button"
                onClick={handleReplace}
                disabled={isReplacing}
                className="self-start text-sm text-accent-ice hover:underline disabled:opacity-50"
              >
                {isReplacing ? 'Подбираем замену...' : 'Заменить упражнение'}
              </button>
            )}
            <FormError message={replaceError} />
            {onSkip !== undefined && (
              <button
                type="button"
                onClick={handleSkipClick}
                disabled={isSkipping}
                className={`self-start text-sm hover:underline disabled:opacity-50 ${
                  isSkipConfirming ? 'text-accent-persimmon' : 'text-text-secondary'
                }`}
              >
                {isSkipping ? 'Пропускаем...' : isSkipConfirming ? 'Точно пропустить?' : 'Пропустить упражнение'}
              </button>
            )}
          </div>
        )}
      </div>
  )
}

// −/+ around a big number, replacing the old text-field-with-keyboard input
// (icelevel_player_master_prompt.md, 2026-08-28) -- starts at whatever the
// caller resolves as the current effective value (a suggestion, or an
// already-saved value when reopened for correction) and only changes on an
// explicit tap, never via typing.
// Inline "совпадает/меньше/больше" read on a saved rep count against the
// exercise's own range -- the honest-reconciliation tag from the mockup,
// computed fresh from what's already stored rather than needing to record
// "what was suggested at save time" as new data.
function repsRangeTag(reps: number, min: number, max: number): 'match' | 'less' | 'more' {
  if (reps < min) {
    return 'less'
  }
  if (reps > max) {
    return 'more'
  }
  return 'match'
}

const REPS_TAG_LABELS = { match: 'совпадает', less: 'меньше', more: 'больше' } as const

// Vibration + a short synthesized beep (Web Audio oscillator, no external
// audio asset needed) when a rest countdown reaches zero. Both are
// best-effort -- navigator.vibrate isn't available on desktop browsers, and
// AudioContext can be blocked without a prior user gesture on some mobile
// browsers -- the visual countdown hitting 0:00 is the signal that always
// works regardless of whether either of these actually fires.
function alertRestDone() {
  if (typeof navigator.vibrate === 'function') {
    navigator.vibrate(200)
  }
  try {
    const AudioContextClass =
      window.AudioContext ??
      (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
    if (AudioContextClass === undefined) {
      return
    }
    const ctx = new AudioContextClass()
    const oscillator = ctx.createOscillator()
    const gain = ctx.createGain()
    oscillator.frequency.value = 880
    gain.gain.setValueAtTime(0.2, ctx.currentTime)
    oscillator.connect(gain)
    gain.connect(ctx.destination)
    oscillator.start()
    oscillator.stop(ctx.currentTime + 0.3)
    oscillator.onended = () => ctx.close()
  } catch {
    // Best-effort -- see comment above, the visual countdown already
    // reached zero regardless of whether this succeeds.
  }
}

// Auto-started by SetLogger right after a non-final set is saved (see
// restState there) -- counts down from the exercise's computed
// rest_seconds (app/core/rest.py's stimulus_type/difficulty_level formula)
// and fires alertRestDone + onDone once it reaches zero, so the next set's
// input reappears on its own without another tap. "Пропустить" lets the
// athlete end the rest early if they feel ready.
//
// Also schedules a local (on-device) notification for the same moment --
// see utils/restNotification.ts for why this is web-PWA best-effort, not a
// native guarantee -- so the athlete doesn't have to keep the screen
// unlocked and watching the countdown. Cancelled on unmount, which covers
// both "rest finished naturally" (this component unmounts right after
// alertRestDone fires) and "Пропустить" (unmounts immediately) -- either
// way there's nothing left to notify about.
function RestTimer({
  totalSeconds,
  accessToken,
  onDone,
}: {
  totalSeconds: number
  accessToken: string
  onDone: () => void
}) {
  const [remaining, setRemaining] = useState(totalSeconds)
  const onDoneRef = useRef(onDone)
  onDoneRef.current = onDone
  // Same wall-clock-deadline fix as TimerPlayer's work/rest ring (found
  // 2026-08-30 fixing that one): a tick-based countdown stalls while the
  // screen is locked and just resumes from wherever it froze once unlocked,
  // silently eating the locked time. This ring had no notification safety
  // net covering it either way -- scheduleRestDoneNotification below only
  // fires a background alert at the real deadline, it doesn't correct what
  // the on-screen digits show once the athlete looks again.
  const deadlineRef = useRef(Date.now() + totalSeconds * 1000)

  useEffect(() => {
    let cancelled = false
    let scheduled: ScheduledRestNotification = { cancel: () => {} }
    ensureNotificationPermission()
      .then(() => progressApi.getRestDonePhrase(accessToken))
      .then((phrase) => {
        if (!cancelled) {
          scheduled = scheduleRestDoneNotification(totalSeconds, phrase.text)
        }
      })
      .catch(() => {
        // Best-effort -- worst case this specific rest period just has no
        // background notification, the on-screen countdown still works.
      })
    return () => {
      cancelled = true
      scheduled.cancel()
    }
    // Deliberately mount-only (totalSeconds/accessToken don't change across
    // this component's lifetime -- a new rest period is always a fresh
    // RestTimer instance, per restState.forSetNumber's key in the caller).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    function sync() {
      setRemaining(Math.max(0, (deadlineRef.current - Date.now()) / 1000))
    }
    sync()
    const interval = setInterval(sync, 1000)
    // Recompute immediately on regaining visibility (screen unlock, tab
    // refocus) instead of waiting for the next 1s tick.
    document.addEventListener('visibilitychange', sync)
    return () => {
      clearInterval(interval)
      document.removeEventListener('visibilitychange', sync)
    }
  }, [])

  useEffect(() => {
    if (remaining > 0) {
      return
    }
    alertRestDone()
    onDoneRef.current()
  }, [remaining])

  return (
    <div className="flex min-w-0 flex-col items-center gap-2 py-2">
      <span className="text-xs font-medium uppercase tracking-wide text-text-secondary">
        Отдых перед следующим подходом
      </span>
      <CountdownRing
        size={120}
        totalSeconds={totalSeconds}
        remainingSeconds={Math.max(0, remaining)}
        label="Отдых"
        accent="persimmon"
      />
      <button
        type="button"
        onClick={onDone}
        className="text-xs text-text-secondary underline underline-offset-2 hover:text-text-primary"
      >
        Пропустить
      </button>
    </div>
  )
}

// Per-set logging layered on top of the exercise-level Checkbox in
// TrainingSessionPage's ExerciseRow: SessionBlock.completed_at (and the
// block_completed event that drives stat/XP gain) are untouched by any of
// this, this is purely the additional SetCompletion granularity.
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
  onLastSetCompleted,
  onSettled,
}: {
  exercise: ExerciseRead
  trainingSessionId: string
  accessToken: string
  onLastSetCompleted?: () => void
  // Fires once the feedback prompt below is answered (icelevel_player_
  // master_prompt.md, 2026-08-28: auto-advance to the next exercise) --
  // distinct from onLastSetCompleted, which ticks the block's completed_at
  // as soon as the LAST set is logged, before feedback is even asked.
  // Undefined in read-only contexts, same gate as onLastSetCompleted.
  onSettled?: () => void
}) {
  const { user, updateUser } = useAuth()
  const targetSets = exercise.target_sets
  const hasRepRange = exercise.rep_range_min !== null && exercise.rep_range_max !== null
  // Session-local guard, same reasoning as OnboardingTour's tourDismissed --
  // dismiss immediately regardless of whether the persist call below
  // succeeds, so a dropped request never leaves the hint stuck on screen.
  const [weightHintDismissed, setWeightHintDismissed] = useState(false)
  const [suggestedWeightKg, setSuggestedWeightKg] = useState<number | null>(null)
  const [isLoadingSuggestion, setIsLoadingSuggestion] = useState(exercise.tracks_weight)
  const [suggestedReps, setSuggestedReps] = useState<number | null>(null)
  const [isLoadingRepsSuggestion, setIsLoadingRepsSuggestion] = useState(hasRepRange)
  const [isLoadingSets, setIsLoadingSets] = useState(true)
  const [completedSets, setCompletedSets] = useState<
    Record<number, Pick<SetCompletionSummary, 'weight_kg' | 'reps_completed'>>
  >({})
  // null = "use the current suggestion" (icelevel_player_master_prompt.md,
  // 2026-08-28: the stepper starts pre-filled at the suggested number, not
  // empty) -- becomes a real number only once the athlete actually taps
  // +/-. Reset to null on every advance to a fresh set, so a suggestion
  // that finishes loading after that point still fills it in correctly.
  // The old Stage-1.5 protection ("never silently record an untouched
  // guess") is now the explicit tap on the confirm circle instead of a
  // blank-field requirement -- confirming still requires a deliberate
  // action, it's just not the deciding factor anymore whether the field
  // was literally edited.
  const [weightValue, setWeightValue] = useState<number | null>(null)
  const [repsValue, setRepsValue] = useState<number | null>(null)
  const [isSaving, setIsSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  // A completed set reopened for correction (tapped in the list below) --
  // null means no correction in progress, the normal "next pending set"
  // flow applies. Distinct from currentSetNumber (the first *un*-logged
  // set): editing set 2 while set 5 is still pending must show set 2's
  // input card, not set 5's, and must not touch restState/onLastSetCompleted
  // on save -- this is fixing history, not progressing forward. POST
  // /set-completions overwrites in place for a set_number that already has
  // a row (see set_completion_service.save_set's own comment), so no new
  // endpoint is needed to support this.
  const [editingSetNumber, setEditingSetNumber] = useState<number | null>(null)
  const [feedback, setFeedback] = useState<SetFeedback | null>(null)
  const [isSavingFeedback, setIsSavingFeedback] = useState(false)
  const [feedbackError, setFeedbackError] = useState<string | null>(null)
  // Set right after a non-final set is saved (see handleSaveSet) -- renders
  // RestTimer in place of the next set's input card until it counts down to
  // 0 or the athlete taps "Пропустить". forSetNumber pins the timer to the
  // specific set it's a rest *before*, so it never survives into rendering
  // for the wrong set.
  const [restState, setRestState] = useState<{ forSetNumber: number; totalSeconds: number } | null>(
    null,
  )

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

    if (hasRepRange) {
      exercisesApi
        .getSuggestedReps(exercise.id, accessToken)
        .then((result) => {
          if (cancelled) {
            return
          }
          setSuggestedReps(result.suggested_reps)
        })
        .catch(() => {
          // Best-effort -- same fallback as the weight suggestion above.
        })
        .finally(() => {
          if (!cancelled) {
            setIsLoadingRepsSuggestion(false)
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
  }, [exercise.id, exercise.tracks_weight, hasRepRange, trainingSessionId, accessToken])

  // First set_number (1..targetSets) without a logged record -- not just
  // Object.keys(completedSets).length + 1, in case rehydrated sets have a
  // gap. Computed before the targetSets===null early return below (and
  // guarded for it) so the auto-complete effect right after can see
  // allSetsDone on every render, not just once sets start getting logged.
  let currentSetNumber = targetSets === null ? 0 : targetSets + 1
  if (targetSets !== null) {
    for (let setNumber = 1; setNumber <= targetSets; setNumber += 1) {
      if (completedSets[setNumber] === undefined) {
        currentSetNumber = setNumber
        break
      }
    }
  }
  const allSetsDone = targetSets !== null && currentSetNumber > targetSets

  // handleSaveSet's onLastSetCompleted call (below) only fires as a side
  // effect of the save request for the Nth set landing -- it never runs if
  // the sets were already all logged by the time this modal opened (a
  // dropped completeSessionBlock call earlier, the app being backgrounded
  // mid-flow, sets logged in an older session before this feature existed,
  // etc). This effect is the reconciling path: whenever rehydration
  // settles and finds every set already logged, but the block itself
  // isn't marked complete yet, it fires the same callback -- handleComplete
  // is itself guarded against a block that's already completed, so this is
  // safe to re-run on every render once allSetsDone is true.
  useEffect(() => {
    if (!isLoadingSets && allSetsDone && onLastSetCompleted !== undefined) {
      onLastSetCompleted()
    }
  }, [isLoadingSets, allSetsDone, onLastSetCompleted])

  if (targetSets === null) {
    return null
  }

  const showWeightHint =
    exercise.tracks_weight && user !== null && !user.has_seen_weight_hint && !weightHintDismissed

  async function dismissWeightHint() {
    setWeightHintDismissed(true)
    try {
      const updated = await usersApi.markWeightHintSeen(accessToken)
      updateUser(updated)
    } catch {
      // Best-effort -- weightHintDismissed above already hides it for this
      // session; a failed persist just means it can show once more later.
    }
  }

  // Stepper always shows a real number (never blank), so there's nothing
  // left to validate before saving -- the effective value below is always
  // a legitimate reps count. (Previously an empty reps field used to
  // silently persist as reps_completed: null and render as a permanent,
  // unfixable "—" -- found 2026-08-27, "если не выбираешь подход оно
  // ставится прочерком, не изменить нифига" -- the stepper can't reach
  // that state at all, there's no empty state to leave it in.)
  const effectiveReps = repsValue ?? suggestedReps ?? exercise.rep_range_min ?? 1
  const effectiveWeight = weightValue ?? suggestedWeightKg ?? 0

  function beginEditSet(
    setNumber: number,
    completed: Pick<SetCompletionSummary, 'weight_kg' | 'reps_completed'>,
  ) {
    setEditingSetNumber(setNumber)
    setWeightValue(completed.weight_kg)
    setRepsValue(completed.reps_completed)
    setSaveError(null)
  }

  function cancelEditSet() {
    setEditingSetNumber(null)
    setWeightValue(null)
    setRepsValue(null)
    setSaveError(null)
  }

  async function handleSaveSet() {
    // Editing an already-logged set overwrites that same set_number in
    // place (see set_completion_service.save_set) rather than advancing
    // anything -- targetSetNumber is whichever this save is actually for.
    const targetSetNumber = editingSetNumber ?? currentSetNumber
    const isCorrection = editingSetNumber !== null
    const reps = effectiveReps
    const weight = exercise.tracks_weight ? effectiveWeight : null

    setSaveError(null)
    setIsSaving(true)
    try {
      const result = await setCompletionsApi.saveSet(
        {
          exercise_id: exercise.id,
          training_session_id: trainingSessionId,
          set_number: targetSetNumber,
          weight_kg: weight,
          reps_completed: reps,
        },
        accessToken,
      )
      setCompletedSets((previous) => ({ ...previous, [targetSetNumber]: result }))
      setWeightValue(null)
      setRepsValue(null)

      if (isCorrection) {
        // Fixing history, not progressing -- no rest timer, no
        // auto-complete re-trigger, just back to the read-only list with
        // the corrected numbers showing.
        setEditingSetNumber(null)
        setSuggestedWeightKg(result.suggested_weight_kg)
        return
      }

      // Next set's stepper starts at the fresh suggestion once it loads
      // (repsValue/weightValue are already back to null above) --
      // suggestions personalize per-set (RepsSuggestionService/
      // WeightSuggestionService), not just once per exercise.
      setSuggestedWeightKg(result.suggested_weight_kg)

      if (hasRepRange) {
        setIsLoadingRepsSuggestion(true)
        exercisesApi
          .getSuggestedReps(exercise.id, accessToken)
          .then((repsResult) => {
            setSuggestedReps(repsResult.suggested_reps)
          })
          .catch(() => {
            setSuggestedReps(null)
          })
          .finally(() => {
            setIsLoadingRepsSuggestion(false)
          })
      }

      // targetSetNumber is the set just saved (captured before this async
      // call started) -- if it's the last one, tick the exercise off
      // automatically instead of making the user tap the checkbox
      // separately. onLastSetCompleted is undefined in read-only contexts
      // (NewSchedulePage), where this must never fire.
      if (targetSetNumber === targetSets) {
        if (onLastSetCompleted !== undefined) {
          onLastSetCompleted()
        }
      } else if (exercise.rest_seconds !== null) {
        // Only between sets of *this* exercise -- there's no next set to
        // rest before once the last one is saved, whatever comes after
        // (next exercise, or done) isn't this formula's concern.
        setRestState({ forSetNumber: targetSetNumber + 1, totalSeconds: exercise.rest_seconds })
      }
    } catch (err) {
      if (err instanceof ApiError && err.status === 400) {
        // The specific case the backend's >3x sanity check guards against --
        // a typo like 500 instead of 50. The "required" 400 case can't land
        // here any more -- the stepper never produces an empty/missing
        // weight, only a real out-of-range number the server itself flags.
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
      // Fires the auto-advance-to-next-exercise flow (icelevel_player_
      // master_prompt.md, 2026-08-28) -- only from a fresh tap here, never
      // when `feedback` was already non-null on load (reopening a
      // previously-answered exercise renders the read-only label below
      // instead of this picker at all, so handleSaveFeedback can't
      // re-run).
      onSettled?.()
    } catch (err) {
      setFeedbackError(err instanceof ApiError ? err.message : 'Не удалось сохранить оценку.')
    } finally {
      setIsSavingFeedback(false)
    }
  }

  return (
    <div className={`flex flex-col gap-3 rounded-md ${CARD_BORDER} bg-dark-bg/40 p-4`}>
      <p className="text-xs font-medium uppercase tracking-wide text-text-secondary">Подходы</p>

      {isLoadingSets && <p className="text-sm text-text-secondary">Загрузка...</p>}

      {!isLoadingSets && (
      <div className="flex flex-col gap-2">
        {Array.from({ length: targetSets }, (_, index) => index + 1).map((setNumber) => {
          const completed = completedSets[setNumber]

          if (completed !== undefined && setNumber !== editingSetNumber) {
            // Compact row, not a card -- icelevel_player_master_prompt.md
            // (2026-08-28): each set is one tappable row (reopens for
            // correction via beginEditSet), not a form-like card.
            const reps = completed.reps_completed
            const tag =
              reps !== null && hasRepRange
                ? repsRangeTag(reps, exercise.rep_range_min!, exercise.rep_range_max!)
                : null
            return (
              <button
                key={setNumber}
                type="button"
                onClick={() => beginEditSet(setNumber, completed)}
                className="flex min-w-0 items-center justify-between gap-2 rounded-md border border-white/5 bg-dark-card px-3 py-2.5 text-left transition-colors hover:border-white/20"
              >
                <span className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-0.5">
                  <span className="shrink-0 font-display text-sm font-semibold text-text-primary">
                    Подход {setNumber}
                  </span>
                  {tag !== null ? (
                    <span
                      className={`shrink-0 rounded-full px-2 py-0.5 font-display text-[10px] uppercase tracking-wide ${
                        tag === 'match' ? 'bg-accent-ice/15 text-accent-ice' : 'bg-white/10 text-text-secondary'
                      }`}
                    >
                      {reps} {REPS_TAG_LABELS[tag]}
                    </span>
                  ) : (
                    reps !== null && (
                      <span className="shrink-0 font-mono text-xs text-text-secondary">
                        {exercise.tracks_weight && completed.weight_kg !== null
                          ? `${completed.weight_kg}кг x ${reps}`
                          : reps}
                      </span>
                    )
                  )}
                </span>
                <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-accent-ice text-dark-bg">
                  <i className="ti ti-check text-sm" aria-hidden="true" />
                </span>
              </button>
            )
          }

          const isEditingThis = setNumber === editingSetNumber
          if (isEditingThis || (setNumber === currentSetNumber && !allSetsDone && editingSetNumber === null)) {
            // The rest timer only ever gates the forward "next pending set"
            // flow -- reopening an earlier completed set for a correction
            // must show its input card immediately, never a rest countdown
            // left over from progressing past it the first time.
            if (!isEditingThis && restState !== null && restState.forSetNumber === setNumber) {
              return (
                <RestTimer
                  key={setNumber}
                  totalSeconds={restState.totalSeconds}
                  accessToken={accessToken}
                  onDone={() => setRestState(null)}
                />
              )
            }
            return (
              <div key={setNumber} className="flex flex-col gap-2">
                {showWeightHint && exercise.tracks_weight && (
                  <div className="flex flex-col gap-2 rounded border border-accent-ice/30 bg-accent-ice/5 px-3 py-2.5">
                    <p className="text-xs leading-relaxed text-text-secondary">
                      Мы подсказываем вес, но стартовое значение можно скорректировать стрелками
                      до того, что реально подняли. После подхода скажите, как ощущалось — в
                      следующий раз подберём точнее.
                    </p>
                    <Button variant="neutral" onClick={dismissWeightHint} className="self-start px-3 py-1 text-xs">
                      Понятно
                    </Button>
                  </div>
                )}
                <div className="flex flex-col gap-2 rounded-md border-2 border-accent-persimmon bg-dark-card px-3 py-2.5">
                  <span className="font-display text-sm font-semibold text-text-primary">
                    Подход {setNumber}
                    {isEditingThis && (
                      <span className="ml-2 text-xs font-normal text-text-secondary">(исправление)</span>
                    )}
                  </span>
                  {/* Own row, wrapping if needed -- both steppers side by
                      side previously squeezed this row's label down to
                      nothing on a narrow phone (2026-08-29: "слово подход
                      теряется если есть вес"). Label now always gets its own
                      full-width line above instead of sharing one row with
                      the steppers. */}
                  <div className="flex flex-wrap items-center gap-3">
                    {exercise.tracks_weight && (
                      <Stepper
                        value={effectiveWeight}
                        unit="кг"
                        step={2.5}
                        disabled={isLoadingSuggestion || isSaving}
                        onChange={setWeightValue}
                      />
                    )}
                    <Stepper
                      value={effectiveReps}
                      step={1}
                      min={1}
                      disabled={isLoadingRepsSuggestion || isSaving}
                      onChange={setRepsValue}
                    />
                  </div>
                </div>
                <FormError message={saveError} />
                <div className="flex items-center justify-end gap-3">
                  {isEditingThis && (
                    <button
                      type="button"
                      onClick={cancelEditSet}
                      disabled={isSaving}
                      className="text-sm text-text-secondary underline underline-offset-2 hover:text-text-primary disabled:opacity-50"
                    >
                      Отмена
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={handleSaveSet}
                    disabled={isSaving}
                    aria-label="Подтвердить подход"
                    className="flex h-9 w-9 items-center justify-center rounded-full bg-accent-ice text-dark-bg transition-opacity hover:opacity-90 disabled:opacity-50"
                  >
                    <i className="ti ti-check text-lg" aria-hidden="true" />
                  </button>
                </div>
              </div>
            )
          }

          return (
            <div
              key={setNumber}
              className="flex min-w-0 items-center rounded-md border border-white/5 px-3 py-2.5 text-text-secondary/50"
            >
              <span className="min-w-0 truncate font-display text-sm">Подход {setNumber}</span>
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

