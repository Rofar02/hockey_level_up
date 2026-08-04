import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { Button } from './ui/Button'
import { FormError } from './ui/FormError'
import { Modal } from './ui/Modal'
import { ExerciseTechnique } from './ExerciseTechnique'
import * as exercisesApi from '../api/exercises'
import * as setCompletionsApi from '../api/setCompletions'
import * as trainingSessionsApi from '../api/trainingSessions'
import { ApiError } from '../api/client'
import type { ExerciseRead } from '../types/exercise'
import { SET_FEEDBACK_LABELS, SET_FEEDBACK_OPTIONS } from '../types/setCompletion'
import type { SetCompletionSummary, SetFeedback } from '../types/setCompletion'
import { hasExerciseTechnique } from '../utils/exerciseTechnique'

// Same volume formatting as NewSchedulePage's own (page-local there, for
// its own unrelated display) -- duplicated rather than imported, matching
// this codebase's convention of duplicating small stable helpers per call
// site instead of centralizing every one of them.
function formatTargetVolume(exercise: ExerciseRead): string | null {
  if (exercise.target_sets !== null && exercise.target_reps !== null) {
    return `${exercise.target_sets} × ${exercise.target_reps}`
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
}: {
  exercise: ExerciseRead
  trainingSessionId: string
  accessToken: string
  onClose: () => void
}) {
  const [activeTab, setActiveTab] = useState<ExerciseModalTab>('sets')

  const targetVolume = formatTargetVolume(exercise)
  const hasSets = exercise.target_sets !== null
  const hasTechnique = hasExerciseTechnique(exercise)

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
            />
          ) : targetVolume !== null ? (
            <div className="flex items-center justify-between text-sm">
              <span className="text-text-secondary">Объём</span>
              <span className="font-mono text-text-primary">{targetVolume}</span>
            </div>
          ) : (
            <p className="text-sm text-text-secondary">
              Количество подходов для этого упражнения ещё не задано.
            </p>
          ))}

        {activeTab === 'technique' &&
          (hasTechnique ? (
            <ExerciseTechnique exercise={exercise} />
          ) : (
            <p className="text-sm text-text-secondary">Описание техники пока не добавлено.</p>
          ))}
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
        className="w-20 shrink-0 rounded border border-white/10 bg-dark-bg px-2 py-1.5 font-mono text-sm text-text-primary placeholder:text-text-secondary/60 focus:border-accent-ice focus:outline-none disabled:opacity-50"
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
          if (setNumber === currentSetNumber && !allSetsDone) {
            return (
              <div
                key={setNumber}
                className="flex min-w-0 flex-col gap-3 rounded border-2 border-accent-persimmon bg-dark-card px-3 py-3"
              >
                <span className="min-w-0 truncate text-sm font-medium text-text-primary">
                  Подход {setNumber}
                </span>

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
