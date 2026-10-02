import { useEffect, useState } from 'react'
import { BackLink } from '../components/ui/BackLink'
import { Button } from '../components/ui/Button'
import { CARD_CLASS } from '../components/ui/cardStyle'
import { EquipmentIcon } from '../components/ui/EquipmentIcon'
import { FormError } from '../components/ui/FormError'
import { IceGlowBackground } from '../components/ui/IceGlowBackground'
import { Switch } from '../components/ui/Switch'
import * as exercisesApi from '../api/exercises'
import * as usersApi from '../api/users'
import { ApiError } from '../api/client'
import { useAuth } from '../hooks/useAuth'
import { EQUIPMENT_ITEM_LABELS, GYM_COVERED_ITEMS, PERSONAL_GEAR_ITEMS } from '../types/exercise'
import type { EquipmentItem, ExerciseEquipmentRequirement } from '../types/exercise'
import {
  TYPICAL_HOME_PRESET,
  applyGymCoveredPreset,
  countAvailableExercises,
  countExercisesUsingItem,
  needsPullEquipmentNudge,
} from '../utils/equipmentAvailability'

// The one place a player says what they train with -- gym access plus the
// items they own. It used to live twice: Settings › Оборудование (the
// toggles) and a tab in the profile's details modal (icons + per-item
// exercise counts), with the same data behind both.
export function InventoryPage() {
  const { user, accessToken, updateUser } = useAuth()

  const [hasGymAccess, setHasGymAccess] = useState(user?.has_gym_access ?? false)
  const [isSavingGymAccess, setIsSavingGymAccess] = useState(false)
  const [ownedItems, setOwnedItems] = useState<Set<EquipmentItem> | null>(null)
  const [requirements, setRequirements] = useState<ExerciseEquipmentRequirement[] | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [saveError, setSaveError] = useState<string | null>(null)

  useEffect(() => {
    if (accessToken === null) {
      return
    }
    let cancelled = false
    usersApi
      .getMyEquipmentItems(accessToken)
      .then((items) => !cancelled && setOwnedItems(new Set(items)))
      .catch((err: unknown) => {
        if (!cancelled) {
          setLoadError(err instanceof ApiError ? err.message : 'Не удалось загрузить инвентарь.')
        }
      })
    exercisesApi
      .listExerciseEquipmentRequirements(accessToken)
      .then((result) => !cancelled && setRequirements(result))
      .catch(() => {
        // Best-effort -- the toggles still work without the counters.
      })
    return () => {
      cancelled = true
    }
  }, [accessToken])

  async function handleGymAccessToggle() {
    if (accessToken === null) {
      return
    }
    const previous = hasGymAccess
    setSaveError(null)
    setIsSavingGymAccess(true)
    setHasGymAccess(!previous)
    try {
      const updated = await usersApi.updateProfile({ has_gym_access: !previous }, accessToken)
      updateUser(updated)
    } catch (err) {
      setHasGymAccess(previous)
      setSaveError(err instanceof ApiError ? err.message : 'Не удалось сохранить выбор. Попробуйте ещё раз.')
    } finally {
      setIsSavingGymAccess(false)
    }
  }

  async function toggleItem(item: EquipmentItem) {
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
    setSaveError(null)
    setOwnedItems(next)
    try {
      await usersApi.replaceMyEquipmentItems(Array.from(next), accessToken)
    } catch (err) {
      setOwnedItems(previous)
      setSaveError(err instanceof ApiError ? err.message : 'Не удалось сохранить выбор. Попробуйте ещё раз.')
    }
  }

  async function applyHomePreset() {
    if (accessToken === null || ownedItems === null) {
      return
    }
    const previousGymAccess = hasGymAccess
    const previousItems = ownedItems
    const nextItems = applyGymCoveredPreset(TYPICAL_HOME_PRESET, ownedItems)
    setSaveError(null)
    setHasGymAccess(false)
    setOwnedItems(nextItems)
    try {
      if (previousGymAccess) {
        updateUser(await usersApi.updateProfile({ has_gym_access: false }, accessToken))
      }
      await usersApi.replaceMyEquipmentItems(Array.from(nextItems), accessToken)
    } catch (err) {
      setHasGymAccess(previousGymAccess)
      setOwnedItems(previousItems)
      setSaveError(err instanceof ApiError ? err.message : 'Не удалось сохранить выбор. Попробуйте ещё раз.')
    }
  }

  function renderItems(items: readonly EquipmentItem[]) {
    if (ownedItems === null) {
      return null
    }
    return (
      <div className="grid grid-cols-2 gap-2">
        {items.map((item) => {
          const owned = ownedItems.has(item)
          const usedBy = requirements !== null ? countExercisesUsingItem(requirements, item) : null
          return (
            <button
              key={item}
              type="button"
              onClick={() => toggleItem(item)}
              aria-pressed={owned}
              className={`flex min-h-[64px] items-center gap-3 rounded-md border px-3 py-2.5 text-left transition-colors ${
                owned ? 'border-accent-ice/50 bg-accent-ice/10' : 'border-white/10 bg-dark-card hover:border-white/20'
              }`}
            >
              <EquipmentIcon item={item} className={`text-2xl ${owned ? 'text-accent-ice' : 'text-[#8A94A6]'}`} />
              <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                <span className="text-sm leading-tight text-[#F5F7FA]">{EQUIPMENT_ITEM_LABELS[item]}</span>
                {usedBy !== null && (
                  <span className={`text-xs ${owned ? 'text-accent-ice' : 'text-[#8A94A6]'}`}>
                    {owned ? 'Есть' : `в ${usedBy} упражн.`}
                  </span>
                )}
              </span>
            </button>
          )
        })}
      </div>
    )
  }

  return (
    <div className="relative min-h-svh overflow-hidden">
      <IceGlowBackground />
      <div className="relative z-[1] mx-auto flex max-w-2xl flex-col gap-5 px-4 py-6">
        <div className="flex flex-col gap-2">
          <BackLink />
          <h1 className="text-xl font-semibold">Инвентарь</h1>
          <p className="text-sm text-[#8A94A6]">От этого зависит, какие упражнения попадут в ваш план.</p>
        </div>

        {requirements !== null && ownedItems !== null && (
          <p className="text-sm text-accent-ice">
            Доступно {countAvailableExercises(requirements, hasGymAccess, ownedItems)} из {requirements.length}{' '}
            упражнений
          </p>
        )}

        <div className={`flex items-center gap-3 px-4 py-3.5 ${CARD_CLASS}`}>
          <span className="flex flex-1 flex-col gap-0.5">
            <span className="text-sm font-medium text-[#F5F7FA]">Хожу в тренажёрный зал</span>
            <span className="text-xs text-[#8A94A6]">Тренажёры, штанга и свободные веса — всё, что есть в зале</span>
          </span>
          <Switch checked={hasGymAccess} disabled={isSavingGymAccess} onClick={handleGymAccessToggle} />
        </div>

        <FormError message={loadError} />
        <FormError message={saveError} />

        {hasGymAccess && (
          <p className="px-1 text-xs leading-relaxed text-[#8A94A6]">
            Всё оборудование зала уже учтено: штанга, гантели, гири, турник, тренажёры и остальное.
          </p>
        )}

        {!hasGymAccess && (
          <section className="flex flex-col gap-2">
            <div className="flex items-center justify-between gap-2 px-1">
              <h2 className="text-xs font-semibold uppercase tracking-wide text-[#8A94A6]">Дома</h2>
              <Button type="button" variant="neutral" onClick={applyHomePreset} className="!px-3 !py-1 !text-xs">
                Типичный домашний набор
              </Button>
            </div>
            {renderItems(GYM_COVERED_ITEMS)}
          </section>
        )}

        <section className="flex flex-col gap-2">
          <h2 className="px-1 text-xs font-semibold uppercase tracking-wide text-[#8A94A6]">Своё снаряжение</h2>
          <p className="px-1 text-xs text-[#8A94A6]">Этого в зале обычно нет — отмечайте отдельно.</p>
          {renderItems(PERSONAL_GEAR_ITEMS)}
        </section>

        {ownedItems !== null && needsPullEquipmentNudge(hasGymAccess, ownedItems) && (
          <p className="text-xs text-[#8A94A6]">
            Совсем без инвентаря почти не остаётся тяговых упражнений на спину — рекомендуем взять хотя бы
            резинку-эспандер, она недорогая и помещается в сумку.
          </p>
        )}
      </div>
    </div>
  )
}
