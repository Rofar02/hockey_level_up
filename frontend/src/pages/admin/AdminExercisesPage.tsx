import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { AdminLayout } from '../../components/admin/AdminLayout'
import { AdminModal } from '../../components/admin/AdminModal'
import { Button } from '../../components/ui/Button'
import { FormError } from '../../components/ui/FormError'
import { SelectField } from '../../components/ui/SelectField'
import { TextField } from '../../components/ui/TextField'
import * as exercisesApi from '../../api/exercises'
import * as skillsApi from '../../api/skills'
import { ApiError } from '../../api/client'
import { useAuth } from '../../hooks/useAuth'
import {
  CATALOG_HEALTH_ISSUE_LABELS,
  EQUIPMENT_ITEMS,
  EQUIPMENT_ITEM_LABELS,
  EXERCISE_CATEGORIES,
  EXERCISE_CATEGORY_LABELS,
  EXERCISE_TYPES,
  EXERCISE_TYPE_LABELS,
  MOVEMENT_PATTERNS,
  MOVEMENT_PATTERN_LABELS,
  MUSCLE_GROUPS,
  MUSCLE_GROUP_LABELS,
  STIMULUS_TYPES,
  STIMULUS_TYPE_LABELS,
  TARGET_STATS,
  TARGET_STAT_LABELS,
  WARMUP_STAGES,
  WARMUP_STAGE_LABELS,
} from '../../types/exercise'
import type {
  CatalogHealthIssue,
  EquipmentItem,
  ExerciseCategory,
  ExerciseRead,
  ExerciseType,
  ExerciseWrite,
  MovementPattern,
  MuscleGroup,
  StimulusType,
  TargetStat,
  WarmupStage,
} from '../../types/exercise'
import { TRAINING_PHASES } from '../../types/schedule'
import type { TrainingPhase } from '../../types/schedule'
import type { SkillOption, SkillTagRead } from '../../types/skill'

const PHASE_LABELS: Record<TrainingPhase, string> = {
  warmup: 'Разминка',
  main: 'Основная часть',
  cooldown: 'Заминка',
  puck: 'Владение шайбой',
}

const CATEGORY_OPTIONS = EXERCISE_CATEGORIES.map((value) => ({
  value,
  label: EXERCISE_CATEGORY_LABELS[value],
}))
const PHASE_OPTIONS = TRAINING_PHASES.map((value) => ({ value, label: PHASE_LABELS[value] }))
const TARGET_STAT_OPTIONS = TARGET_STATS.map((value) => ({ value, label: TARGET_STAT_LABELS[value] }))
const EQUIPMENT_ITEM_OPTIONS = EQUIPMENT_ITEMS.map((value) => ({
  value,
  label: EQUIPMENT_ITEM_LABELS[value],
}))
const MUSCLE_GROUP_OPTIONS = MUSCLE_GROUPS.map((value) => ({
  value,
  label: MUSCLE_GROUP_LABELS[value],
}))
const STIMULUS_TYPE_OPTIONS = STIMULUS_TYPES.map((value) => ({
  value,
  label: STIMULUS_TYPE_LABELS[value],
}))
const EXERCISE_TYPE_OPTIONS = EXERCISE_TYPES.map((value) => ({
  value,
  label: EXERCISE_TYPE_LABELS[value],
}))
const WARMUP_STAGE_OPTIONS = WARMUP_STAGES.map((value) => ({
  value,
  label: WARMUP_STAGE_LABELS[value],
}))

