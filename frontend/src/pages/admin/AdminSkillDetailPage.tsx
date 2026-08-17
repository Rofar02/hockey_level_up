import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { useParams } from 'react-router-dom'
import { AdminLayout } from '../../components/admin/AdminLayout'
import { BackLink } from '../../components/ui/BackLink'
import { Button } from '../../components/ui/Button'
import { FormError } from '../../components/ui/FormError'
import { SelectField } from '../../components/ui/SelectField'
import { TextField } from '../../components/ui/TextField'
import * as skillsApi from '../../api/skills'
import { ApiError } from '../../api/client'
import { useAuth } from '../../hooks/useAuth'
import { TARGET_STATS, TARGET_STAT_LABELS } from '../../types/exercise'
import type { TargetStat } from '../../types/exercise'
import type { SkillMilestoneRead, SkillOption, SkillStatWeightRead } from '../../types/skill'

const WEIGHT_SUM_EPSILON = 1e-6

export function AdminSkillDetailPage() {
  const { skillId } = useParams<{ skillId: string }>()
  const { accessToken } = useAuth()

  const [skill, setSkill] = useState<SkillOption | null>(null)
  const [weights, setWeights] = useState<SkillStatWeightRead[] | null>(null)
  const [milestones, setMilestones] = useState<SkillMilestoneRead[] | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    if (accessToken === null || skillId === undefined) {
      return
    }
    let cancelled = false
    Promise.all([
      skillsApi.getSkillAdmin(skillId, accessToken),
      skillsApi.listStatWeights(skillId, accessToken),
      skillsApi.listMilestones(skillId, accessToken),
    ])
      .then(([skillResult, weightsResult, milestonesResult]) => {
        if (cancelled) {
          return
        }
        setSkill(skillResult)
        setWeights(weightsResult)
        setMilestones(milestonesResult)
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setLoadError(err instanceof ApiError ? err.message : 'Не удалось загрузить навык.')
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
  }, [accessToken, skillId])

  if (skillId === undefined) {
    return null
  }

  return (
    <AdminLayout title="Редактирование навыка">
      <BackLink to="/admin/skills" />
      <FormError message={loadError} />
      {isLoading && <p className="mt-4 text-sm text-text-secondary">Загрузка...</p>}

      {!isLoading && skill !== null && accessToken !== null && (
        <div className="mt-4 flex flex-col gap-8">
          <SkillNameSection skill={skill} accessToken={accessToken} onSaved={setSkill} />
          <StatWeightsSection
            skillId={skillId}
            weights={weights ?? []}
            accessToken={accessToken}
            onChange={setWeights}
          />
          <MilestonesSection
            skillId={skillId}
            milestones={milestones ?? []}
            accessToken={accessToken}
            onChange={setMilestones}
          />
        </div>
      )}
    </AdminLayout>
  )
}

function SkillNameSection({
  skill,
  accessToken,
  onSaved,
}: {
  skill: SkillOption
  accessToken: string
  onSaved: (skill: SkillOption) => void
}) {
  const [name, setName] = useState(skill.name)
  const [requiredLevel, setRequiredLevel] = useState(String(skill.required_level))
  const [error, setError] = useState<string | null>(null)
  const [isSaving, setIsSaving] = useState(false)

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    if (name.trim() === '') {
      setError('Название обязательно.')
      return
    }
    const requiredLevelValue = Number(requiredLevel)
    if (!Number.isInteger(requiredLevelValue) || requiredLevelValue < 1) {
      setError('Уровень должен быть целым числом от 1.')
      return
    }
    if (name.trim() === skill.name && requiredLevelValue === skill.required_level) {
      return
    }
    setIsSaving(true)
    try {
      const updated = await skillsApi.updateSkill(
        skill.id,
        { name: name.trim(), required_level: requiredLevelValue },
        accessToken,
      )
      onSaved(updated)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Не удалось сохранить название.')
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-sm font-medium text-text-secondary">Название и требуемый уровень</h2>
      <form onSubmit={handleSubmit} className="flex flex-col gap-2 sm:flex-row sm:items-end">
        <TextField
          label="Название навыка"
          value={name}
          onChange={(event) => setName(event.target.value)}
          maxLength={255}
          className="sm:w-64"
        />
        <TextField
          label="Требуемый уровень"
          type="number"
          numeric
          min={1}
          value={requiredLevel}
          onChange={(event) => setRequiredLevel(event.target.value)}
          className="sm:w-40"
        />
        <Button type="submit" variant="neutral" isLoading={isSaving}>
          Сохранить
        </Button>
      </form>
      <FormError message={error} />
    </section>
  )
}

