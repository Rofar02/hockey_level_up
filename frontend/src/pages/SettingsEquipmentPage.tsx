import { useEffect, useState } from 'react'
import { BackLink } from '../components/ui/BackLink'
import { Button } from '../components/ui/Button'
import { ChoiceCard } from '../components/ui/ChoiceCard'
import { FormError } from '../components/ui/FormError'
import { IceGlowBackground } from '../components/ui/IceGlowBackground'
import * as exercisesApi from '../api/exercises'
import * as usersApi from '../api/users'
import { ApiError } from '../api/client'
import { useAuth } from '../hooks/useAuth'
import { EQUIPMENT_ITEM_LABELS, GYM_COVERED_ITEMS, PERSONAL_GEAR_ITEMS } from '../types/exercise'
import type { EquipmentItem, ExerciseEquipmentRequirement } from '../types/exercise'
import { TYPICAL_HOME_PRESET, applyGymCoveredPreset, countAvailableExercises } from '../utils/equipmentAvailability'

export function SettingsEquipmentPage() {
  const { user, accessToken, updateUser } = useAuth()

  const [hasGymAccess, setHasGymAccess] = useState(user?.has_gym_access ?? false)
  const [isSavingGymAccess, setIsSavingGymAccess] = useState(false)
  const [gymAccessError, setGymAccessError] = useState<string | null>(null)

  const [ownedItems, setOwnedItems] = useState<Set<EquipmentItem> | null>(null)
  const [ownedItemsLoadError, setOwnedItemsLoadError] = useState<string | null>(null)
  const [ownedItemsSaveError, setOwnedItemsSaveError] = useState<string | null>(null)
  const [equipmentRequirements, setEquipmentRequirements] = useState<ExerciseEquipmentRequirement[] | null>(null)

  useEffect(() => {
    if (accessToken === null) {
      return
    }
    let cancelled = false
    usersApi
      .getMyEquipmentItems(accessToken)
      .then((items) => {
        if (!cancelled) {
          setOwnedItems(new Set(items))
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setOwnedItemsLoadError(
            err instanceof ApiError ? err.message : 'Не удалось загрузить инвентарь.',
          )
        }
      })
    return () => {
      cancelled = true
    }
  }, [accessToken])

  useEffect(() => {
    if (accessToken === null) {
      return
    }
    let cancelled = false
    exercisesApi
      .listExerciseEquipmentRequirements(accessToken)
      .then((result) => {
        if (!cancelled) {
          setEquipmentRequirements(result)
        }
      })
      .catch(() => {
        // Best-effort -- the toggles still work without a live counter.
      })
    return () => {
      cancelled = true
    }
  }, [accessToken])

  async function handleGymAccessSelect(value: boolean) {
    if (accessToken === null || value === hasGymAccess) {
      return
    }
    const previous = hasGymAccess
    setGymAccessError(null)
    setIsSavingGymAccess(true)
    setHasGymAccess(value)
    try {
      const updated = await usersApi.updateProfile({ has_gym_access: value }, accessToken)
      updateUser(updated)
    } catch (err) {
      setHasGymAccess(previous)
      setGymAccessError(err instanceof ApiError ? err.message : 'Не удалось сохранить выбор. Попробуйте ещё раз.')
    } finally {
      setIsSavingGymAccess(false)
    }
  }

  async function toggleOwnedItem(item: EquipmentItem) {
    if (accessToken === null || ownedItems === null) {
      return
    }
    const previous = ownedItems
    const next = new Set(previous)
    if (next.has(item)) {
      next.delete(item)
    } else {
      next.add(item)
    }
    setOwnedItemsSaveError(null)
    setOwnedItems(next)
    try {
      await usersApi.replaceMyEquipmentItems(Array.from(next), accessToken)
    } catch (err) {
      setOwnedItems(previous)
      setOwnedItemsSaveError(
        err instanceof ApiError ? err.message : 'Не удалось сохранить выбор. Попробуйте ещё раз.',
      )
    }
  }

  async function applyHomePreset() {
    if (accessToken === null) {
      return
    }
    const previousGymAccess = hasGymAccess
    const previousItems = ownedItems
    const nextItems = applyGymCoveredPreset(TYPICAL_HOME_PRESET, ownedItems ?? new Set())
    setGymAccessError(null)
    setOwnedItemsSaveError(null)
    setHasGymAccess(false)
    setOwnedItems(nextItems)
    try {
      if (hasGymAccess) {
        const updated = await usersApi.updateProfile({ has_gym_access: false }, accessToken)
        updateUser(updated)
      }
      await usersApi.replaceMyEquipmentItems(Array.from(nextItems), accessToken)
    } catch (err) {
      setHasGymAccess(previousGymAccess)
      setOwnedItems(previousItems)
      setOwnedItemsSaveError(
        err instanceof ApiError ? err.message : 'Не удалось сохранить выбор. Попробуйте ещё раз.',
      )
    }
  }

  return (
    <div className="relative min-h-svh overflow-hidden">
      <IceGlowBackground />
      <div className="relative z-[1] mx-auto flex max-w-2xl flex-col gap-6 px-4 py-8">
        <div className="flex flex-col gap-2">
          <BackLink />
          <h1 className="text-xl font-semibold">Оборудование</h1>
        </div>

        <div className="flex flex-col gap-4">
          <div className="flex flex-wrap gap-3">
            <Button
              type="button"
              variant="neutral"
              onClick={() => handleGymAccessSelect(true)}
              disabled={isSavingGymAccess}
            >
              Зал
            </Button>
            <Button type="button" variant="neutral" onClick={applyHomePreset} disabled={isSavingGymAccess}>
              Типичный домашний набор
            </Button>
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <ChoiceCard
              title="Тренажёрный зал"
              description="Полный доступ к тренажёрам и свободным весам"
              selected={hasGymAccess}
              disabled={isSavingGymAccess}
              onClick={() => handleGymAccessSelect(true)}
            />
            <ChoiceCard
              title="Свой инвентарь"
              description="Отметьте ниже, что есть — пусто тоже подходит, тренировки без инвентаря"
              selected={!hasGymAccess}
              disabled={isSavingGymAccess}
              onClick={() => handleGymAccessSelect(false)}
            />
          </div>
          <FormError message={gymAccessError} />

          <FormError message={ownedItemsLoadError} />
          {!hasGymAccess && ownedItems !== null && (
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
              {GYM_COVERED_ITEMS.map((item) => (
                <label key={item} className="flex items-center gap-2 text-sm text-text-primary">
                  <input
                    type="checkbox"
                    checked={ownedItems.has(item)}
                    onChange={() => toggleOwnedItem(item)}
                    className="h-4 w-4"
                  />
                  {EQUIPMENT_ITEM_LABELS[item]}
                </label>
              ))}
            </div>
          )}

          {ownedItems !== null && (
            <div className="flex flex-col gap-2">
              <p className="text-xs text-[#8A94A6]">
                Своё снаряжение — не покрывается доступом в зал, отмечайте отдельно.
              </p>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                {PERSONAL_GEAR_ITEMS.map((item) => (
                  <label key={item} className="flex items-center gap-2 text-sm text-text-primary">
                    <input
                      type="checkbox"
                      checked={ownedItems.has(item)}
                      onChange={() => toggleOwnedItem(item)}
                      className="h-4 w-4"
                    />
                    {EQUIPMENT_ITEM_LABELS[item]}
                  </label>
                ))}
              </div>
            </div>
          )}
          <FormError message={ownedItemsSaveError} />

          {equipmentRequirements !== null && ownedItems !== null && (
            <p className="text-sm text-accent-ice">
              Доступно {countAvailableExercises(equipmentRequirements, hasGymAccess, ownedItems)} из{' '}
              {equipmentRequirements.length} упражнений
            </p>
          )}
        </div>
      </div>
    </div>
  )
}
