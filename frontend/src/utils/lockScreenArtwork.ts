// Branded artwork for the lock-screen player (workoutAudio.ts). The browser
// only lets a page fill the stock media widget -- but the artwork square is
// ours, so it is drawn here on the fly in IceLevel's own look: the phase in
// big condensed letters (ice = work, persimmon = rest), the exercise name,
// the round dots. Redrawn on every phase/round change, not every second.

const SIZE = 512
const COLORS = {
  bg: '#111827',
  card: '#171F30',
  ice: '#D7EFFF',
  persimmon: '#FF5C34',
  text: '#F3F6FA',
  muted: '#8A94A7',
  dot: 'rgba(255,255,255,0.18)',
}
const DISPLAY_FONT = 'Oswald, "Arial Narrow", system-ui, sans-serif'
const TEXT_FONT = 'Inter, system-ui, sans-serif'

export interface ArtworkState {
  // 'idle': the screensaver left on the lock screen between exercises.
  // 'set': a set done at the athlete's own pace (sets/reps exercises).
  // 'next': the few seconds between two warm-up / cool-down exercises.
  phase: 'work' | 'rest' | 'done' | 'idle' | 'set' | 'next'
  exerciseName: string
  // Seconds of the segment shown (work or rest length); omitted for 'done'.
  seconds?: number
  // Replaces the seconds line, e.g. "8–12 повт. · 60 кг" for a set.
  detail?: string
  rounds: number
  // Rounds fully finished so far.
  completedRounds: number
}

function wrapLines(ctx: CanvasRenderingContext2D, text: string, maxWidth: number, maxLines: number): string[] {
  const words = text.split(/\s+/)
  const lines: string[] = []
  let line = ''
  for (const word of words) {
    const candidate = line ? `${line} ${word}` : word
    if (ctx.measureText(candidate).width <= maxWidth || line === '') {
      line = candidate
    } else {
      lines.push(line)
      line = word
    }
  }
  if (line) {
    lines.push(line)
  }
  if (lines.length > maxLines) {
    const kept = lines.slice(0, maxLines)
    let last = kept[maxLines - 1]
    while (last.length > 1 && ctx.measureText(`${last}…`).width > maxWidth) {
      last = last.slice(0, -1)
    }
    kept[maxLines - 1] = `${last.trimEnd()}…`
    return kept
  }
  return lines
}

// Screensaver: big wordmark, a thin ice line, and what was done last.
function drawIdle(ctx: CanvasRenderingContext2D, lastExercise: string, pad: number): void {
  ctx.fillStyle = COLORS.ice
  ctx.font = `700 104px ${DISPLAY_FONT}`
  ctx.fillText('ICE', pad - 4, 230)
  const iceWidth = ctx.measureText('ICE').width
  ctx.fillStyle = COLORS.persimmon
  ctx.fillText('LEVEL', pad - 4 + iceWidth + 8, 230)
  ctx.fillStyle = COLORS.ice
  ctx.fillRect(pad, 262, 64, 4)
  ctx.fillStyle = COLORS.text
  ctx.font = `600 32px ${TEXT_FONT}`
  ctx.fillText('Тренировка идёт', pad, 320)
  if (lastExercise) {
    ctx.fillStyle = COLORS.muted
    ctx.font = `500 24px ${TEXT_FONT}`
    const lines = wrapLines(ctx, `Последнее: ${lastExercise}`, SIZE - pad * 2, 2)
    lines.forEach((text, index) => ctx.fillText(text, pad, SIZE - pad - 40 + index * 32 - (lines.length - 1) * 32))
  }
}