function StatWeightsSection({
  skillId,
  weights,
  accessToken,
  onChange,
}: {
  skillId: string
  weights: SkillStatWeightRead[]
  accessToken: string
  onChange: (weights: SkillStatWeightRead[]) => void
}) {
  const usedStats = new Set(weights.map((weight) => weight.stat_type))
  const availableStats = TARGET_STATS.filter((stat) => !usedStats.has(stat))

  const [newStat, setNewStat] = useState<TargetStat | ''>('')
  const [newWeight, setNewWeight] = useState('')
  const [addError, setAddError] = useState<string | null>(null)
  const [isAdding, setIsAdding] = useState(false)

  const sum = weights.reduce((total, weight) => total + weight.weight, 0)
  const sumExceeds = sum > 1.0 + WEIGHT_SUM_EPSILON

  async function handleAdd(event: FormEvent) {
    event.preventDefault()
    setAddError(null)
    if (newStat === '') {
      setAddError('Выберите характеристику.')
      return
    }
    const weightValue = Number(newWeight)
    if (Number.isNaN(weightValue) || weightValue < 0 || weightValue > 1) {
      setAddError('Вес должен быть числом от 0.0 до 1.0.')
      return
    }
    setIsAdding(true)
    try {
      const created = await skillsApi.createStatWeight(
        skillId,
        { stat_type: newStat, weight: weightValue },
        accessToken,
      )
      onChange([...weights, created])
      setNewStat('')
      setNewWeight('')
    } catch (err) {
      setAddError(err instanceof ApiError ? err.message : 'Не удалось добавить вес.')
    } finally {
      setIsAdding(false)
    }
  }

  async function handleUpdate(weight: SkillStatWeightRead, newValue: number): Promise<string | null> {
    try {
      const updated = await skillsApi.updateStatWeight(
        skillId,
        weight.id,
        { stat_type: weight.stat_type, weight: newValue },
        accessToken,
      )
      onChange(weights.map((item) => (item.id === updated.id ? updated : item)))
      return null
    } catch (err) {
      return err instanceof ApiError ? err.message : 'Не удалось сохранить вес.'
    }
  }

  async function handleDelete(weight: SkillStatWeightRead) {
    if (!window.confirm(`Удалить вес «${TARGET_STAT_LABELS[weight.stat_type]}»?`)) {
      return
    }
    try {
      await skillsApi.deleteStatWeight(skillId, weight.id, accessToken)
      onChange(weights.filter((item) => item.id !== weight.id))
    } catch (err) {
      window.alert(err instanceof ApiError ? err.message : 'Не удалось удалить вес.')
    }
  }

  return (
    <section className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-medium text-text-secondary">Веса характеристик</h2>
        <p className={`font-mono text-sm ${sumExceeds ? 'text-accent-persimmon' : 'text-accent-ice'}`}>
          Сумма: {sum.toFixed(2)}
          {sumExceeds && ' — превышает 1.0'}
        </p>
      </div>

      {weights.length === 0 && <p className="text-sm text-text-secondary">Веса ещё не заданы.</p>}
      {weights.length > 0 && (
        <>
          <div className="hidden overflow-hidden rounded-md border border-white/10 md:block">
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="border-b border-white/10 bg-white/5 text-left text-text-secondary">
                  <th className="px-3 py-2 font-medium">Характеристика</th>
                  <th className="px-3 py-2 font-medium">Вес</th>
                  <th className="px-3 py-2 font-medium" />
                </tr>
              </thead>
              <tbody>
                {weights.map((weight) => (
                  <StatWeightRow
                    key={weight.id}
                    weight={weight}
                    onSave={handleUpdate}
                    onDelete={() => handleDelete(weight)}
                  />
                ))}
              </tbody>
            </table>
          </div>

          <div className="flex flex-col gap-3 md:hidden">
            {weights.map((weight) => (
              <StatWeightCard
                key={weight.id}
                weight={weight}
                onSave={handleUpdate}
                onDelete={() => handleDelete(weight)}
              />
            ))}
          </div>
        </>
      )}

      {availableStats.length > 0 && (
        <form onSubmit={handleAdd} className="flex flex-col gap-2 sm:flex-row sm:items-end">
          <SelectField
            label="Характеристика"
            options={availableStats.map((stat) => ({ value: stat, label: TARGET_STAT_LABELS[stat] }))}
            placeholder="Выберите"
            value={newStat}
            onChange={(event) => setNewStat(event.target.value as TargetStat)}
          />
          <TextField
            label="Вес (0.0-1.0)"
            type="number"
            numeric
            min={0}
            max={1}
            step="0.01"
            value={newWeight}
            onChange={(event) => setNewWeight(event.target.value)}
            className="max-w-[140px]"
          />
          <Button type="submit" variant="neutral" isLoading={isAdding}>
            Добавить
          </Button>
        </form>
      )}
      <FormError message={addError} />
    </section>
  )
}

