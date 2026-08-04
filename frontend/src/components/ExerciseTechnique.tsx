import { hasExerciseDescription } from '../utils/exerciseTechnique'
import type { ExerciseRead } from '../types/exercise'

// Video embed + description -- shared between TrainingSessionPage's
// "Техника" tab and NewSchedulePage's read-only day-preview modal, so the
// embed logic (and any future video-source support) lives in exactly one
// place. Callers that need to gate on "is there anything to show" first
// should check hasExerciseTechnique (utils/exerciseTechnique) separately --
// this component always renders its wrapper div even if both description
// and video end up absent (callers are expected not to render it in that
// case).
export function ExerciseTechnique({ exercise }: { exercise: ExerciseRead }) {
  return (
    <div className="flex flex-col gap-3">
      {hasExerciseDescription(exercise) && (
        <p className="text-sm text-text-secondary">{exercise.description}</p>
      )}
      {exercise.video_source_type === 'youtube' && exercise.video_source_id !== null && (
        <div className="aspect-video overflow-hidden rounded-md">
          <iframe
            src={`https://www.youtube.com/embed/${exercise.video_source_id}`}
            title={exercise.name}
            className="h-full w-full"
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
            allowFullScreen
          />
        </div>
      )}
      {exercise.video_source_type === 'vk' && exercise.video_source_id !== null && (
        <p className="text-sm text-text-secondary">Embed для VK будет добавлен отдельно</p>
      )}
    </div>
  )
}
