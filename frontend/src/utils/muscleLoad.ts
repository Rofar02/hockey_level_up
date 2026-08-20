import type { MuscleGroup } from '../types/exercise'
import type { MuscleLoadRead } from '../types/progress'

// Maps our 8 coarse MuscleGroup values (Stage 2.1, 2026-08-20 planning
// session) onto the body-muscles library's own ~87 finer-grained
// left/right zone ids (see node_modules/body-muscles/dist/data/
// muscles.front.js and muscles.back.js for the authoritative id list --
// there's no published full list in the library's own README, only the
// naming convention). Several library ids always map to the same one of
// our groups since our taxonomy doesn't track laterality or the library's
// finer subdivisions (e.g. traps vs lats both read as our single "back"
// value).
//
// Deliberately unmapped, left permanently neutral on the chart: head,
// face, neck, biceps/forearm/elbow/hand (front+back), knee, foot -- our
// 8-value taxonomy has no bucket for arms/hands/feet/knees at all (see
// MUSCLE_GROUPS in types/exercise.ts), so there's nothing honest to show
// there rather than force-fitting them into a group that doesn't
// anatomically match.
//
// Two judgment calls worth naming: adductors (inner thigh) map to
// "glutes" rather than "quads"/"hamstrings" -- both are hip-stabilizing
// muscles, the closer anatomical fit of the two. hip-flexor maps to
// "core" for the same reason -- no better bucket exists among our 8.
const MUSCLE_LIBRARY_IDS_BY_GROUP: Record<MuscleGroup, string[]> = {
  quads: ['quads-left', 'quads-right'],
  hamstrings: [
    'hamstrings-medial-left',
    'hamstrings-lateral-left',
    'hamstrings-medial-right',
    'hamstrings-lateral-right',
  ],
  glutes: [
    'gluteus-medius-left',
    'gluteus-maximus-left',
    'gluteus-medius-right',
    'gluteus-maximus-right',
    'adductors-left',
    'adductors-right',
  ],
  chest: ['chest-upper-left', 'chest-lower-left', 'chest-upper-right', 'chest-lower-right'],
  back: [
    'traps-upper-left', 'traps-mid-left', 'traps-lower-left',
    'traps-upper-right', 'traps-mid-right', 'traps-lower-right',
    'lats-upper-left', 'lats-mid-left', 'lats-lower-left',
    'lats-upper-right', 'lats-mid-right', 'lats-lower-right',
    'spine', 'lower-back-erectors-left', 'lower-back-ql-left',
    'lower-back-erectors-right', 'lower-back-ql-right',
  ],
  shoulders: [
    'shoulder-front-left', 'shoulder-side-left',
    'shoulder-front-right', 'shoulder-side-right',
    'deltoid-rear-left', 'deltoid-rear-right',
  ],
  core: [
    'abs-upper-left', 'abs-lower-left', 'serratus-anterior-left', 'obliques-left',
    'abs-upper-right', 'abs-lower-right', 'serratus-anterior-right', 'obliques-right',
    'hip-flexor-left', 'hip-flexor-right',
  ],
  calves: [
    'calves-gastroc-medial-left', 'calves-gastroc-lateral-left', 'calves-soleus-left',
    'calves-gastroc-medial-right', 'calves-gastroc-lateral-right', 'calves-soleus-right',
  ],
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

export function buildBodyMusclesState(loads: MuscleLoadRead[]): BodyMusclesState {
  const state: BodyMusclesState = {}
  for (const load of loads) {
    const libraryIds = MUSCLE_LIBRARY_IDS_BY_GROUP[load.muscle_group]
    for (const libraryId of libraryIds) {
      state[libraryId] = { intensity: load.intensity, selected: false }
    }
  }
  return state
}