export function AdminExercisesPage() {
  const { accessToken } = useAuth()

  const [category, setCategory] = useState<ExerciseCategory | ''>('')
  const [phase, setPhase] = useState<TrainingPhase | ''>('')
  const [targetStat, setTargetStat] = useState<TargetStat | ''>('')
  // Client-side only, unlike the three filters above -- GET /exercises has
  // no stimulus_type/exercise_type query params on the backend, and with
  // the catalog's current size (~150 rows, already fetched whole into
  // state) a round trip for these two isn't worth adding API surface for.
  const [stimulusType, setStimulusType] = useState<StimulusType | ''>('')
  const [exerciseType, setExerciseType] = useState<ExerciseType | ''>('')

  const [exercises, setExercises] = useState<ExerciseRead[] | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  // Stage 3 (2026-08-20 planning session): fetched once, independently of
  // the category/phase/target_stat filters above -- a health issue can
  // exist in a category the admin currently isn't looking at, and this is
  // small (one row per *problem* exercise, not the whole catalog).
  const [catalogHealthIssues, setCatalogHealthIssues] = useState<CatalogHealthIssue[] | null>(null)
  const [healthOnly, setHealthOnly] = useState(false)

  const [isFormOpen, setIsFormOpen] = useState(false)
  const [editingExercise, setEditingExercise] = useState<ExerciseRead | null>(null)

  useEffect(() => {
    if (accessToken === null) {
      return
    }
    let cancelled = false
    setIsLoading(true)
    exercisesApi
      .listExercises(
        {
          category: category === '' ? undefined : category,
          phase: phase === '' ? undefined : phase,
          target_stat: targetStat === '' ? undefined : targetStat,
        },
        accessToken,
      )
      .then((result) => {
        if (!cancelled) {
          setExercises(result)
          setLoadError(null)
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setLoadError(err instanceof ApiError ? err.message : 'Не удалось загрузить упражнения.')
        }
      })
      .finally(() => {
        if (!cancelled) {
          setIsLoading(false)
        }
      })
    return () => {
      cancelled = true
    }
  }, [accessToken, category, phase, targetStat])

  useEffect(() => {
    if (accessToken === null) {
      return
    }
    let cancelled = false
    exercisesApi
      .listCatalogHealthIssues(accessToken)
      .then((result) => {
        if (!cancelled) {
          setCatalogHealthIssues(result)
        }
      })
      .catch(() => {
        // Non-fatal -- the exercise list itself already loaded/loads
        // independently above; the health column/filter just stays empty.
      })
    return () => {
      cancelled = true
    }
  }, [accessToken])

  const issuesByExerciseId = new Map(
    (catalogHealthIssues ?? []).map((issue) => [issue.exercise_id, issue.missing]),
  )

  function openCreateForm() {
    setEditingExercise(null)
    setIsFormOpen(true)
  }

  function openEditForm(exercise: ExerciseRead) {
    setEditingExercise(exercise)
    setIsFormOpen(true)
  }

  function handleSaved(saved: ExerciseRead) {
    setExercises((previous) => {
      if (previous === null) {
        return previous
      }
      const exists = previous.some((item) => item.id === saved.id)
      return exists
        ? previous.map((item) => (item.id === saved.id ? saved : item))
        : [...previous, saved]
    })
  }

  async function handleDelete(exercise: ExerciseRead) {
    if (accessToken === null) {
      return
    }
    if (!window.confirm(`Удалить упражнение «${exercise.name}»?`)) {
      return
    }
    try {
      await exercisesApi.deleteExercise(exercise.id, accessToken)
      setExercises((previous) => previous?.filter((item) => item.id !== exercise.id) ?? previous)
    } catch (err) {
      window.alert(err instanceof ApiError ? err.message : 'Не удалось удалить упражнение.')
    }
  }

  const filteredExercises = (exercises ?? []).filter(
    (exercise) =>
      (stimulusType === '' || exercise.stimulus_type === stimulusType)
      && (exerciseType === '' || exercise.exercise_type === exerciseType)
      && (!healthOnly || (issuesByExerciseId.get(exercise.id)?.length ?? 0) > 0),
  )

  return (
    <AdminLayout title="Упражнения">
      <div className="mb-4 flex flex-wrap items-end justify-between gap-4">
        <div className="flex flex-wrap gap-3">
          <SelectField
            label="Категория"
            options={CATEGORY_OPTIONS}
            placeholder="Все"
            value={category}
            onChange={(event) => setCategory(event.target.value as ExerciseCategory | '')}
          />
          <SelectField
            label="Фаза"
            options={PHASE_OPTIONS}
            placeholder="Все"
            value={phase}
            onChange={(event) => setPhase(event.target.value as TrainingPhase | '')}
          />
          <SelectField
            label="Характеристика"
            options={TARGET_STAT_OPTIONS}
            placeholder="Все"
            value={targetStat}
            onChange={(event) => setTargetStat(event.target.value as TargetStat | '')}
          />
          <SelectField
            label="Stimulus type"
            options={STIMULUS_TYPE_OPTIONS}
            placeholder="Все"
            value={stimulusType}
            onChange={(event) => setStimulusType(event.target.value as StimulusType | '')}
          />
          <SelectField
            label="Exercise type"
            options={EXERCISE_TYPE_OPTIONS}
            placeholder="Все"
            value={exerciseType}
            onChange={(event) => setExerciseType(event.target.value as ExerciseType | '')}
          />
          <label className="flex items-center gap-2 self-end pb-2 text-sm text-text-secondary">
            <input
              type="checkbox"
              checked={healthOnly}
              onChange={(event) => setHealthOnly(event.target.checked)}
            />
            Только с проблемами каталога
            {catalogHealthIssues !== null && ` (${catalogHealthIssues.length})`}
          </label>
        </div>
        <Button type="button" onClick={openCreateForm}>
          Добавить упражнение
        </Button>
      </div>

      <FormError message={loadError} />
      {isLoading && <p className="text-sm text-text-secondary">Загрузка...</p>}

      {!isLoading && exercises !== null && filteredExercises.length === 0 && (
        <p className="text-sm text-text-secondary">Ничего не найдено.</p>
      )}

      {!isLoading && exercises !== null && filteredExercises.length > 0 && (
        <>
          <div className="hidden overflow-x-auto rounded-md border border-white/10 md:block">
            <table className="w-full min-w-[720px] border-collapse text-sm">
              <thead>
                <tr className="border-b border-white/10 bg-white/5 text-left text-text-secondary">
                  <th className="px-3 py-2 font-medium">Название</th>
                  <th className="px-3 py-2 font-medium">Категория</th>
                  <th className="px-3 py-2 font-medium">Фаза</th>
                  <th className="px-3 py-2 font-medium">Характеристика</th>
                  <th className="px-3 py-2 font-medium">Stimulus</th>
                  <th className="px-3 py-2 font-medium">Exercise type</th>
                  <th className="px-3 py-2 font-medium">Сложность</th>
                  <th className="px-3 py-2 font-medium">Здоровье</th>
                  <th className="px-3 py-2 font-medium" />
                </tr>
              </thead>
              <tbody>
                {filteredExercises.map((exercise) => (
                  <tr key={exercise.id} className="border-b border-white/5 hover:bg-white/5">
                    <td className="px-3 py-2 text-text-primary">{exercise.name}</td>
                    <td className="px-3 py-2 text-text-secondary">
                      {EXERCISE_CATEGORY_LABELS[exercise.category]}
                    </td>
                    <td className="px-3 py-2 text-text-secondary">
                      {PHASE_LABELS[exercise.phase]}
                      {exercise.phase === 'warmup' && exercise.warmup_stage === null && (
                        <span
                          className="ml-1.5 text-accent-persimmon"
                          title="Без стадии разминки — никогда не попадёт в собранную разминку"
                        >
                          ⚠
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-text-secondary">
                      {exercise.target_stats.length === 0
                        ? '—'
                        : exercise.target_stats.map((stat) => TARGET_STAT_LABELS[stat]).join(', ')}
                    </td>
                    <td className="px-3 py-2 text-text-secondary">
                      {exercise.stimulus_type === null ? '—' : STIMULUS_TYPE_LABELS[exercise.stimulus_type]}
                    </td>
                    <td className="px-3 py-2 text-text-secondary">
                      {exercise.exercise_type === null ? '—' : EXERCISE_TYPE_LABELS[exercise.exercise_type]}
                    </td>
                    <td className="px-3 py-2 font-mono text-text-secondary">{exercise.difficulty_level}</td>
                    <td className="px-3 py-2 text-accent-persimmon">
                      {(issuesByExerciseId.get(exercise.id) ?? []).length === 0
                        ? <span className="text-text-secondary">—</span>
                        : (
                          <span title={(issuesByExerciseId.get(exercise.id) ?? [])
                            .map((code) => CATALOG_HEALTH_ISSUE_LABELS[code] ?? code)
                            .join('; ')}
                          >
                            ⚠ {(issuesByExerciseId.get(exercise.id) ?? []).length}
                          </span>
                        )}
                    </td>
                    <td className="px-3 py-2 text-right">
                      <div className="flex justify-end gap-3">
                        <button
                          type="button"
                          onClick={() => openEditForm(exercise)}
                          className="text-accent-ice hover:underline"
                        >
                          Изменить
                        </button>
                        <button
                          type="button"
                          onClick={() => handleDelete(exercise)}
                          className="text-accent-persimmon hover:underline"
                        >
                          Удалить
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="flex flex-col gap-3 md:hidden">
            {filteredExercises.map((exercise) => (
              <div key={exercise.id} className="rounded-md border border-white/10 bg-dark-card p-3">
                <p className="text-sm font-medium text-text-primary">{exercise.name}</p>
                <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs text-text-secondary">
                  <span>{EXERCISE_CATEGORY_LABELS[exercise.category]}</span>
                  <span>
                    {PHASE_LABELS[exercise.phase]}
                    {exercise.phase === 'warmup' && exercise.warmup_stage === null && (
                      <span
                        className="ml-1 text-accent-persimmon"
                        title="Без стадии разминки — никогда не попадёт в собранную разминку"
                      >
                        ⚠
                      </span>
                    )}
                  </span>
                  <span className="font-mono">Сложность: {exercise.difficulty_level}</span>
                </div>
                <p className="mt-1 text-xs text-text-secondary">
                  {exercise.target_stats.length === 0
                    ? '—'
                    : exercise.target_stats.map((stat) => TARGET_STAT_LABELS[stat]).join(', ')}
                </p>
                <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs text-text-secondary">
                  <span>
                    Stimulus: {exercise.stimulus_type === null ? '—' : STIMULUS_TYPE_LABELS[exercise.stimulus_type]}
                  </span>
                  <span>
                    Type: {exercise.exercise_type === null ? '—' : EXERCISE_TYPE_LABELS[exercise.exercise_type]}
                  </span>
                </div>
                {(issuesByExerciseId.get(exercise.id) ?? []).length > 0 && (
                  <p className="mt-1 text-xs text-accent-persimmon">
                    ⚠ {(issuesByExerciseId.get(exercise.id) ?? [])
                      .map((code) => CATALOG_HEALTH_ISSUE_LABELS[code] ?? code)
                      .join('; ')}
                  </p>
                )}
                <div className="mt-2 flex gap-4 text-sm">
                  <button
                    type="button"
                    onClick={() => openEditForm(exercise)}
                    className="text-accent-ice hover:underline"
                  >
                    Изменить
                  </button>
                  <button
                    type="button"
                    onClick={() => handleDelete(exercise)}
                    className="text-accent-persimmon hover:underline"
                  >
                    Удалить
                  </button>
                </div>
              </div>
            ))}
          </div>
        </>
      )}

      {isFormOpen && (
        <ExerciseFormModal
          exercise={editingExercise}
          onClose={() => setIsFormOpen(false)}
          onSaved={handleSaved}
        />
      )}
    </AdminLayout>
  )
}

function parseOptionalInt(value: string): number | null {
  return value.trim() === '' ? null : Number(value)
}

function parseOptionalFloat(value: string): number | null {
  return value.trim() === '' ? null : Number(value)
}

function ExerciseFormModal({
  exercise,
  onClose,
  onSaved,
}: {
  exercise: ExerciseRead | null
  onClose: () => void
  onSaved: (exercise: ExerciseRead) => void
}) {
  const { accessToken } = useAuth()

  // Tracks the record actually persisted so far -- distinct from the
  // `exercise` prop (the value the form was *opened* with): once a create
  // succeeds this flips from null to the new record so the "Связанные
  // навыки" section below can appear immediately, without closing the modal
  // and making the admin reopen it just to tag their new exercise.
  const [currentExercise, setCurrentExercise] = useState<ExerciseRead | null>(exercise)

  const [name, setName] = useState(exercise?.name ?? '')
  const [description, setDescription] = useState(exercise?.description ?? '')
  const [category, setCategory] = useState<ExerciseCategory>(exercise?.category ?? 'off_ice')
  const [phase, setPhase] = useState<TrainingPhase>(exercise?.phase ?? 'main')
  const [difficultyLevel, setDifficultyLevel] = useState(String(exercise?.difficulty_level ?? 1))
  const [videoSourceType, setVideoSourceType] = useState(exercise?.video_source_type ?? '')
  const [videoSourceId, setVideoSourceId] = useState(exercise?.video_source_id ?? '')
  const [targetSets, setTargetSets] = useState(
    exercise?.target_sets != null ? String(exercise.target_sets) : '',
  )
  const [repRangeMin, setRepRangeMin] = useState(
    exercise?.rep_range_min != null ? String(exercise.rep_range_min) : '',
  )
  const [repRangeMax, setRepRangeMax] = useState(
    exercise?.rep_range_max != null ? String(exercise.rep_range_max) : '',
  )
  const [targetDurationSeconds, setTargetDurationSeconds] = useState(
    exercise?.target_duration_seconds != null ? String(exercise.target_duration_seconds) : '',
  )
  const [tracksWeight, setTracksWeight] = useState(exercise?.tracks_weight ?? false)
  const [bodyweightRatio, setBodyweightRatio] = useState(
    exercise?.bodyweight_ratio != null ? String(exercise.bodyweight_ratio) : '',
  )
  const [suitableForGameDay, setSuitableForGameDay] = useState(
    exercise?.suitable_for_game_day ?? false,
  )
  // Tri-state (not two booleans) since is_unilateral is nullable --
  // '' means "not yet classified", not "bilateral".
  const [isUnilateral, setIsUnilateral] = useState<'' | 'true' | 'false'>(
    exercise?.is_unilateral === true ? 'true' : exercise?.is_unilateral === false ? 'false' : '',
  )
  const [stimulusType, setStimulusType] = useState<StimulusType | ''>(
    exercise?.stimulus_type ?? '',
  )
  const [exerciseType, setExerciseType] = useState<ExerciseType | ''>(
    exercise?.exercise_type ?? '',
  )
  const [warmupStage, setWarmupStage] = useState<WarmupStage | ''>(
    exercise?.warmup_stage ?? '',
  )

  const [formError, setFormError] = useState<string | null>(null)
  const [isSaving, setIsSaving] = useState(false)

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (accessToken === null) {
      return
    }
    setFormError(null)

    if (name.trim() === '') {
      setFormError('Название обязательно.')
      return
    }
    const difficulty = Number(difficultyLevel)
    if (!Number.isInteger(difficulty) || difficulty < 1 || difficulty > 5) {
      setFormError('Сложность должна быть целым числом от 1 до 5.')
      return
    }
    const bodyweightRatioValue = parseOptionalFloat(bodyweightRatio)
    if (bodyweightRatioValue !== null && bodyweightRatioValue <= 0) {
      setFormError('Коэффициент веса тела должен быть больше 0.')
      return
    }
    if (phase === 'warmup' && warmupStage === '') {
      setFormError(
        'Укажите стадию разминки — без неё упражнение никогда не попадёт в собранную разминку.',
      )
      return
    }

    const payload: ExerciseWrite = {
      name: name.trim(),
      description: description.trim() === '' ? null : description.trim(),
      category,
      phase,
      difficulty_level: difficulty,
      // Only meaningful for phase=warmup -- forced null otherwise even if
      // some stale value is still sitting in state, so switching phase away
      // and back can't silently resurrect an unreviewed stage.
      warmup_stage: phase === 'warmup' && warmupStage !== '' ? warmupStage : null,
      video_source_type: videoSourceType.trim() === '' ? null : videoSourceType.trim(),
      video_source_id: videoSourceId.trim() === '' ? null : videoSourceId.trim(),
      target_sets: parseOptionalInt(targetSets),
      rep_range_min: parseOptionalInt(repRangeMin),
      rep_range_max: parseOptionalInt(repRangeMax),
      target_duration_seconds: parseOptionalInt(targetDurationSeconds),
      tracks_weight: tracksWeight,
      bodyweight_ratio: bodyweightRatioValue,
      suitable_for_game_day: suitableForGameDay,
      is_unilateral: isUnilateral === '' ? null : isUnilateral === 'true',
      stimulus_type: stimulusType === '' ? null : stimulusType,
      exercise_type: exerciseType === '' ? null : exerciseType,
    }

    setIsSaving(true)
    try {
      if (currentExercise === null) {
        const created = await exercisesApi.createExercise(payload, accessToken)
        setCurrentExercise(created)
        onSaved(created)
      } else {
        const updated = await exercisesApi.updateExercise(currentExercise.id, payload, accessToken)
        setCurrentExercise(updated)
        onSaved(updated)
        onClose()
      }
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : 'Не удалось сохранить упражнение.')
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <AdminModal
      title={currentExercise === null ? 'Новое упражнение' : `Редактирование: ${currentExercise.name}`}
      onClose={onClose}
    >
      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        <TextField
          label="Название"
          value={name}
          onChange={(event) => setName(event.target.value)}
          maxLength={255}
          required
        />
        <div className="flex flex-col gap-1.5">
          <label className="text-sm text-text-secondary" htmlFor="exercise-description">
            Описание
          </label>
          <textarea
            id="exercise-description"
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            rows={3}
            className="rounded border border-white/10 bg-dark-bg px-3 py-2 text-text-primary focus:border-accent-ice focus:outline-none"
          />
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <SelectField
            label="Категория"
            options={CATEGORY_OPTIONS}
            value={category}
            onChange={(event) => setCategory(event.target.value as ExerciseCategory)}
            required
          />
          <SelectField
            label="Фаза"
            options={PHASE_OPTIONS}
            value={phase}
            onChange={(event) => {
              const nextPhase = event.target.value as TrainingPhase
              setPhase(nextPhase)
              // Stage only means anything for a warmup exercise -- clear it
              // on the way out so it can't linger unseen and reappear if the
              // phase is switched back later with a stale, unreviewed value.
              if (nextPhase !== 'warmup') {
                setWarmupStage('')
              }
            }}
            required
          />
          <SelectField
            label="Stimulus type"
            options={STIMULUS_TYPE_OPTIONS}
            placeholder="Не задано"
            value={stimulusType}
            onChange={(event) => setStimulusType(event.target.value as StimulusType | '')}
          />
          <SelectField
            label="Exercise type"
            options={EXERCISE_TYPE_OPTIONS}
            placeholder="Не задано"
            value={exerciseType}
            onChange={(event) => setExerciseType(event.target.value as ExerciseType | '')}
          />
        </div>

        {phase === 'warmup' && (
          <div className="flex flex-col gap-1.5 rounded border border-accent-persimmon/30 bg-accent-persimmon/5 p-3">
            <SelectField
              label="Стадия разминки"
              options={WARMUP_STAGE_OPTIONS}
              placeholder="Не задано"
              value={warmupStage}
              onChange={(event) => setWarmupStage(event.target.value as WarmupStage | '')}
            />
            <p className="text-xs text-text-secondary">
              Комплекс разминки собирается по стадиям (миофасциальный релиз → подъём пульса →
              суставная мобильность → активация → динамическая). Без стадии это упражнение
              никогда не попадёт в собранную разминку — даже если всё остальное заполнено.
            </p>
          </div>
        )}

        <TextField
          label="Сложность (1-5)"
          type="number"
          numeric
          min={1}
          max={5}
          value={difficultyLevel}
          onChange={(event) => setDifficultyLevel(event.target.value)}
          required
        />

        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <TextField
            label="Подходы"
            type="number"
            numeric
            min={0}
            value={targetSets}
            onChange={(event) => setTargetSets(event.target.value)}
          />
          <TextField
            label="Повторы, мин"
            type="number"
            numeric
            min={0}
            value={repRangeMin}
            onChange={(event) => setRepRangeMin(event.target.value)}
          />
          <TextField
            label="Повторы, макс"
            type="number"
            numeric
            min={0}
            value={repRangeMax}
            onChange={(event) => setRepRangeMax(event.target.value)}
          />
          <TextField
            label="Длительность, сек"
            type="number"
            numeric
            min={0}
            value={targetDurationSeconds}
            onChange={(event) => setTargetDurationSeconds(event.target.value)}
          />
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <TextField
            label="Тип источника видео"
            value={videoSourceType}
            onChange={(event) => setVideoSourceType(event.target.value)}
            placeholder="youtube, vimeo..."
          />
          <TextField
            label="ID видео"
            value={videoSourceId}
            onChange={(event) => setVideoSourceId(event.target.value)}
          />
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <label className="flex items-center gap-2 text-sm text-text-primary">
            <input
              type="checkbox"
              checked={tracksWeight}
              onChange={(event) => setTracksWeight(event.target.checked)}
              className="h-4 w-4"
            />
            Учитывает рабочий вес
          </label>
          <TextField
            label="Коэффициент веса тела"
            type="number"
            numeric
            min={0}
            step="0.01"
            value={bodyweightRatio}
            onChange={(event) => setBodyweightRatio(event.target.value)}
            className="max-w-[180px]"
          />
        </div>

        <label className="flex items-center gap-2 text-sm text-text-primary">
          <input
            type="checkbox"
            checked={suitableForGameDay}
            onChange={(event) => setSuitableForGameDay(event.target.checked)}
            className="h-4 w-4"
          />
          Подходит для дня игры
        </label>

        <SelectField
          label="Нагрузка (squat/hip_hinge)"
          options={[
            { value: 'true', label: 'Унилатеральная (одна нога)' },
            { value: 'false', label: 'Билатеральная (обе ноги)' },
          ]}
          placeholder="Не задано"
          value={isUnilateral}
          onChange={(event) => setIsUnilateral(event.target.value as '' | 'true' | 'false')}
        />

        <FormError message={formError} />
        <Button type="submit" isLoading={isSaving} className="self-start">
          {currentExercise === null ? 'Создать' : 'Сохранить'}
        </Button>
      </form>

      {currentExercise !== null && accessToken !== null && (
        <ExerciseTargetStatsSection exerciseId={currentExercise.id} accessToken={accessToken} />
      )}
      {currentExercise !== null && accessToken !== null && (
        <ExerciseSkillTagsSection exerciseId={currentExercise.id} accessToken={accessToken} />
      )}
      {currentExercise !== null && accessToken !== null && (
        <ExerciseMovementPatternsSection exerciseId={currentExercise.id} accessToken={accessToken} />
      )}
      {currentExercise !== null && accessToken !== null && (
        <ExerciseMuscleGroupsSection exerciseId={currentExercise.id} accessToken={accessToken} />
      )}
      {currentExercise !== null && accessToken !== null && (
        <ExerciseEquipmentItemsSection exerciseId={currentExercise.id} accessToken={accessToken} />
      )}
    </AdminModal>
  )
}

function ExerciseTargetStatsSection({
  exerciseId,
  accessToken,
}: {
  exerciseId: string
  accessToken: string
}) {
  // Order matters here, unlike movement patterns: index 0 is the "primary"
  // stat ScheduleService._pick_main/suggest_party_exercises bucket on for
  // diversity (see ExerciseRead.target_stats). Modeled as a separate
  // required "primary" select + checkboxes for the rest, rather than a
  // plain multi-select, so that ordering survives the round trip without
  // building a full drag-reorder UI -- only the primary slot's identity is
  // functionally load-bearing, the relative order of the others isn't.
  const [primary, setPrimary] = useState<TargetStat | ''>('')
  const [additional, setAdditional] = useState<Set<TargetStat>>(new Set())
  const [loaded, setLoaded] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [isSaving, setIsSaving] = useState(false)

  useEffect(() => {
    let cancelled = false
    exercisesApi
      .listExerciseTargetStats(exerciseId, accessToken)
      .then((stats) => {
        if (cancelled) {
          return
        }
        setPrimary(stats[0] ?? '')
        setAdditional(new Set(stats.slice(1)))
        setLoaded(true)
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setLoadError(err instanceof ApiError ? err.message : 'Не удалось загрузить статы.')
        }
      })
    return () => {
      cancelled = true
    }
  }, [exerciseId, accessToken])

  function toggleAdditional(stat: TargetStat) {
    setAdditional((previous) => {
      const next = new Set(previous)
      if (next.has(stat)) {
        next.delete(stat)
      } else {
        next.add(stat)
      }
      return next
    })
  }

  async function handleSave() {
    if (primary === '') {
      setSaveError('Выберите основной стат.')
      return
    }
    setSaveError(null)
    setIsSaving(true)
    try {
      const saved = await exercisesApi.replaceExerciseTargetStats(
        exerciseId,
        [primary, ...Array.from(additional)],
        accessToken,
      )
      setPrimary(saved[0] ?? '')
      setAdditional(new Set(saved.slice(1)))
    } catch (err) {
      setSaveError(err instanceof ApiError ? err.message : 'Не удалось сохранить статы.')
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <div className="flex flex-col gap-3 border-t border-white/10 pt-6">
      <h3 className="text-sm font-medium text-text-secondary">Целевые статы</h3>
      <FormError message={loadError} />

      {loaded && (
        <>
          <SelectField
            label="Основной стат"
            options={TARGET_STAT_OPTIONS}
            placeholder="Не задано"
            value={primary}
            onChange={(event) => {
              const value = event.target.value as TargetStat | ''
              setPrimary(value)
              setAdditional((previous) => {
                if (value === '') {
                  return previous
                }
                const next = new Set(previous)
                next.delete(value)
                return next
              })
            }}
          />
          <div className="flex flex-col gap-1.5">
            <span className="text-sm text-text-secondary">Дополнительные статы</span>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
              {TARGET_STATS.filter((stat) => stat !== primary).map((stat) => (
                <label key={stat} className="flex items-center gap-2 text-sm text-text-primary">
                  <input
                    type="checkbox"
                    checked={additional.has(stat)}
                    onChange={() => toggleAdditional(stat)}
                    className="h-4 w-4"
                  />
                  {TARGET_STAT_LABELS[stat]}
                </label>
              ))}
            </div>
          </div>
        </>
      )}

      <Button
        type="button"
        variant="neutral"
        isLoading={isSaving}
        disabled={!loaded}
        onClick={handleSave}
        className="self-start"
      >
        Сохранить статы
      </Button>
      <FormError message={saveError} />
    </div>
  )
}

function ExerciseMovementPatternsSection({
  exerciseId,
  accessToken,
}: {
  exerciseId: string
  accessToken: string
}) {
  const [selected, setSelected] = useState<Set<MovementPattern> | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [isSaving, setIsSaving] = useState(false)

  useEffect(() => {
    let cancelled = false
    exercisesApi
      .listExerciseMovementPatterns(exerciseId, accessToken)
      .then((patterns) => {
        if (!cancelled) {
          setSelected(new Set(patterns))
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setLoadError(err instanceof ApiError ? err.message : 'Не удалось загрузить паттерны.')
        }
      })
    return () => {
      cancelled = true
    }
  }, [exerciseId, accessToken])

  function toggle(pattern: MovementPattern) {
    setSelected((previous) => {
      const next = new Set(previous ?? [])
      if (next.has(pattern)) {
        next.delete(pattern)
      } else {
        next.add(pattern)
      }
      return next
    })
  }

  async function handleSave() {
    if (selected === null) {
      return
    }
    setSaveError(null)
    setIsSaving(true)
    try {
      const saved = await exercisesApi.replaceExerciseMovementPatterns(
        exerciseId,
        Array.from(selected),
        accessToken,
      )
      setSelected(new Set(saved))
    } catch (err) {
      setSaveError(err instanceof ApiError ? err.message : 'Не удалось сохранить паттерны.')
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <div className="flex flex-col gap-3 border-t border-white/10 pt-6">
      <h3 className="text-sm font-medium text-text-secondary">Двигательные паттерны</h3>
      <FormError message={loadError} />

      {selected !== null && (
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          {MOVEMENT_PATTERNS.map((pattern) => (
            <label
              key={pattern}
              className="flex items-center gap-2 text-sm text-text-primary"
            >
              <input
                type="checkbox"
                checked={selected.has(pattern)}
                onChange={() => toggle(pattern)}
                className="h-4 w-4"
              />
              {MOVEMENT_PATTERN_LABELS[pattern]}
            </label>
          ))}
        </div>
      )}

      <Button
        type="button"
        variant="neutral"
        isLoading={isSaving}
        disabled={selected === null}
        onClick={handleSave}
        className="self-start"
      >
        Сохранить паттерны
      </Button>
      <FormError message={saveError} />
    </div>
  )
}

// Bare full-replace checkbox set, same shape as ExerciseMovementPatternsSection
// above -- AND semantics, not weighted (Stage 2.2): every checked item is
// required simultaneously for a non-gym user to see this exercise, see
// ExerciseRepository.list_for_assembly.
function ExerciseEquipmentItemsSection({
  exerciseId,
  accessToken,
}: {
  exerciseId: string
  accessToken: string
}) {
  const [selected, setSelected] = useState<Set<EquipmentItem> | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [isSaving, setIsSaving] = useState(false)

  useEffect(() => {
    let cancelled = false
    exercisesApi
      .listExerciseEquipmentItems(exerciseId, accessToken)
      .then((items) => {
        if (!cancelled) {
          setSelected(new Set(items))
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setLoadError(err instanceof ApiError ? err.message : 'Не удалось загрузить инвентарь.')
        }
      })
    return () => {
      cancelled = true
    }
  }, [exerciseId, accessToken])

  function toggle(item: EquipmentItem) {
    setSelected((previous) => {
      const next = new Set(previous ?? [])
      if (next.has(item)) {
        next.delete(item)
      } else {
        next.add(item)
      }
      return next
    })
  }

  async function handleSave() {
    if (selected === null) {
      return
    }
    setSaveError(null)
    setIsSaving(true)
    try {
      const saved = await exercisesApi.replaceExerciseEquipmentItems(
        exerciseId,
        Array.from(selected),
        accessToken,
      )
      setSelected(new Set(saved))
    } catch (err) {
      setSaveError(err instanceof ApiError ? err.message : 'Не удалось сохранить инвентарь.')
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <div className="flex flex-col gap-3 border-t border-white/10 pt-6">
      <h3 className="text-sm font-medium text-text-secondary">Инвентарь</h3>
      <p className="text-xs text-text-secondary">
        Ничего не выбрано — упражнение доступно без инвентаря. Выбранные предметы нужны
        одновременно (не любой один из них).
      </p>
      <FormError message={loadError} />

      {selected !== null && (
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          {EQUIPMENT_ITEM_OPTIONS.map(({ value, label }) => (
            <label key={value} className="flex items-center gap-2 text-sm text-text-primary">
              <input
                type="checkbox"
                checked={selected.has(value)}
                onChange={() => toggle(value)}
                className="h-4 w-4"
              />
              {label}
            </label>
          ))}
        </div>
      )}

      <Button
        type="button"
        variant="neutral"
        isLoading={isSaving}
        disabled={selected === null}
        onClick={handleSave}
        className="self-start"
      >
        Сохранить инвентарь
      </Button>
      <FormError message={saveError} />
    </div>
  )
}

// Same weighted-list shape as ExerciseTargetStatsSection's cousin,
// SkillStatWeight (see AdminSkillDetailPage's WEIGHT_SUM_EPSILON) -- a
// checkbox brings a group into the set at a default weight, its own number
// input then edits that weight. Full-replace on save, same as
// ExerciseMovementPatternsSection above, not per-row CRUD.
const MUSCLE_GROUP_WEIGHT_SUM_EPSILON = 1e-6

function ExerciseMuscleGroupsSection({
  exerciseId,
  accessToken,
}: {
  exerciseId: string
  accessToken: string
}) {
  const [weights, setWeights] = useState<Partial<Record<MuscleGroup, string>> | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [isSaving, setIsSaving] = useState(false)

  useEffect(() => {
    let cancelled = false
    exercisesApi
      .listExerciseMuscleGroups(exerciseId, accessToken)
      .then((groups) => {
        if (!cancelled) {
          const initial: Partial<Record<MuscleGroup, string>> = {}
          for (const g of groups) {
            initial[g.muscle_group] = String(g.weight)
          }
          setWeights(initial)
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setLoadError(err instanceof ApiError ? err.message : 'Не удалось загрузить мышечные группы.')
        }
      })
    return () => {
      cancelled = true
    }
  }, [exerciseId, accessToken])

  function toggle(group: MuscleGroup) {
    setWeights((previous) => {
      const next = { ...(previous ?? {}) }
      if (group in next) {
        delete next[group]
      } else {
        next[group] = '1'
      }
      return next
    })
  }

  function setWeight(group: MuscleGroup, value: string) {
    setWeights((previous) => ({ ...(previous ?? {}), [group]: value }))
  }

  const sum =
    weights === null
      ? 0
      : Object.values(weights).reduce((total, value) => total + (Number(value) || 0), 0)
  const sumExceeds = sum > 1.0 + MUSCLE_GROUP_WEIGHT_SUM_EPSILON

  async function handleSave() {
    if (weights === null) {
      return
    }
    setSaveError(null)
    setIsSaving(true)
    try {
      const payload = Object.entries(weights).map(([muscle_group, weight]) => ({
        muscle_group: muscle_group as MuscleGroup,
        weight: Number(weight) || 0,
      }))
      const saved = await exercisesApi.replaceExerciseMuscleGroups(exerciseId, payload, accessToken)
      const next: Partial<Record<MuscleGroup, string>> = {}
      for (const g of saved) {
        next[g.muscle_group] = String(g.weight)
      }
      setWeights(next)
    } catch (err) {
      setSaveError(err instanceof ApiError ? err.message : 'Не удалось сохранить мышечные группы.')
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <div className="flex flex-col gap-3 border-t border-white/10 pt-6">
      <h3 className="text-sm font-medium text-text-secondary">Мышечные группы</h3>
      <FormError message={loadError} />

      {weights !== null && (
        <div className="flex flex-col gap-2">
          {MUSCLE_GROUP_OPTIONS.map(({ value, label }) => (
            <div key={value} className="flex items-center gap-2">
              <label className="flex min-w-0 flex-1 items-center gap-2 text-sm text-text-primary">
                <input
                  type="checkbox"
                  checked={value in weights}
                  onChange={() => toggle(value)}
                  className="h-4 w-4 shrink-0"
                />
                {label}
              </label>
              {value in weights && (
                <input
                  type="number"
                  min="0"
                  max="1"
                  step="0.05"
                  value={weights[value] ?? ''}
                  onChange={(event) => setWeight(value, event.target.value)}
                  className="w-20 shrink-0 rounded border border-white/10 bg-dark-bg px-2 py-1 font-mono text-sm text-text-primary focus:border-accent-ice focus:outline-none"
                />
              )}
            </div>
          ))}
          <p className={`font-mono text-xs ${sumExceeds ? 'text-accent-persimmon' : 'text-text-secondary'}`}>
            Сумма весов: {sum.toFixed(2)}
            {sumExceeds && ' — превышает 1.0'}
          </p>
        </div>
      )}

      <Button
        type="button"
        variant="neutral"
        isLoading={isSaving}
        disabled={weights === null || sumExceeds}
        onClick={handleSave}
        className="self-start"
      >
        Сохранить мышечные группы
      </Button>
      <FormError message={saveError} />
    </div>
  )
}

function ExerciseSkillTagsSection({
  exerciseId,
  accessToken,
}: {
  exerciseId: string
  accessToken: string
}) {
  const [tags, setTags] = useState<SkillTagRead[] | null>(null)
  const [allSkills, setAllSkills] = useState<SkillOption[] | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)

  const [newSkillId, setNewSkillId] = useState('')
  const [newTransferNote, setNewTransferNote] = useState('')
  const [addError, setAddError] = useState<string | null>(null)
  const [isAdding, setIsAdding] = useState(false)

  useEffect(() => {
    let cancelled = false
    Promise.all([
      skillsApi.listSkillsAdmin(accessToken),
      exercisesApi.listExerciseSkillTags(exerciseId, accessToken),
    ])
      .then(([skills, exerciseTags]) => {
        if (cancelled) {
          return
        }
        setAllSkills(skills)
        setTags(exerciseTags)
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setLoadError(err instanceof ApiError ? err.message : 'Не удалось загрузить навыки.')
        }
      })
    return () => {
      cancelled = true
    }
  }, [exerciseId, accessToken])

  const skillNameById = new Map((allSkills ?? []).map((skill) => [skill.id, skill.name]))
  const taggedSkillIds = new Set((tags ?? []).map((tag) => tag.skill_id))
  const availableSkills = (allSkills ?? []).filter((skill) => !taggedSkillIds.has(skill.id))

  async function handleAddTag(event: FormEvent) {
    event.preventDefault()
    setAddError(null)
    if (newSkillId === '') {
      setAddError('Выберите навык.')
      return
    }
    if (newTransferNote.trim() === '') {
      setAddError('Укажите transfer_note.')
      return
    }
    setIsAdding(true)
    try {
      const created = await skillsApi.createSkillTag(
        newSkillId,
        { exercise_id: exerciseId, transfer_note: newTransferNote.trim() },
        accessToken,
      )
      setTags((previous) => [...(previous ?? []), created])
      setNewSkillId('')
      setNewTransferNote('')
    } catch (err) {
      setAddError(err instanceof ApiError ? err.message : 'Не удалось добавить связь.')
    } finally {
      setIsAdding(false)
    }
  }

  async function handleDeleteTag(tag: SkillTagRead) {
    try {
      await skillsApi.deleteSkillTag(tag.skill_id, tag.id, accessToken)
      setTags((previous) => previous?.filter((item) => item.id !== tag.id) ?? previous)
    } catch (err) {
      window.alert(err instanceof ApiError ? err.message : 'Не удалось удалить связь.')
    }
  }

  return (
    <div className="flex flex-col gap-3 border-t border-white/10 pt-6">
      <h3 className="text-sm font-medium text-text-secondary">Связанные навыки</h3>
      <FormError message={loadError} />

      {tags !== null && tags.length === 0 && (
        <p className="text-sm text-text-secondary">Пока не привязано ни к одному навыку.</p>
      )}
      {tags !== null && tags.length > 0 && (
        <ul className="flex flex-col gap-2">
          {tags.map((tag) => (
            <li
              key={tag.id}
              className="flex items-start justify-between gap-3 rounded border border-white/10 bg-dark-bg px-3 py-2"
            >
              <div>
                <p className="text-sm text-text-primary">
                  {skillNameById.get(tag.skill_id) ?? tag.skill_id}
                </p>
                <p className="text-xs text-text-secondary">{tag.transfer_note}</p>
              </div>
              <button
                type="button"
                onClick={() => handleDeleteTag(tag)}
                className="shrink-0 text-xs text-accent-persimmon hover:underline"
              >
                Удалить
              </button>
            </li>
          ))}
        </ul>
      )}

      {allSkills !== null && (
        <form onSubmit={handleAddTag} className="flex flex-col gap-2 sm:flex-row sm:items-end">
          <SelectField
            label="Навык"
            options={availableSkills.map((skill) => ({ value: skill.id, label: skill.name }))}
            placeholder="Выберите навык"
            value={newSkillId}
            onChange={(event) => setNewSkillId(event.target.value)}
            className="sm:w-48"
          />
          <TextField
            label="Transfer note"
            value={newTransferNote}
            onChange={(event) => setNewTransferNote(event.target.value)}
            className="flex-1"
          />
          <Button type="submit" variant="neutral" isLoading={isAdding}>
            Добавить
          </Button>
        </form>
      )}
      <FormError message={addError} />
    </div>
  )
}
