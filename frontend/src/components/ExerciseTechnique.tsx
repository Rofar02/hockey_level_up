import { ExerciseVideoStage } from './ExerciseVideoStage'
import { hasExerciseDescription } from '../utils/exerciseTechnique'
import type { ExerciseRead } from '../types/exercise'

// Description + video embed -- shared between TrainingSessionPage's
// "Техника" tab and NewSchedulePage's read-only day-preview modal, so the
// embed logic (and any future video-source support) lives in exactly one
// place. Callers that need to gate on "is there anything to show" first
// should check hasExerciseTechnique (utils/exerciseTechnique) separately --
// this component always renders its wrapper div even if both description
// and video end up absent (callers are expected not to render it in that
// case).
export function ExerciseTechnique({
  exercise,
  hideVideo = false,
}: {
  exercise: ExerciseRead
  // ExerciseFocusScreen already shows ExerciseVideoStage once, above the
  // tabs (2026-08-28) -- true there so the "Техника" tab doesn't repeat it
  // right below. Unused (video renders here as it always has) for the
  // boxed ExerciseDetailModal, which has no video area of its own.
  hideVideo?: boolean
}) {
  return (
    <div className="flex flex-col gap-3">
      {hasExerciseDescription(exercise) && (
        <p className="text-sm text-text-secondary">{exercise.description}</p>
      )}
      {!hideVideo && <ExerciseVideoStage exercise={exercise} />}
    </div>
  )
}
