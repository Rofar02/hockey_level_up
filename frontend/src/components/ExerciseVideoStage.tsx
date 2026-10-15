import { useRef, useState } from 'react'
import { useOnline } from '../hooks/useNetworkStatus'
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
// Videos aren't saved for offline use (Б1, 2026-10-13) -- too big. Without
// a connection the stage says so; the technique text below stays.
function VideoNeedsNetwork() {
  return (
    <div className="flex aspect-video w-full flex-col items-center justify-center gap-2 rounded-md bg-black px-4 text-center">
      <i className="ti ti-wifi-off text-2xl text-white/50" aria-hidden="true" />
      <span className="text-sm text-text-secondary">Видео доступно при подключении</span>
    </div>
  )
}

export function ExerciseVideoStage({ exercise }: { exercise: ExerciseRead }) {
  const online = useOnline()
  const hasVideo =
    exercise.video_source_id !== null && (exercise.video_source_type === 'youtube' || exercise.video_source_type === 'file')
  if (hasVideo && !online) {
    return <VideoNeedsNetwork />
  }
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

  // No video yet (VK embeds aren't supported either): a slim, plainly
  // inactive strip -- 15.10: the old full-size black stage with a big ▶ read
  // as a player that wouldn't start.
  return (
    <div
      className="flex min-h-12 w-full items-center gap-2.5 rounded-md border border-dashed border-white/10 px-3.5 py-2.5 text-sm text-text-secondary"
      data-video-placeholder
    >
      <i className="ti ti-video-off text-lg" aria-hidden="true" />
      Видео скоро — техника описана ниже
    </div>
  )
}
