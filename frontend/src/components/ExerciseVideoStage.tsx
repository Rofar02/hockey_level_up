import { useRef, useState } from 'react'
import type { ExerciseRead } from '../types/exercise'
import { exercisePosterUrl, exerciseVideoUrl } from '../utils/media'

// Poster frame + big play button while the clip is paused: the poster alone
// reads as a still picture, so the button is what says "this is a video".
// Native controls stay for scrubbing; the overlay only sits on top while
// paused/ended and hands the click to the <video>.
function FileVideoPlayer({ id, title }: { id: string; title: string }) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const [playing, setPlaying] = useState(false)

  return (
    <div className="relative aspect-video overflow-hidden rounded-md bg-black">
      <video
        ref={videoRef}
        src={exerciseVideoUrl(id)}
        poster={exercisePosterUrl(id)}
        title={title}
        className="h-full w-full"
        controls
        loop
        muted
        playsInline
        preload="metadata"
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
        onEnded={() => setPlaying(false)}
      />
      {!playing && (
        <button
          type="button"
          aria-label="Воспроизвести видео"
          onClick={() => void videoRef.current?.play()}
          className="absolute inset-0 flex items-center justify-center bg-black/20"
        >
          <span
            className="flex h-16 w-16 items-center justify-center rounded-full bg-black/55 ring-1 ring-white/40 backdrop-blur-sm"
            aria-hidden="true"
          >
            <i className="ti ti-player-play ml-0.5 text-3xl text-white" aria-hidden="true" />
          </span>
        </button>
      )}
    </div>
  )
}

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

  // Self-hosted clip (the author's permission was obtained): video_source_id
  // is the file's base name under static/exercise-videos/. Muted + looping
  // + inline so it behaves like a technique GIF on mobile, with controls
  // for scrubbing.
  if (exercise.video_source_type === 'file' && exercise.video_source_id !== null) {
    return <FileVideoPlayer id={exercise.video_source_id} title={exercise.name} />
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
