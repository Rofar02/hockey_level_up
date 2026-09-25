import { useEffect, useState } from 'react'
import { RinkDiagram } from './RinkDiagram'
import type { DrillDiagram } from '../../../types/teamEvent'
import { diagramFrames } from '../../../utils/rinkDiagram'

// How long each frame stays on screen while playing -- long enough for its
// dots to finish their run (RinkDiagram's MovingDot takes 1.1s).
const FRAME_MS = 1700

// A drill's scheme for players: the whole thing at rest ("Всё"), frame by
// frame ("1 · 2 · 3" -- what happens at the same time, and in what order),
// and "▶" to play the frames through. A scheme with a single frame has
// nothing to step through and shows plain.
export function FramePlayer({ diagram, className = '' }: { diagram: DrillDiagram; className?: string }) {
  const frames = diagramFrames(diagram)
  const [frame, setFrame] = useState<number | null>(null)
  const [isPlaying, setIsPlaying] = useState(false)
  const [playKey, setPlayKey] = useState(0)

  // One step of playback per FRAME_MS: 1 → 2 → … → last → back to "Всё".
  useEffect(() => {
    if (!isPlaying) {
      return
    }
    const timer = setTimeout(() => {
      const index = frame === null ? -1 : frames.indexOf(frame)
      if (index < frames.length - 1) {
        setFrame(frames[index + 1])
        setPlayKey((key) => key + 1)
      } else {
        setFrame(null)
        setIsPlaying(false)
      }
    }, frame === null ? 0 : FRAME_MS)
    return () => clearTimeout(timer)
  }, [isPlaying, frame, frames])

  if (frames.length <= 1) {
    return <RinkDiagram diagram={diagram} className={className} />
  }

  function pick(next: number | null) {
    setIsPlaying(false)
    setFrame(next)
  }

  function togglePlay() {
    if (isPlaying) {
      setIsPlaying(false)
      return
    }
    // Start from the beginning -- the timer effect moves to frame 1 at once.
    setFrame(null)
    setIsPlaying(true)
  }

  return (
    <div className="flex flex-col items-center gap-2.5">
      <RinkDiagram
        diagram={diagram}
        className={className}
        frame={frame}
        playKey={isPlaying ? playKey : null}
        moveTokens
      />
      <div className="flex max-w-full flex-wrap items-center justify-center gap-1.5">
        <button
          type="button"
          onClick={togglePlay}
          aria-label={isPlaying ? 'Пауза' : 'Проиграть'}
          className="flex h-10 w-10 items-center justify-center rounded-full bg-accent-persimmon text-white transition-transform active:scale-95"
        >
          {/* Inline -- the icon font on the CDN has no filled variants. */}
          <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
            {isPlaying ? (
              <path d="M4 2.5h2.6v11H4zM9.4 2.5H12v11H9.4z" fill="currentColor" />
            ) : (
              <path d="M4.5 2.3v11.4c0 .5.5.8.9.5l8.4-5.7a.6.6 0 0 0 0-1L5.4 1.8c-.4-.3-.9 0-.9.5z" fill="currentColor" />
            )}
          </svg>
        </button>
        <div role="group" aria-label="Кадры" className="flex flex-wrap items-center gap-1 rounded-full bg-white/5 p-1">
          <FrameChip label="Всё" active={frame === null && !isPlaying} onClick={() => pick(null)} />
          {frames.map((value) => (
            <FrameChip
              key={value}
              label={String(value)}
              ariaLabel={`Кадр ${value}`}
              active={frame === value}
              onClick={() => pick(value)}
            />
          ))}
        </div>
      </div>
      <p className="text-center text-[11px] text-[#8A94A6]">
        Кадр — что происходит одновременно. Листай по порядку или нажми ▶ — игроки поедут по своим линиям.
      </p>
    </div>
  )
}

function FrameChip({
  label,
  ariaLabel,
  active,
  onClick,
}: {
  label: string
  ariaLabel?: string
  active: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={ariaLabel}
      aria-pressed={active}
      className={`flex h-8 min-w-8 items-center justify-center rounded-full px-2.5 text-xs font-semibold transition-colors ${
        active ? 'bg-accent-ice text-[#0B0F14]' : 'text-[#C9D1DC] hover:bg-white/10'
      }`}
    >
      {label}
    </button>
  )
}