// Shared by the table row (desktop/tablet) and card (mobile) presentations
// below -- both need the same dirty/save/error state, just laid out
// differently, so the stateful bits live here once rather than being
// copy-pasted between a <tr> and a <div>.
function useStatWeightEditor(
  weight: SkillStatWeightRead,
  onSave: (weight: SkillStatWeightRead, newValue: number) => Promise<string | null>,
) {
  const [value, setValue] = useState(String(weight.weight))
  const [error, setError] = useState<string | null>(null)
  const [isSaving, setIsSaving] = useState(false)
  const isDirty = value !== String(weight.weight)

  async function handleSave() {
    setError(null)
    const parsed = Number(value)
    if (Number.isNaN(parsed) || parsed < 0 || parsed > 1) {
      setError('Вес должен быть числом от 0.0 до 1.0.')
      return
    }
    setIsSaving(true)
    const failureMessage = await onSave(weight, parsed)
    setIsSaving(false)
    if (failureMessage !== null) {
      setError(failureMessage)
    }
  }

  return { value, setValue, error, isSaving, isDirty, handleSave }
}

function StatWeightRow({
  weight,
  onSave,
  onDelete,
}: {
  weight: SkillStatWeightRead
  onSave: (weight: SkillStatWeightRead, newValue: number) => Promise<string | null>
  onDelete: () => void
}) {
  const { value, setValue, error, isSaving, isDirty, handleSave } = useStatWeightEditor(weight, onSave)

  return (
    <tr className="border-b border-white/5 hover:bg-white/5">
      <td className="px-3 py-2 text-text-primary">{TARGET_STAT_LABELS[weight.stat_type]}</td>
      <td className="px-3 py-2">
        <div className="flex flex-col gap-1">
          <input
            type="number"
            min={0}
            max={1}
            step="0.01"
            value={value}
            onChange={(event) => setValue(event.target.value)}
            className="w-24 rounded border border-white/10 bg-dark-bg px-2 py-1 font-mono text-text-primary focus:border-accent-ice focus:outline-none"
          />
          {error !== null && <span className="text-xs text-accent-persimmon">{error}</span>}
        </div>
      </td>
      <td className="px-3 py-2 text-right">
        <div className="flex justify-end gap-3">
          {isDirty && (
            <button
              type="button"
              onClick={handleSave}
              disabled={isSaving}
              className="text-accent-ice hover:underline disabled:opacity-50"
            >
              Сохранить
            </button>
          )}
          <button type="button" onClick={onDelete} className="text-accent-persimmon hover:underline">
            Удалить
          </button>
        </div>
      </td>
    </tr>
  )
}

