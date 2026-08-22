import { GYM_COVERED_ITEMS, PERSONAL_GEAR_ITEMS } from '../types/exercise'
import type { EquipmentItem, ExerciseEquipmentRequirement } from '../types/exercise'

// Mirrors ExerciseRepository.list_for_assembly's own has_gym_access/
// owned-items subset check (app/repositories/exercise_repository.py) --
// client-side so the onboarding/profile inventory screen's "Доступно X из
// N" counter updates on every checkbox tap with no network round trip.
// Requirements come from GET /exercises/equipment-requirements (off_ice
// only, see that endpoint's own docstring for why).
//
// 2026-08-22: has_gym_access no longer bypasses every item -- an exercise
// requiring a PERSONAL_GEAR_ITEMS item (e.g. hockey_stick) still needs
// that item in ownedItems regardless of gym access, same fix as the
// backend's personal-gear split.
export function countAvailableExercises(
  requirements: ExerciseEquipmentRequirement[],
  hasGymAccess: boolean,
  ownedItems: ReadonlySet<EquipmentItem>,
): number {
  return requirements.filter((requirement) =>
    requirement.equipment_items.every(
      (item) => ownedItems.has(item) || (hasGymAccess && GYM_COVERED_ITEMS.includes(item)),
    ),
  ).length
}

// How many exercises require this specific item (regardless of what else
// they also require, and regardless of whether the user owns it) --
// the "как в играх, нажимая на предмет — сколько упражнений оно
// добавляет" inventory-tab detail count. Deliberately the simple "used by"
// count, not a marginal "how many NEWLY become available if I add just
// this one" figure -- that would depend on the rest of the owned set in a
// way that's more confusing than useful in a per-item detail view.
export function countExercisesUsingItem(
  requirements: ExerciseEquipmentRequirement[],
  item: EquipmentItem,
): number {
  return requirements.filter((requirement) => requirement.equipment_items.includes(item)).length
}

// A reasonable common home setup -- one of the two quick presets ("Зал"
// is the other, see EquipmentStep.tsx/SettingsPage.tsx), not meant to be
// exhaustive of every possible home gym.
export const TYPICAL_HOME_PRESET: readonly EquipmentItem[] = ['dumbbells', 'resistance_band', 'jump_rope']

// 2026-08-22: applying a gym-equipment preset (the "Зал"/"Типичный
// домашний набор" buttons) must not silently drop any PERSONAL_GEAR_ITEMS
// the user already checked -- a stick isn't part of either preset, so a
// naive `setOwnedItems(new Set(preset))` would wipe it out. Carries the
// current personal-gear selection forward into the next gym-covered set.
export function applyGymCoveredPreset(
  nextGymCoveredItems: readonly EquipmentItem[],
  currentOwnedItems: ReadonlySet<EquipmentItem>,
): Set<EquipmentItem> {
  const preservedPersonalGear = [...currentOwnedItems].filter((item) =>
    PERSONAL_GEAR_ITEMS.includes(item),
  )
  return new Set([...nextGymCoveredItems, ...preservedPersonalGear])
}