// Returns a PNG data URL, or null where canvas isn't available.
export function renderLockScreenArtwork(state: ArtworkState): string | null {
  const canvas = document.createElement('canvas')
  canvas.width = SIZE
  canvas.height = SIZE
  const ctx = canvas.getContext('2d')
  if (ctx === null) {
    return null
  }
  const accent = state.phase === 'rest' || state.phase === 'next' ? COLORS.persimmon : COLORS.ice

  // Background: dark card with a soft glow of the phase colour.
  const background = ctx.createLinearGradient(0, 0, 0, SIZE)
  background.addColorStop(0, COLORS.card)
  background.addColorStop(1, COLORS.bg)
  ctx.fillStyle = background
  ctx.fillRect(0, 0, SIZE, SIZE)
  const glow = ctx.createRadialGradient(SIZE * 0.85, SIZE * 0.1, 0, SIZE * 0.85, SIZE * 0.1, SIZE * 0.75)
  glow.addColorStop(
    0,
    state.phase === 'rest' || state.phase === 'next' ? 'rgba(255,92,52,0.35)' : 'rgba(215,239,255,0.22)',
  )
  glow.addColorStop(1, 'rgba(0,0,0,0)')
  ctx.fillStyle = glow
  ctx.fillRect(0, 0, SIZE, SIZE)

  const pad = 40
  ctx.textBaseline = 'alphabetic'

  if (state.phase === 'idle') {
    drawIdle(ctx, state.exerciseName, pad)
    try {
      return canvas.toDataURL('image/png')
    } catch {
      return null
    }
  }

  // Wordmark.
  ctx.fillStyle = COLORS.muted
  ctx.font = `600 22px ${TEXT_FONT}`
  ctx.letterSpacing = '6px'
  ctx.fillText('ICELEVEL', pad, pad + 22)
  ctx.letterSpacing = '0px'

  // Phase.
  const phaseLabel =
    state.phase === 'work'
      ? 'РАБОТА'
      : state.phase === 'rest'
        ? 'ОТДЫХ'
        : state.phase === 'set'
          ? 'ПОДХОД'
          : state.phase === 'next'
            ? 'ДАЛЕЕ'
            : 'ГОТОВО'
  ctx.fillStyle = accent
  ctx.font = `700 118px ${DISPLAY_FONT}`
  ctx.fillText(phaseLabel, pad - 4, 205)

  // Segment length, next to nothing else -- the progress bar under the
  // artwork shows the countdown itself.
  const detail = state.detail ?? (state.seconds !== undefined && state.phase !== 'done' ? `${state.seconds} сек` : null)
  if (detail !== null) {
    ctx.fillStyle = COLORS.text
    ctx.font = `600 40px ${DISPLAY_FONT}`
    ctx.fillText(detail, pad, 262)
  }

  // Exercise name, up to two lines.
  ctx.fillStyle = COLORS.text
  ctx.font = `600 34px ${TEXT_FONT}`
  const lines = wrapLines(ctx, state.exerciseName, SIZE - pad * 2, 2)
  lines.forEach((text, index) => ctx.fillText(text, pad, 340 + index * 44))

  // Round dots: done = filled ice, current = persimmon ring, rest = grey.
  if (state.rounds > 1) {
    const radius = 13
    const gap = 14
    const y = SIZE - pad - radius
    const maxDots = Math.min(state.rounds, 12)
    for (let index = 0; index < maxDots; index += 1) {
      const x = pad + radius + index * (radius * 2 + gap)
      ctx.beginPath()
      ctx.arc(x, y, radius, 0, Math.PI * 2)
      if (index < state.completedRounds) {
        ctx.fillStyle = COLORS.ice
        ctx.fill()
      } else if (index === state.completedRounds && state.phase !== 'done') {
        ctx.lineWidth = 4
        ctx.strokeStyle = COLORS.persimmon
        ctx.stroke()
      } else {
        ctx.lineWidth = 3
        ctx.strokeStyle = COLORS.dot
        ctx.stroke()
      }
    }
    ctx.fillStyle = COLORS.muted
    ctx.font = `600 24px ${TEXT_FONT}`
    ctx.textAlign = 'right'
    const shown = Math.min(state.completedRounds + (state.phase === 'done' ? 0 : 1), state.rounds)
    ctx.fillText(`${shown} / ${state.rounds}`, SIZE - pad, y + 9)
    ctx.textAlign = 'left'
  }

  try {
    return canvas.toDataURL('image/png')
  } catch {
    return null
  }
}
