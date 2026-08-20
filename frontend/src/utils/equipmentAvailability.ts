import type { EquipmentItem, ExerciseEquipmentRequirement } from '../types/exercise'

// Mirrors ExerciseRepository.list_for_assembly's own has_gym_access/
// owned-items subset check (app/repositories/exercise_repository.py) --
// client-side so the onboarding/profile inventory screen's "Доступно X из
// N" counter updates on every checkbox tap with no network round trip.
// Requirements come from GET /exercises/equipment-requirements (off_ice
// only, see that endpoint's own docstring for why).
export function countAvailableExercises(
  requirements: ExerciseEquipmentRequirement[],
  hasGymAccess: boolean,
  ownedItems: ReadonlySet<EquipmentItem>,
): number {
  if (hasGymAccess) {
    return requirements.length
  }
  return requirements.filter((requirement) =>
    requirement.equipment_items.every((item) => ownedItems.has(item)),
  ).length
}

// A reasonable common home setup -- one of the two quick presets ("Зал"
// is the other, see EquipmentStep.tsx/SettingsPage.tsx), not meant to be
// exhaustive of every possible home gym.
export const TYPICAL_HOME_PRESET: readonly EquipmentItem[] = [
  'dumbbells',
  'resistance_band',
  'pull_up_bar',
  'jump_rope',
]
