import type { ExerciseRead } from '../types/exercise'

// The actual video embed (or its placeholder) -- pulled out of
// ExerciseTechnique (2026-08-28) once ExerciseFocusScreen needed to show it
// up top, player-style, above the tabs rather than only inside the
// "Техника" tab. One component either way: a real embed here is exactly as
// good sitting at the top of the focus screen as it is inside that tab, so
// there's no reason to keep two copies of the source-type branching.
export function ExerciseVideoStage({ exercise }: { exercise: ExerciseRead }) {
  if (exercise.video_source_type === 'youtube' && exercise.video_source_id !== null) {
    return (
      <div className="aspect-video overflow-hidden rounded-md">
        <iframe
          src={`https://www.youtube.com/embed/${exercise.video_source_id}`}
          title={exercise.name}
          className="h-full w-full"
          allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
          allowFullScreen
        />
      </div>
    )
  }

  if (exercise.video_source_type === 'vk' && exercise.video_source_id !== null) {
    return (
      <div className="flex aspect-video items-center justify-center rounded-md bg-white/5 px-4 text-center text-sm text-text-secondary">
        Embed для VK будет добавлен отдельно
      </div>
    )
  }

  // Falls through here whenever hasExerciseVideo(exercise) is false (the
  // two branches above are the only ways it's true) -- 2026-08-20:
  // catalog-wide, no exercise has a real video yet (Stage 4 content pass
  // covers text/muscle tagging only, video shoot is a separate, later
  // effort). Styled as an actual player stage (dark, big play control)
  // rather than a small dashed-border box, since this now also has to read
  // as "this is where the video plays" at the top of ExerciseFocusScreen,
  // not just a filler inside a tab.
  return (
    <div className="relative flex aspect-video w-full items-center justify-center overflow-hidden rounded-md bg-black">
      <div
        className="flex h-14 w-14 items-center justify-center rounded-full bg-white/10 ring-1 ring-white/25"
        aria-hidden="true"
      >
        <i className="ti ti-player-play ml-0.5 text-2xl text-white" aria-hidden="true" />
      </div>
      <span className="absolute bottom-2 right-3 text-[10px] uppercase tracking-wide text-white/40">
        Видео скоро
      </span>
    </div>
  )
}
