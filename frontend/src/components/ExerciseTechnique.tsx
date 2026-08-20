import { hasExerciseDescription, hasExerciseVideo } from '../utils/exerciseTechnique'
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
      {/* 2026-08-20: catalog-wide, no exercise has a real video yet (Stage
          4 content pass covers text/muscle tagging only, video shoot is a
          separate, later effort) -- a placeholder keeps the "Техника" tab
          from looking broken/unfinished and previews where the real embed
          will eventually sit. */}
      {!hasExerciseVideo(exercise) && (
        <div className="flex aspect-video flex-col items-center justify-center gap-2 rounded-md border border-dashed border-white/15 bg-white/5 text-text-secondary">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth={1.5}
            className="h-8 w-8 opacity-60"
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16v12H4z" />
            <path strokeLinecap="round" strokeLinejoin="round" d="M10 9.5l5 2.5-5 2.5v-5z" />
          </svg>
          <span className="text-sm">Видео техники скоро появится</span>
        </div>
      )}
    </div>
  )
}
