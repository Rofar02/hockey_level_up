import { useEffect, useState } from 'react'
import { Button } from '../../components/ui/Button'
import { FormError } from '../../components/ui/FormError'
import * as exercisesApi from '../../api/exercises'
import * as usersApi from '../../api/users'
import { ApiError } from '../../api/client'
import { useAuth } from '../../hooks/useAuth'
import { EQUIPMENT_ITEMS, EQUIPMENT_ITEM_LABELS } from '../../types/exercise'
import type { EquipmentItem, ExerciseEquipmentRequirement } from '../../types/exercise'
import { TYPICAL_HOME_PRESET, countAvailableExercises } from '../../utils/equipmentAvailability'

// Stage 2.3 (2026-08-20 planning session): one screen, not two steps --
// the "Зал"/"типичный дом" presets just pre-fill the same checkbox grid
// (and the has_gym_access toggle) rather than leading anywhere separate,
// a live counter tracks every tap, and the whole step is skippable
// without blocking registration -- the defaults (has_gym_access=false, no
// owned items) already are "bodyweight only", so skipping is just "don't
// call the API", not a special-cased empty state.
export function EquipmentStep({ onNext }: { onNext: () => void }) {
  const { accessToken } = useAuth()
  const [hasGymAccess, setHasGymAccess] = useState(false)
  const [selectedItems, setSelectedItems] = useState<Set<EquipmentItem>>(new Set())
  const [requirements, setRequirements] = useState<ExerciseEquipmentRequirement[] | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (accessToken === null) {
      return
    }
    let cancelled = false
    exercisesApi
      .listExerciseEquipmentRequirements(accessToken)
      .then((result) => {
        if (!cancelled) {
          setRequirements(result)
        }
      })
      .catch(() => {
        // Best-effort -- the grid/toggle still work without a live
        // counter, worst case it just never appears.
      })
    return () => {
      cancelled = true
    }
  }, [accessToken])

  function toggleItem(item: EquipmentItem) {
    setSelectedItems((previous) => {
      const next = new Set(previous)
      if (next.has(item)) {
        next.delete(item)
      } else {
        next.add(item)
      }
      return next
    })
  }

  function applyGymPreset() {
    setHasGymAccess(true)
  }

  function applyHomePreset() {
    setHasGymAccess(false)
    setSelectedItems(new Set(TYPICAL_HOME_PRESET))
  }

  async function handleNext() {
    if (accessToken === null) {
      return
    }
    setError(null)
    setIsSubmitting(true)
    try {
      await usersApi.updateProfile({ has_gym_access: hasGymAccess }, accessToken)
      if (!hasGymAccess && selectedItems.size > 0) {
        await usersApi.replaceMyEquipmentItems(Array.from(selectedItems), accessToken)
      }
      onNext()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Не удалось сохранить выбор. Попробуйте ещё раз.')
    } finally {
      setIsSubmitting(false)
    }
  }

  const available = requirements === null ? null : countAvailableExercises(requirements, hasGymAccess, selectedItems)

  return (
    <div className="flex flex-col gap-6">
      <h2 className="text-lg font-semibold">Какое оборудование у вас есть?</h2>

      <div className="flex flex-wrap gap-3">
        <Button type="button" variant="neutral" onClick={applyGymPreset} disabled={isSubmitting}>
          Зал
        </Button>
        <Button type="button" variant="neutral" onClick={applyHomePreset} disabled={isSubmitting}>
          Типичный домашний набор
        </Button>
      </div>

      <label className="flex items-center gap-2 text-sm text-text-primary">
        <input
          type="checkbox"
          checked={hasGymAccess}
          onChange={(event) => setHasGymAccess(event.target.checked)}
          disabled={isSubmitting}
          className="h-4 w-4"
        />
        Есть доступ в тренажёрный зал
      </label>

      <div className="flex flex-col gap-2">
        <p className="text-xs text-text-secondary">
          {hasGymAccess
            ? 'При доступе в зал остальное не важно — доступны все упражнения.'
            : 'Или отметьте, что есть у вас — пусто тоже подходит, тренировки без инвентаря.'}
        </p>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          {EQUIPMENT_ITEMS.map((item) => (
            <label
              key={item}
              className={`flex items-center gap-2 text-sm text-text-primary ${hasGymAccess ? 'opacity-50' : ''}`}
            >
              <input
                type="checkbox"
                checked={selectedItems.has(item)}
                onChange={() => toggleItem(item)}
                disabled={isSubmitting || hasGymAccess}
                className="h-4 w-4"
              />
              {EQUIPMENT_ITEM_LABELS[item]}
            </label>
          ))}
        </div>
      </div>

      {available !== null && (
        <p className="text-sm text-accent-ice">Доступно {available} из {requirements?.length ?? 0} упражнений</p>
      )}

      {isSubmitting && <p className="text-sm text-text-secondary">Загрузка...</p>}
      <FormError message={error} />
      <div className="flex items-center justify-between">
        <Button type="button" variant="neutral" onClick={onNext} disabled={isSubmitting}>
          Пропустить
        </Button>
        <Button onClick={handleNext} isLoading={isSubmitting}>
          Далее
        </Button>
      </div>
    </div>
  )
}