function StatWeightCard({
  weight,
  onSave,
  onDelete,
}: {
  weight: SkillStatWeightRead
  onSave: (weight: SkillStatWeightRead, newValue: number) => Promise<string | null>
  onDelete: () => void
}) {
  const { value, setValue, error, isSaving, isDirty, handleSave } = useStatWeightEditor(weight, onSave)

  return (
    <div className="rounded-md border border-white/10 bg-dark-card p-3">
      <p className="text-sm font-medium text-text-primary">{TARGET_STAT_LABELS[weight.stat_type]}</p>
      <div className="mt-2 flex flex-col gap-1">
        <input
          type="number"
          min={0}
          max={1}
          step="0.01"
          value={value}
          onChange={(event) => setValue(event.target.value)}
          className="w-24 rounded border border-white/10 bg-dark-bg px-2 py-1 font-mono text-text-primary focus:border-accent-ice focus:outline-none"
        />
        {error !== null && <span className="text-xs text-accent-persimmon">{error}</span>}
      </div>
      <div className="mt-2 flex gap-4 text-sm">
        {isDirty && (
          <button
            type="button"
            onClick={handleSave}
            disabled={isSaving}
            className="text-accent-ice hover:underline disabled:opacity-50"
          >
            Сохранить
          </button>
        )}
        <button type="button" onClick={onDelete} className="text-accent-persimmon hover:underline">
          Удалить
        </button>
      </div>
    </div>
  )
}

const EMPTY_MILESTONE_FORM = { threshold: '', title: '', description: '' }

