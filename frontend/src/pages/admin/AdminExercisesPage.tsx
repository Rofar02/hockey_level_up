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
  EQUIPMENT_TYPES,
  EQUIPMENT_TYPE_LABELS,
  EXERCISE_CATEGORIES,
  EXERCISE_CATEGORY_LABELS,
  TARGET_STATS,
  TARGET_STAT_LABELS,
} from '../../types/exercise'
import type { EquipmentType, ExerciseCategory, ExerciseRead, ExerciseWrite, TargetStat } from '../../types/exercise'
import { TRAINING_PHASES } from '../../types/schedule'
import type { TrainingPhase } from '../../types/schedule'
import type { SkillOption, SkillTagRead } from '../../types/skill'

const PHASE_LABELS: Record<TrainingPhase, string> = {
  warmup: 'Разминка',
  main: 'Основная часть',
  cooldown: 'Заминка',
}

const CATEGORY_OPTIONS = EXERCISE_CATEGORIES.map((value) => ({
  value,
  label: EXERCISE_CATEGORY_LABELS[value],
}))
const PHASE_OPTIONS = TRAINING_PHASES.map((value) => ({ value, label: PHASE_LABELS[value] }))
const TARGET_STAT_OPTIONS = TARGET_STATS.map((value) => ({ value, label: TARGET_STAT_LABELS[value] }))
const EQUIPMENT_OPTIONS = EQUIPMENT_TYPES.map((value) => ({
  value,
  label: EQUIPMENT_TYPE_LABELS[value],
}))

export function AdminExercisesPage() {
  const { accessToken } = useAuth()

  const [category, setCategory] = useState<ExerciseCategory | ''>('')
  const [phase, setPhase] = useState<TrainingPhase | ''>('')
  const [targetStat, setTargetStat] = useState<TargetStat | ''>('')

  const [exercises, setExercises] = useState<ExerciseRead[] | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(true)

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
        </div>
        <Button type="button" onClick={openCreateForm}>
          Добавить упражнение
        </Button>
      </div>

      <FormError message={loadError} />
      {isLoading && <p className="text-sm text-text-secondary">Загрузка...</p>}

      {!isLoading && exercises !== null && (
        <div className="overflow-x-auto rounded-md border border-white/10">
          <table className="w-full min-w-[720px] border-collapse text-sm">
            <thead>
              <tr className="border-b border-white/10 bg-white/5 text-left text-text-secondary">
                <th className="px-3 py-2 font-medium">Название</th>
                <th className="px-3 py-2 font-medium">Категория</th>
                <th className="px-3 py-2 font-medium">Фаза</th>
                <th className="px-3 py-2 font-medium">Характеристика</th>
                <th className="px-3 py-2 font-medium">Сложность</th>
                <th className="px-3 py-2 font-medium">Инвентарь</th>
                <th className="px-3 py-2 font-medium" />
              </tr>
            </thead>
            <tbody>
              {exercises.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-3 py-6 text-center text-text-secondary">
                    Ничего не найдено.
                  </td>
                </tr>
              )}
              {exercises.map((exercise) => (
                <tr key={exercise.id} className="border-b border-white/5 hover:bg-white/5">
                  <td className="px-3 py-2 text-text-primary">{exercise.name}</td>
                  <td className="px-3 py-2 text-text-secondary">
                    {EXERCISE_CATEGORY_LABELS[exercise.category]}
                  </td>
                  <td className="px-3 py-2 text-text-secondary">{PHASE_LABELS[exercise.phase]}</td>
                  <td className="px-3 py-2 text-text-secondary">
                    {TARGET_STAT_LABELS[exercise.target_stat]}
                  </td>
                  <td className="px-3 py-2 font-mono text-text-secondary">{exercise.difficulty_level}</td>
                  <td className="px-3 py-2 text-text-secondary">
                    {EQUIPMENT_TYPE_LABELS[exercise.equipment_type]}
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
  const [targetStat, setTargetStat] = useState<TargetStat>(exercise?.target_stat ?? 'strength')
  const [difficultyLevel, setDifficultyLevel] = useState(String(exercise?.difficulty_level ?? 1))
  const [equipmentType, setEquipmentType] = useState<EquipmentType>(
    exercise?.equipment_type ?? 'bodyweight',
  )
  const [videoSourceType, setVideoSourceType] = useState(exercise?.video_source_type ?? '')
  const [videoSourceId, setVideoSourceId] = useState(exercise?.video_source_id ?? '')
  const [targetSets, setTargetSets] = useState(
    exercise?.target_sets != null ? String(exercise.target_sets) : '',
  )
  const [targetReps, setTargetReps] = useState(
    exercise?.target_reps != null ? String(exercise.target_reps) : '',
  )
  const [targetDurationSeconds, setTargetDurationSeconds] = useState(
    exercise?.target_duration_seconds != null ? String(exercise.target_duration_seconds) : '',
  )
  const [tracksWeight, setTracksWeight] = useState(exercise?.tracks_weight ?? false)
  const [bodyweightRatio, setBodyweightRatio] = useState(
    exercise?.bodyweight_ratio != null ? String(exercise.bodyweight_ratio) : '',
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

    const payload: ExerciseWrite = {
      name: name.trim(),
      description: description.trim() === '' ? null : description.trim(),
      category,
      phase,
      target_stat: targetStat,
      difficulty_level: difficulty,
      equipment_type: equipmentType,
      video_source_type: videoSourceType.trim() === '' ? null : videoSourceType.trim(),
      video_source_id: videoSourceId.trim() === '' ? null : videoSourceId.trim(),
      target_sets: parseOptionalInt(targetSets),
      target_reps: parseOptionalInt(targetReps),
      target_duration_seconds: parseOptionalInt(targetDurationSeconds),
      tracks_weight: tracksWeight,
      bodyweight_ratio: bodyweightRatioValue,
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

        <div className="grid grid-cols-2 gap-4">
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
            onChange={(event) => setPhase(event.target.value as TrainingPhase)}
            required
          />
          <SelectField
            label="Характеристика"
            options={TARGET_STAT_OPTIONS}
            value={targetStat}
            onChange={(event) => setTargetStat(event.target.value as TargetStat)}
            required
          />
          <SelectField
            label="Инвентарь"
            options={EQUIPMENT_OPTIONS}
            value={equipmentType}
            onChange={(event) => setEquipmentType(event.target.value as EquipmentType)}
            required
          />
        </div>

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

        <div className="grid grid-cols-3 gap-4">
          <TextField
            label="Подходы"
            type="number"
            numeric
            min={0}
            value={targetSets}
            onChange={(event) => setTargetSets(event.target.value)}
          />
          <TextField
            label="Повторения"
            type="number"
            numeric
            min={0}
            value={targetReps}
            onChange={(event) => setTargetReps(event.target.value)}
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

        <div className="grid grid-cols-2 gap-4">
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

        <div className="flex items-center gap-3">
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

        <FormError message={formError} />
        <Button type="submit" isLoading={isSaving} className="self-start">
          {currentExercise === null ? 'Создать' : 'Сохранить'}
        </Button>
      </form>

      {currentExercise !== null && accessToken !== null && (
        <ExerciseSkillTagsSection exerciseId={currentExercise.id} accessToken={accessToken} />
      )}
    </AdminModal>
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
