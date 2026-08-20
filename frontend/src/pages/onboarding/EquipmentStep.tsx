import { useState } from 'react'
import { Button } from '../../components/ui/Button'
import { ChoiceCard } from '../../components/ui/ChoiceCard'
import { FormError } from '../../components/ui/FormError'
import * as usersApi from '../../api/users'
import { ApiError } from '../../api/client'
import { useAuth } from '../../hooks/useAuth'
import { EQUIPMENT_ITEMS, EQUIPMENT_ITEM_LABELS } from '../../types/exercise'
import type { EquipmentItem } from '../../types/exercise'

// Functional but intentionally modest (Stage 2.2, 2026-08-20 planning
// session) -- a real gym-access + item checklist against the new
// ExerciseEquipmentItem/UserEquipmentItem model, replacing the old flat
// gym/home/bodyweight picker. The full one-screen redesign (quick presets,
// live "unlocks N exercises" counter, skippable with a bodyweight-only
// default) is Stage 2.3's job, not this one -- this keeps the same
// blocking, must-choose-something shape the old 3-card picker had.
export function EquipmentStep({ onNext }: { onNext: () => void }) {
  const { accessToken } = useAuth()
  const [hasGymAccess, setHasGymAccess] = useState<boolean | null>(null)
  const [selectedItems, setSelectedItems] = useState<Set<EquipmentItem>>(new Set())
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

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

  async function handleNext() {
    if (hasGymAccess === null || accessToken === null) {
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

  return (
    <div className="flex flex-col gap-6">
      <h2 className="text-lg font-semibold">Какое оборудование у вас есть?</h2>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <ChoiceCard
          title="Тренажёрный зал"
          description="Полный доступ к тренажёрам и свободным весам"
          selected={hasGymAccess === true}
          disabled={isSubmitting}
          onClick={() => setHasGymAccess(true)}
        />
        <ChoiceCard
          title="Свой инвентарь"
          description="Отметьте ниже, что есть дома — пусто тоже подходит, тренировки без инвентаря"
          selected={hasGymAccess === false}
          disabled={isSubmitting}
          onClick={() => setHasGymAccess(false)}
        />
      </div>

      {hasGymAccess === false && (
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          {EQUIPMENT_ITEMS.map((item) => (
            <label key={item} className="flex items-center gap-2 text-sm text-text-primary">
              <input
                type="checkbox"
                checked={selectedItems.has(item)}
                onChange={() => toggleItem(item)}
                disabled={isSubmitting}
                className="h-4 w-4"
              />
              {EQUIPMENT_ITEM_LABELS[item]}
            </label>
          ))}
        </div>
      )}

      {isSubmitting && <p className="text-sm text-text-secondary">Загрузка...</p>}
      <FormError message={error} />
      <Button
        onClick={handleNext}
        disabled={hasGymAccess === null}
        isLoading={isSubmitting}
        className="self-end"
      >
        Далее
      </Button>
    </div>
  )
}