function MilestonesSection({
  skillId,
  milestones,
  accessToken,
  onChange,
}: {
  skillId: string
  milestones: SkillMilestoneRead[]
  accessToken: string
  onChange: (milestones: SkillMilestoneRead[]) => void
}) {
  const [editingId, setEditingId] = useState<string | null>(null)
  const [form, setForm] = useState(EMPTY_MILESTONE_FORM)
  const [error, setError] = useState<string | null>(null)
  const [isSaving, setIsSaving] = useState(false)

  function startCreate() {
    setEditingId(null)
    setForm(EMPTY_MILESTONE_FORM)
    setError(null)
  }

  function startEdit(milestone: SkillMilestoneRead) {
    setEditingId(milestone.id)
    setForm({
      threshold: String(milestone.threshold),
      title: milestone.title,
      description: milestone.description,
    })
    setError(null)
  }

  async function handleDelete(milestone: SkillMilestoneRead) {
    if (!window.confirm(`Удалить порог «${milestone.title}»?`)) {
      return
    }
    try {
      await skillsApi.deleteMilestone(skillId, milestone.id, accessToken)
      onChange(milestones.filter((item) => item.id !== milestone.id))
      if (editingId === milestone.id) {
        startCreate()
      }
    } catch (err) {
      window.alert(err instanceof ApiError ? err.message : 'Не удалось удалить порог.')
    }
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setError(null)

    const threshold = Number(form.threshold)
    if (!Number.isInteger(threshold) || threshold < 0 || threshold > 100) {
      setError('Порог должен быть целым числом от 0 до 100.')
      return
    }
    if (form.title.trim() === '') {
      setError('Название обязательно.')
      return
    }
    if (form.description.trim() === '') {
      setError('Описание обязательно.')
      return
    }

    const payload = { threshold, title: form.title.trim(), description: form.description.trim() }

    setIsSaving(true)
    try {
      if (editingId === null) {
        const created = await skillsApi.createMilestone(skillId, payload, accessToken)
        onChange([...milestones, created].sort((a, b) => a.threshold - b.threshold))
      } else {
        const updated = await skillsApi.updateMilestone(skillId, editingId, payload, accessToken)
        onChange(
          milestones
            .map((item) => (item.id === updated.id ? updated : item))
            .sort((a, b) => a.threshold - b.threshold),
        )
      }
      startCreate()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Не удалось сохранить порог.')
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-sm font-medium text-text-secondary">Пороги</h2>

      {milestones.length === 0 && <p className="text-sm text-text-secondary">Пороги ещё не заданы.</p>}
      {milestones.length > 0 && (
        <>
          <div className="hidden overflow-hidden rounded-md border border-white/10 md:block">
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="border-b border-white/10 bg-white/5 text-left text-text-secondary">
                  <th className="px-3 py-2 font-medium">Порог</th>
                  <th className="px-3 py-2 font-medium">Название</th>
                  <th className="px-3 py-2 font-medium">Описание</th>
                  <th className="px-3 py-2 font-medium" />
                </tr>
              </thead>
              <tbody>
                {milestones.map((milestone) => (
                  <tr key={milestone.id} className="border-b border-white/5 hover:bg-white/5">
                    <td className="px-3 py-2 font-mono text-text-primary">{milestone.threshold}</td>
                    <td className="px-3 py-2 text-text-primary">{milestone.title}</td>
                    <td
                      className="max-w-xs truncate px-3 py-2 text-text-secondary"
                      title={milestone.description}
                    >
                      {milestone.description}
                    </td>
                    <td className="px-3 py-2 text-right">
                      <div className="flex justify-end gap-3">
                        <button
                          type="button"
                          onClick={() => startEdit(milestone)}
                          className="text-accent-ice hover:underline"
                        >
                          Изменить
                        </button>
                        <button
                          type="button"
                          onClick={() => handleDelete(milestone)}
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
            {milestones.map((milestone) => (
              <div key={milestone.id} className="rounded-md border border-white/10 bg-dark-card p-3">
                <p className="font-mono text-xs text-text-secondary">Порог: {milestone.threshold}</p>
                <p className="mt-1 text-sm font-medium text-text-primary">{milestone.title}</p>
                <p className="mt-1 text-sm text-text-secondary">{milestone.description}</p>
                <div className="mt-2 flex gap-4 text-sm">
                  <button
                    type="button"
                    onClick={() => startEdit(milestone)}
                    className="text-accent-ice hover:underline"
                  >
                    Изменить
                  </button>
                  <button
                    type="button"
                    onClick={() => handleDelete(milestone)}
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

      <form onSubmit={handleSubmit} className="flex flex-col gap-3 rounded-md border border-white/10 p-4">
        <p className="text-sm font-medium text-text-secondary">
          {editingId === null ? 'Новый порог' : 'Редактирование порога'}
        </p>
        <div className="grid grid-cols-2 gap-4">
          <TextField
            label="Порог (0-100)"
            type="number"
            numeric
            min={0}
            max={100}
            value={form.threshold}
            onChange={(event) => setForm((previous) => ({ ...previous, threshold: event.target.value }))}
            required
          />
          <TextField
            label="Название"
            value={form.title}
            onChange={(event) => setForm((previous) => ({ ...previous, title: event.target.value }))}
            maxLength={255}
            required
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <label className="text-sm text-text-secondary" htmlFor="milestone-description">
            Описание
          </label>
          <textarea
            id="milestone-description"
            value={form.description}
            onChange={(event) => setForm((previous) => ({ ...previous, description: event.target.value }))}
            rows={3}
            className="rounded border border-white/10 bg-dark-bg px-3 py-2 text-text-primary focus:border-accent-ice focus:outline-none"
          />
        </div>
        <FormError message={error} />
        <div className="flex gap-3">
          <Button type="submit" variant="neutral" isLoading={isSaving} className="self-start">
            {editingId === null ? 'Добавить' : 'Сохранить'}
          </Button>
          {editingId !== null && (
            <Button type="button" variant="neutral" onClick={startCreate} className="self-start">
              Отмена
            </Button>
          )}
        </div>
      </form>
    </section>
  )
}
