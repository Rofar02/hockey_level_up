import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { Button } from './ui/Button'
import { CARD_BORDER } from './ui/cardStyle'
import { FormError } from './ui/FormError'
import { Modal } from './ui/Modal'
import { ExerciseTechnique } from './ExerciseTechnique'
import * as exercisesApi from '../api/exercises'
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
import { hasExerciseTechnique } from '../utils/exerciseTechnique'

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

// The full exercise detail modal -- "Подходы" (SetLogger: suggested weight,
// per-set logging, feedback, state recovery) + "Техника" (video/
// description via the shared ExerciseTechnique). Used from
// TrainingSessionPage (today's actual session) and from NewSchedulePage
// (an already-started/completed day viewed from the weekly schedule) --
// both cases need the real logged data, not just the plan, which is what
// distinguishes this from NewSchedulePage's separate, genuinely read-only
// DayPreviewModal for not-yet-started future days.
export function ExerciseDetailModal({
  exercise,
  trainingSessionId,
  accessToken,
  onClose,
  onLastSetCompleted,
  blockId,
  onReplaced,
}: {
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
  // Stage 1.5 (2026-08-20 planning session, "тренажёр занят"): both must be
  // supplied together to show the "Заменить упражнение" button -- omitted
  // by NewSchedulePage's call site for now (a started day viewed from the
  // weekly schedule isn't necessarily *today*, and that page's more nested
  // state doesn't yet have a place to route the update), so the button
  // simply doesn't render there rather than needing a second wiring pass.
  blockId?: string
  onReplaced?: (updated: SessionBlockRead) => void
}) {
  const [activeTab, setActiveTab] = useState<ExerciseModalTab>('sets')
  const [isReplacing, setIsReplacing] = useState(false)
  const [replaceError, setReplaceError] = useState<string | null>(null)

  const targetVolume = formatTargetVolume(exercise)
  const hasSets = exercise.target_sets !== null
  const hasTechnique = hasExerciseTechnique(exercise)
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

  // Both tabs always show, on every exercise -- this is the app's standard
  // exercise-modal shape now, not conditional on which exercises happen to
  // have content filled in yet. Each tab falls back to an honest "not set
  // up yet" line instead of hiding itself when its exercise is missing
  // data (e.g. target_sets or description) -- catalog content gets filled
  // in separately (exercise admin edit), not invented here.
  return (
    <Modal title={exercise.name} onClose={onClose}>
      <div className="flex flex-col gap-3">
        <div className="-mx-6 -mt-6 flex border-b border-white/5 bg-dark-card">
          <TabButton active={activeTab === 'sets'} onClick={() => setActiveTab('sets')}>
            Подходы
          </TabButton>
          <TabButton active={activeTab === 'technique'} onClick={() => setActiveTab('technique')}>
            Техника
          </TabButton>
        </div>

        {activeTab === 'sets' &&
          (hasSets ? (
            <SetLogger
              exercise={exercise}
              trainingSessionId={trainingSessionId}
              accessToken={accessToken}
              onLastSetCompleted={onLastSetCompleted}
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
              {/* Without target_sets there's no SetLogger to auto-complete it
                  on a last-set save -- previously the only way to mark this
                  exercise done was to close the modal and tap the row's own
                  checkbox separately, an inconsistent extra step that sets-
                  based exercises don't need. onLastSetCompleted undefined
                  means the same thing it does for SetLogger -- read-only
                  context (NewSchedulePage) or already completed -- so this
                  mirrors that guard exactly. */}
              {onLastSetCompleted !== undefined && (
                <Button
                  onClick={() => {
                    onLastSetCompleted()
                    onClose()
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
            <ExerciseTechnique exercise={exercise} />
          ) : (
            <p className="text-sm text-text-secondary">Описание техники пока не добавлено.</p>
          ))}

        {canReplace && (
          <div className="flex flex-col gap-1.5 border-t border-white/5 pt-3">
            <button
              type="button"
              onClick={handleReplace}
              disabled={isReplacing}
              className="self-start text-sm text-accent-ice hover:underline disabled:opacity-50"
            >
              {isReplacing ? 'Подбираем замену...' : 'Заменить упражнение'}
            </button>
            <FormError message={replaceError} />
          </div>
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
        className="w-24 shrink-0 rounded-md border-2 border-white/10 bg-dark-bg px-3 py-2 font-mono text-lg font-semibold text-text-primary placeholder:text-text-secondary/50 focus:border-accent-ice focus:outline-none disabled:opacity-50"
        value={value}
        placeholder={placeholder}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
      />
      {unit !== undefined && <span className="shrink-0 text-xs text-text-secondary">{unit}</span>}
    </div>
  )
}

function formatRestClock(totalSeconds: number): string {
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return `${minutes}:${String(seconds).padStart(2, '0')}`
}

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
function RestTimer({ totalSeconds, onDone }: { totalSeconds: number; onDone: () => void }) {
  const [remaining, setRemaining] = useState(totalSeconds)
  const onDoneRef = useRef(onDone)
  onDoneRef.current = onDone

  useEffect(() => {
    if (remaining <= 0) {
      alertRestDone()
      onDoneRef.current()
      return
    }
    const timer = setTimeout(() => setRemaining((value) => value - 1), 1000)
    return () => clearTimeout(timer)
  }, [remaining])

  return (
    <div className="flex min-w-0 flex-col items-center gap-2 rounded border-2 border-accent-ice bg-dark-card px-3 py-4">
      <span className="text-xs font-medium uppercase tracking-wide text-text-secondary">
        Отдых перед следующим подходом
      </span>
      <span className="font-mono text-2xl text-accent-ice">{formatRestClock(Math.max(0, remaining))}</span>
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
}: {
  exercise: ExerciseRead
  trainingSessionId: string
  accessToken: string
  onLastSetCompleted?: () => void
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
  const [weightInput, setWeightInput] = useState('')
  const [repsInput, setRepsInput] = useState('')
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

  // Reps is the one number every set logs regardless of exercise type (the
  // "Повторы" field always renders, tracked weight or not -- a duration-per-
  // set input doesn't exist here, that's handled entirely outside SetLogger
  // via target_duration_seconds), so an empty reps field is never a
  // legitimate save -- it used to silently persist as reps_completed: null
  // and render as a permanent, unfixable "—" (found 2026-08-27: "если не
  // выбираешь подход оно ставится прочерком, не изменить нифига"). Mirrors
  // the weight requirement the backend already enforces server-side for
  // tracks_weight exercises (set_completion_service.save_set) -- gating it
  // here too means that 400 case (misreported below as the sanity-check
  // message) is no longer reachable from an empty field, only a real typo.
  const repsMissing = repsInput.trim() === ''
  const weightMissing = exercise.tracks_weight && weightInput.trim() === ''
  const canSaveSet = !repsMissing && !weightMissing

  function beginEditSet(
    setNumber: number,
    completed: Pick<SetCompletionSummary, 'weight_kg' | 'reps_completed'>,
  ) {
    setEditingSetNumber(setNumber)
    setWeightInput(completed.weight_kg !== null ? String(completed.weight_kg) : '')
    setRepsInput(completed.reps_completed !== null ? String(completed.reps_completed) : '')
    setSaveError(null)
  }

  function cancelEditSet() {
    setEditingSetNumber(null)
    setWeightInput('')
    setRepsInput('')
    setSaveError(null)
  }

  async function handleSaveSet() {
    if (!canSaveSet) {
      return
    }
    // Editing an already-logged set overwrites that same set_number in
    // place (see set_completion_service.save_set) rather than advancing
    // anything -- targetSetNumber is whichever this save is actually for.
    const targetSetNumber = editingSetNumber ?? currentSetNumber
    const isCorrection = editingSetNumber !== null
    const reps = Number(repsInput)
    const weight = exercise.tracks_weight ? Number(weightInput) : null

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
      setWeightInput('')
      setRepsInput('')

      if (isCorrection) {
        // Fixing history, not progressing -- no rest timer, no
        // auto-complete re-trigger, just back to the read-only list with
        // the corrected numbers showing.
        setEditingSetNumber(null)
        setSuggestedWeightKg(result.suggested_weight_kg)
        return
      }

      // Next set's fields start blank, not pre-filled with the fresh
      // suggestion -- an athlete who never touches the field must not have
      // the system's own guess silently recorded as what they actually
      // lifted (Stage 1.5, 2026-08-20 planning session). The number still
      // shows as a placeholder + the hint line below, one tap away via
      // "Совпадает".
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
        // a typo like 500 instead of 50 -- gets this friendlier copy instead
        // of the raw server message. The "required" 400 case can't land
        // here any more -- canSaveSet blocks an empty/missing weight before
        // the request is even sent.
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
    <div className={`flex flex-col gap-3 rounded-md ${CARD_BORDER} bg-dark-bg/40 p-4`}>
      <p className="text-xs font-medium uppercase tracking-wide text-text-secondary">Подходы</p>

      {isLoadingSets && <p className="text-sm text-text-secondary">Загрузка...</p>}

      {!isLoadingSets && (
      <div className="flex flex-col gap-2">
        {Array.from({ length: targetSets }, (_, index) => index + 1).map((setNumber) => {
          const completed = completedSets[setNumber]

          if (completed !== undefined && setNumber !== editingSetNumber) {
            return (
              // Tappable -- reopens this set for correction (beginEditSet
              // pre-fills the inputs below from its saved values). The old
              // "—" a blank reps field left behind used to be permanent;
              // this is what makes it fixable.
              <button
                key={setNumber}
                type="button"
                onClick={() => beginEditSet(setNumber, completed)}
                className="flex min-w-0 items-center gap-2 rounded border border-white/5 bg-dark-card px-3 py-2 text-left text-sm transition-colors hover:border-white/20"
              >
                <i className="ti ti-check shrink-0 text-accent-ice" aria-hidden="true" />
                <span className="min-w-0 truncate text-text-secondary">Подход {setNumber}</span>
                <span className="ml-auto shrink-0 whitespace-nowrap font-mono text-text-primary">
                  {exercise.tracks_weight && completed.weight_kg !== null
                    ? `${completed.weight_kg}кг × ${completed.reps_completed ?? '—'}`
                    : (completed.reps_completed ?? '—')}
                </span>
                <i className="ti ti-pencil shrink-0 text-xs text-text-secondary" aria-hidden="true" />
              </button>
            )
          }

          // Current set: identified purely by a plain 2px persimmon outline
          // around the row (dark fill unchanged) -- no extra "Сейчас" label,
          // no filled/colored block. Width budget at the narrowest supported
          // viewport (320px):
          //   320 backdrop(-32, p-4×2) -> 288 card
          //   288 border(-2)           -> 286 modal body
          //   286 body p-6(-48)        -> 238 SetLogger p-4(-32) -> 206
          //   206 this row border-2(-4) + px-3×2(-24) -> 178px content
          // Each CompactNumberField (label ~30px + gap 8 + w-20 input 80px +
          // gap 8 + optional unit ~16px) tops out around 142px -- still
          // under 178px stacked one per line. Side-by-side would need
          // ~142 + 12(gap) + ~112 =~ 266px, which does NOT fit -- that's why
          // weight and reps are stacked instead of in a row.
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
                  onDone={() => setRestState(null)}
                />
              )
            }
            return (
              <div
                key={setNumber}
                className="flex min-w-0 flex-col gap-3 rounded border-2 border-accent-persimmon bg-dark-card px-3 py-3"
              >
                <span className="min-w-0 truncate text-sm font-medium text-text-primary">
                  Подход {setNumber}
                  {isEditingThis && (
                    <span className="ml-2 text-xs font-normal text-text-secondary">(исправление)</span>
                  )}
                </span>

                <div className="flex flex-col gap-2">
                  {exercise.tracks_weight && (
                    <div className="flex flex-col gap-1">
                      {showWeightHint && (
                        <div className="mb-1 flex flex-col gap-2 rounded border border-accent-ice/30 bg-accent-ice/5 px-3 py-2.5">
                          <p className="text-xs leading-relaxed text-text-secondary">
                            Мы подсказываем вес, но поле всегда пустое — впишите то, что реально
                            подняли, или нажмите «Совпадает», если подсказка верна. После подхода
                            скажите, как ощущалось — в следующий раз подберём точнее.
                          </p>
                          <Button
                            variant="neutral"
                            onClick={dismissWeightHint}
                            className="self-start px-3 py-1 text-xs"
                          >
                            Понятно
                          </Button>
                        </div>
                      )}
                      <CompactNumberField
                        label="Вес"
                        unit="кг"
                        value={weightInput}
                        placeholder={suggestedWeightKg !== null ? String(suggestedWeightKg) : undefined}
                        disabled={isLoadingSuggestion || isSaving}
                        onChange={setWeightInput}
                      />
                      <span className="flex flex-wrap items-center gap-2 text-xs text-text-secondary">
                        {isLoadingSuggestion
                          ? 'Загрузка предложения...'
                          : suggestedWeightKg !== null
                            ? (
                              <>
                                <span>Сколько реально подняли? Предложено: {suggestedWeightKg} кг</span>
                                <button
                                  type="button"
                                  onClick={() => setWeightInput(String(suggestedWeightKg))}
                                  className="inline-flex items-center rounded-full border border-accent-ice/40 bg-accent-ice/10 px-2.5 py-0.5 text-[11px] font-semibold text-accent-ice transition-colors hover:bg-accent-ice/20"
                                >
                                  Совпадает
                                </button>
                              </>
                            )
                            : 'Нет предложения — введите вес вручную'}
                      </span>
                    </div>
                  )}
                  <div className="flex flex-col gap-1">
                    <CompactNumberField
                      label="Повторы"
                      value={repsInput}
                      placeholder={suggestedReps !== null ? String(suggestedReps) : undefined}
                      disabled={isLoadingRepsSuggestion || isSaving}
                      onChange={setRepsInput}
                    />
                    {hasRepRange && (
                      <span className="flex flex-wrap items-center gap-2 text-xs text-text-secondary">
                        {isLoadingRepsSuggestion
                          ? 'Загрузка предложения...'
                          : suggestedReps !== null
                            ? (
                              <>
                                <span>
                                  Сколько реально сделали? Предложено: {suggestedReps} (диапазон{' '}
                                  {exercise.rep_range_min}-{exercise.rep_range_max})
                                </span>
                                <button
                                  type="button"
                                  onClick={() => setRepsInput(String(suggestedReps))}
                                  className="inline-flex items-center rounded-full border border-accent-ice/40 bg-accent-ice/10 px-2.5 py-0.5 text-[11px] font-semibold text-accent-ice transition-colors hover:bg-accent-ice/20"
                                >
                                  Совпадает
                                </button>
                              </>
                            )
                            : 'Нет предложения — введите повторы вручную'}
                      </span>
                    )}
                  </div>
                </div>

                {/* Only reason canSaveSet can be false while the field is
                    non-empty is a fat-fingered value the server rejects
                    (FormError below covers that) -- this is specifically
                    what a disabled "Готово" with nothing typed yet means. */}
                {!canSaveSet && (
                  <p className="text-xs text-text-secondary">
                    {repsMissing
                      ? 'Введите количество повторений, чтобы сохранить подход.'
                      : 'Введите вес, чтобы сохранить подход.'}
                  </p>
                )}
                <FormError message={saveError} />
                <div className="flex items-center gap-3">
                  <Button
                    onClick={handleSaveSet}
                    isLoading={isSaving}
                    disabled={!canSaveSet}
                    className="self-start"
                  >
                    Готово
                  </Button>
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
                </div>
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
