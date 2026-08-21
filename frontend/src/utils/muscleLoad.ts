import type { MuscleGroup } from '../types/exercise'
import type { MuscleLoadRead } from '../types/progress'

// Maps our 8 coarse MuscleGroup values (Stage 2.1, 2026-08-20 planning
// session) onto the body-muscles library's own ~87 finer-grained
// left/right zone ids (see node_modules/body-muscles/dist/data/
// muscles.front.js and muscles.back.js for the authoritative id list --
// there's no published full list in the library's own README, only the
// naming convention).
//
// Each entry is a WEIGHT (0-1), not a flat membership list -- a region's
// displayed intensity is `load.intensity * weight`, so within one group
// the primary mover(s) render at full intensity and secondary/synergist
// regions render visibly lighter, instead of one uniform-colored blob
// across everything the group touches (e.g. training "core" lights up
// abs-upper/lower at full strength, obliques a bit less, hip-flexor less
// still -- a graduated spread, not a flat block).
//
// Full-avatar coverage: every library id maps to one of our 9 groups now
// (8 + forearms, added 2026-08-20 -- see MuscleGroup.FOREARMS), including
// the ones a first pass left permanently gray (knees -> quads/hamstrings;
// feet/tibialis-anterior -> calves; neck/nape -> back). The one deliberate
// exception is head/face -- there's no S&C muscle group there to honestly
// show, forcing a mapping would be decorative, not informative.
//
// Judgment calls worth naming:
//  - adductors (inner thigh) -> glutes (hip-stabilizing, closer fit than
//    quads/hamstrings), lower weight as a secondary mover there.
//  - hip-flexor -> core, lower weight (no better bucket exists).
//  - biceps/triceps/hand/forearm/elbow (front+back, both views) ->
//    forearms, all as one group (2026-08-20 fix for hand/forearm/elbow;
//    2026-08-21 fix extended it to biceps/triceps too). Biceps/triceps
//    were originally kept in back/chest as push/pull-chain synergists (a
//    real S&C convention -- they do assist those lifts), but live
//    click-testing on the front view showed the same problem hand/
//    forearm/elbow already had: tapping the visible arm and being told
//    "Спина" (or, on the back view, "Грудь" for triceps) reads as
//    arbitrary to someone just tapping their own arm, not explainable in
//    the UI. Correctness of the S&C convention lost to the interaction
//    actually making sense. hand gets full weight (the region most
//    likely to actually get clicked), forearm close behind, elbow/biceps/
//    triceps lower as joint/synergist regions rather than the prime
//    mover.
//  - knee (front) -> quads, knee (back) -> hamstrings; tibialis-anterior
//    and feet -> calves -- nearest lower-leg group, reduced weight.
const MUSCLE_LIBRARY_WEIGHTS_BY_GROUP: Record<MuscleGroup, Record<string, number>> = {
  quads: {
    'quads-left': 1.0,
    'quads-right': 1.0,
    'knee-left': 0.3,
    'knee-right': 0.3,
  },
  hamstrings: {
    'hamstrings-medial-left': 1.0,
    'hamstrings-lateral-left': 1.0,
    'hamstrings-medial-right': 1.0,
    'hamstrings-lateral-right': 1.0,
    'knee-back-left': 0.3,
    'knee-back-right': 0.3,
  },
  glutes: {
    'gluteus-maximus-left': 1.0,
    'gluteus-maximus-right': 1.0,
    'gluteus-medius-left': 0.8,
    'gluteus-medius-right': 0.8,
    'adductors-left': 0.5,
    'adductors-right': 0.5,
  },
  chest: {
    'chest-upper-left': 1.0,
    'chest-lower-left': 1.0,
    'chest-upper-right': 1.0,
    'chest-lower-right': 1.0,
  },
  back: {
    'traps-upper-left': 1.0, 'traps-mid-left': 1.0, 'traps-lower-left': 1.0,
    'traps-upper-right': 1.0, 'traps-mid-right': 1.0, 'traps-lower-right': 1.0,
    'lats-upper-left': 1.0, 'lats-mid-left': 1.0, 'lats-lower-left': 1.0,
    'lats-upper-right': 1.0, 'lats-mid-right': 1.0, 'lats-lower-right': 1.0,
    spine: 0.9,
    'lower-back-erectors-left': 0.9, 'lower-back-ql-left': 0.9,
    'lower-back-erectors-right': 0.9, 'lower-back-ql-right': 0.9,
    'neck-left': 0.4, 'neck-right': 0.4, nape: 0.4,
  },
  forearms: {
    'hand-left': 1.0, 'hand-right': 1.0,
    'hand-back-left': 1.0, 'hand-back-right': 1.0,
    'forearm-left': 0.8, 'forearm-right': 0.8,
    'forearm-flexors-left': 0.8, 'forearm-flexors-right': 0.8,
    'forearm-extensors-left': 0.8, 'forearm-extensors-right': 0.8,
    'elbow-left': 0.4, 'elbow-right': 0.4,
    'biceps-left': 0.35, 'biceps-right': 0.35,
    'triceps-long-left': 0.35, 'triceps-lateral-left': 0.35,
    'triceps-long-right': 0.35, 'triceps-lateral-right': 0.35,
  },
  shoulders: {
    'shoulder-front-left': 1.0, 'shoulder-side-left': 1.0,
    'shoulder-front-right': 1.0, 'shoulder-side-right': 1.0,
    'deltoid-rear-left': 1.0, 'deltoid-rear-right': 1.0,
  },
  core: {
    'abs-upper-left': 1.0, 'abs-lower-left': 1.0,
    'abs-upper-right': 1.0, 'abs-lower-right': 1.0,
    'obliques-left': 0.8, 'obliques-right': 0.8,
    'serratus-anterior-left': 0.6, 'serratus-anterior-right': 0.6,
    'hip-flexor-left': 0.5, 'hip-flexor-right': 0.5,
  },
  calves: {
    'calves-gastroc-medial-left': 1.0, 'calves-gastroc-lateral-left': 1.0, 'calves-soleus-left': 1.0,
    'calves-gastroc-medial-right': 1.0, 'calves-gastroc-lateral-right': 1.0, 'calves-soleus-right': 1.0,
    'tibialis-anterior-left': 0.4, 'tibialis-anterior-right': 0.4,
    'foot-left': 0.3, 'foot-right': 0.3,
    'foot-back-left': 0.3, 'foot-back-right': 0.3,
  },
}

// Reverse lookup for click-to-detail (MuscleLoadChart's onMuscleClick) --
// which of our 8 groups "owns" a given library id. Built once from the
// weight map above rather than maintained separately, so the two can
// never drift out of sync with each other.
const GROUP_BY_LIBRARY_ID: Record<string, MuscleGroup> = Object.fromEntries(
  (Object.entries(MUSCLE_LIBRARY_WEIGHTS_BY_GROUP) as [MuscleGroup, Record<string, number>][]).flatMap(
    ([group, weights]) => Object.keys(weights).map((libraryId) => [libraryId, group]),
  ),
)

export function muscleGroupForLibraryId(libraryId: string): MuscleGroup | null {
  return GROUP_BY_LIBRARY_ID[libraryId] ?? null
}

// The plan's own 5-stage bucketing of the continuous 0-10 intensity the
// backend sends -- purely a display concern (see MuscleLoadRead's own
// docstring for why this isn't a server-computed field), same "derive the
// label client-side from one raw value" shape as hasExerciseVideo/
// hasExerciseDescription elsewhere in this codebase.
export const MUSCLE_LOAD_STAGES = [
  'untrained', 'fresh', 'light', 'moderate', 'overloaded',
] as const
export type MuscleLoadStage = (typeof MUSCLE_LOAD_STAGES)[number]

export const MUSCLE_LOAD_STAGE_LABELS: Record<MuscleLoadStage, string> = {
  untrained: 'Не тренировано',
  fresh: 'Свежая',
  light: 'Лёгкая',
  moderate: 'Средняя',
  overloaded: 'Перегружена',
}

// Plain-language gloss of what each stage means for training decisions --
// mirrors the actual recovery model in app/core/muscle_load.py (12h grace
// period with no recovery credited, then halving every 12h, so a hard
// session is ~90% recovered by 48h and ~97% by 72h) rather than being an
// arbitrary UI-only description.
export const MUSCLE_LOAD_STAGE_DESCRIPTIONS: Record<MuscleLoadStage, string> = {
  untrained: 'Давно не было целевой нагрузки на эту группу — можно тренировать без ограничений.',
  fresh: 'Нагрузка почти сошла на нет, восстановление в самом конце — группа готова к работе.',
  light: 'Есть остаточная нагрузка от недавней тренировки, но восстановление идёт полным ходом.',
  moderate: 'Мышца ещё не восстановилась полностью. Тренировать можно, но тяжёлую работу лучше отложить на 1–2 дня.',
  overloaded: 'Свежая тяжёлая нагрузка. Организму нужно 2–3 дня, чтобы восстановиться — дайте группе отдохнуть.',
}

export function muscleLoadStage(intensity: number): MuscleLoadStage {
  if (intensity <= 0) return 'untrained'
  if (intensity <= 2) return 'fresh'
  if (intensity <= 5) return 'light'
  if (intensity <= 8) return 'moderate'
  return 'overloaded'
}

// body-muscles' own BodyState shape: Partial<Record<libraryMuscleId,
// { intensity: number; selected: boolean }>>. selected is always false --
// this is a heatmap-only integration (see the plan's own "onMuscleClick
// optional, not required for heatmap-режим" note), nothing in this app
// drives per-muscle selection.
export interface BodyMusclesState {
  [libraryMuscleId: string]: { intensity: number; selected: boolean }
}

// `selectedGroup` marks every one of that group's library ids as
// `selected` together, not just the single sub-region actually tapped.
// The library's ~87 regions are packed tightly enough (viewBox is a mere
// 35x93 units) that a finger's real contact area covers several of them
// at once -- without this, each tiny sliver reacts to hover/tap on its
// own and a single tap on "core" visually reads as many unrelated
// buttons lighting up. Grouping the selected-state visuals to the whole
// MuscleGroup (matching the 8-value taxonomy the click handler already
// resolves down to) makes one tap read as one coherent selection,
// regardless of exactly which sub-region the finger happened to land on.
export function buildBodyMusclesState(
  loads: MuscleLoadRead[],
  selectedGroup: MuscleGroup | null = null,
): BodyMusclesState {
  const intensityByGroup = new Map(loads.map((load) => [load.muscle_group, load.intensity]))
  const state: BodyMusclesState = {}
  for (const [group, weights] of Object.entries(MUSCLE_LIBRARY_WEIGHTS_BY_GROUP) as [
    MuscleGroup,
    Record<string, number>,
  ][]) {
    const intensity = intensityByGroup.get(group) ?? 0
    const selected = group === selectedGroup
    if (intensity === 0 && !selected) {
      continue
    }
    for (const [libraryId, weight] of Object.entries(weights)) {
      state[libraryId] = { intensity: intensity * weight, selected }
    }
  }
  return state
}
