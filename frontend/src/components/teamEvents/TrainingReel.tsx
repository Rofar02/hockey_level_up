import { useEffect, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react'
import * as teamEventsApi from '../../api/teamEvents'
import { useAuth } from '../../hooks/useAuth'
import { useOnline } from '../../hooks/useNetworkStatus'
import type { TeamEventAttendanceRosterRead, TeamEventDrillRead, TeamEventRead } from '../../types/teamEvent'
import { formatMinutes, pluralRu, totalMinutes } from '../../utils/boardPlan'
import { PLAY_FRAME_MS, diagramFrames, diagramViewBox, isEmptyDiagram } from '../../utils/rinkDiagram'
import { NeedsNetworkHint } from '../OfflineBanner'
import { FullScreenOverlay } from '../ui/FullScreenOverlay'
import { RinkDiagram } from './diagram/RinkDiagram'

// The team training plan "like reels" (2026-10-13, В; mockup: "IceLevel —
// просмотр командной тренировки"): one drill per screen, its scheme playing
// by itself -- the whole scheme, then frame by frame, a short pause, again --
// zoomed to where the drill happens. Swipe or arrows for the next one; the
// last screen says when and asks «Иду». Opened from the event («Смотреть
// план»), from the push about a published plan (?reel=1) and from the home
// screen's team day card. Works offline from the saved event (Б1).

interface ReelDrill {
  drill: TeamEventDrillRead
  sectionName: string
}

// Box the scheme is drawn into (width / height) -- the crop is widened to it.
const SCHEME_ASPECT = 1.2
const HOLD_BEATS = 2
const SWIPE_MIN_PX = 50
const SECTION_SPLASH_MS = 900
const SEGMENTS_FIT = 6
const WEEKDAYS = ['ВС', 'ПН', 'ВТ', 'СР', 'ЧТ', 'ПТ', 'СБ']

function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(
    () => typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches === true,
  )
  useEffect(() => {
    const query = window.matchMedia?.('(prefers-reduced-motion: reduce)')
    if (!query) {
      return
    }
    const onChange = () => setReduced(query.matches)
    query.addEventListener('change', onChange)
    return () => query.removeEventListener('change', onChange)
  }, [])
  return reduced
}

function headerDate(startsAt: Date): string {
  const month = startsAt.toLocaleDateString('ru-RU', { month: 'short' }).replace('.', '').toUpperCase()
  const time = startsAt.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
  return `${WEEKDAYS[startsAt.getDay()]} ${startsAt.getDate()} ${month} · ${time}`
}

function pad2(n: number): string {
  return String(n).padStart(2, '0')
}

export function TrainingReel({
  teamId,
  teamName,
  event,
  onClose,
}: {
  teamId: string
  teamName: string
  event: TeamEventRead
  onClose: () => void
}) {
  const drills = useMemo<ReelDrill[]>(
    () =>
      (event.sections ?? []).flatMap((section) =>
        section.drills.map((drill) => ({ drill, sectionName: section.name })),
      ),
    [event.sections],
  )
  const reducedMotion = usePrefersReducedMotion()
  const [index, setIndex] = useState(0)
  const [splash, setSplash] = useState<string | null>(null)
  const [isDescriptionOpen, setIsDescriptionOpen] = useState(false)
  const atEnd = index >= drills.length
  const current = atEnd ? null : drills[index]

  const startsAt = new Date(event.starts_at)
  const minutes = totalMinutes(drills.map((item) => item.drill))

  function go(next: number) {
    const target = Math.max(0, Math.min(next, drills.length))
    if (target === index) {
      return
    }
    const fromSection = drills[index]?.sectionName
    const toSection = drills[target]?.sectionName
    if (toSection !== undefined && fromSection !== undefined && toSection !== fromSection) {
      setSplash(toSection)
    }
    setIsDescriptionOpen(false)
    setIndex(target)
  }

  useEffect(() => {
    if (splash === null) {
      return
    }
    const timer = setTimeout(() => setSplash(null), reducedMotion ? SECTION_SPLASH_MS / 2 : SECTION_SPLASH_MS)
    return () => clearTimeout(timer)
  }, [splash, reducedMotion])

  // Swipe left/right anywhere on the drill.
  const swipeStart = useRef<{ x: number; y: number } | null>(null)
  function onPointerDown(e: ReactPointerEvent) {
    swipeStart.current = { x: e.clientX, y: e.clientY }
  }
  function onPointerUp(e: ReactPointerEvent) {
    const start = swipeStart.current
    swipeStart.current = null
    if (start === null) {
      return
    }
    const dx = e.clientX - start.x
    const dy = e.clientY - start.y
    if (Math.abs(dx) >= SWIPE_MIN_PX && Math.abs(dx) > Math.abs(dy) * 1.5) {
      go(index + (dx < 0 ? 1 : -1))
    }
  }

  return (
    <FullScreenOverlay className="flex flex-col bg-[#0B111C] text-[#F5F7FA]">
      <div
        className="mx-auto flex h-full w-full max-w-md flex-col gap-3 px-4 pb-[calc(1.25rem+env(safe-area-inset-bottom,0px))] pt-[calc(0.75rem+env(safe-area-inset-top,0px))]"
        onPointerDown={onPointerDown}
        onPointerUp={onPointerUp}
      >
        <div className="flex h-11 items-center justify-between">
          <button
            type="button"
            aria-label="Закрыть"
            onClick={onClose}
            className="-ml-2 flex h-11 w-11 items-center justify-center text-[#8A94A6]"
          >
            <i className="ti ti-x text-2xl" aria-hidden="true" />
          </button>
          <span className="min-w-0 truncate px-2 font-display text-[13px] tracking-[0.12em] text-[#8A94A6]">
            {teamName.toUpperCase()} · {headerDate(startsAt)}
          </span>
          <span className="w-11" aria-hidden="true" />
        </div>

        <div className="flex flex-col items-center gap-1 border-y-2 border-accent-ice/55 py-2.5 text-center">
          <h1 className="font-display text-[30px] font-bold leading-none tracking-[0.05em]">ПЛАН ТРЕНИРОВКИ</h1>
          <p className="text-xs uppercase tracking-[0.1em] text-[#A9C7E0]">
            {drills.length} {pluralRu(drills.length, ['упражнение', 'упражнения', 'упражнений'])}
            {minutes !== null && ` · ${formatMinutes(minutes)}`}
            {event.host_team_name != null && ` · вместе с «${event.host_team_name}»`}
          </p>
        </div>

        {current !== null ? (
          <DrillScreen
            key={current.drill.id}
            item={current}
            number={index + 1}
            total={drills.length}
            reducedMotion={reducedMotion}
            onPrev={() => go(index - 1)}
            onNext={() => go(index + 1)}
            onOpenDescription={() => setIsDescriptionOpen(true)}
          />
        ) : (
          <EndScreen teamId={teamId} event={event} startsAt={startsAt} onRestart={() => go(0)} />
        )}

        {drills.length > 0 && <Segments drills={drills} index={index} onPick={go} />}
      </div>

      {splash !== null && (
        <div
          aria-live="polite"
          className={`pointer-events-none fixed inset-0 z-[60] flex items-center justify-center bg-[#0B111C]/85 ${
            reducedMotion ? '' : 'animate-[reel-splash_0.25s_ease-out]'
          }`}
        >
          <span className="font-display text-[34px] font-bold uppercase tracking-[0.08em] text-accent-persimmon">
            {splash}
          </span>
        </div>
      )}

      {isDescriptionOpen && current !== null && (
        <DescriptionSheet drill={current.drill} onClose={() => setIsDescriptionOpen(false)} />
      )}
    </FullScreenOverlay>
  )
}

function DrillScreen({
  item,
  number,
  total,
  reducedMotion,
  onPrev,
  onNext,
  onOpenDescription,
}: {
  item: ReelDrill
  number: number
  total: number
  reducedMotion: boolean
  onPrev: () => void
  onNext: () => void
  onOpenDescription: () => void
}) {
  const { drill, sectionName } = item
  const hasScheme = drill.diagram !== null && !isEmptyDiagram(drill.diagram)
  const keywords = drill.keywords ?? []

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3">
      <div className="flex items-center justify-between">
        <span className="font-display text-xs font-semibold tracking-[0.16em] text-accent-persimmon">
          {sectionName.toUpperCase()}
        </span>
        {drill.duration_minutes !== null && (
          <span className="font-display text-xs tracking-[0.1em] text-[#8A94A6]">{drill.duration_minutes} МИН</span>
        )}
      </div>

      {hasScheme ? (
        <SchemePlayer drill={drill} reducedMotion={reducedMotion} />
      ) : (
        <div className="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto rounded-2xl border border-white/10 bg-[#141C2B] p-5">
          <p className="font-display text-xl font-semibold uppercase tracking-wide">{drill.title}</p>
          <p className="whitespace-pre-line text-sm leading-relaxed text-[#C9D1DC]">
            {drill.description ?? 'Тренер не добавил описание — подробности на льду.'}
          </p>
        </div>
      )}

      <div className="flex flex-col items-center gap-1.5 text-center">
        <div className="flex w-full items-center justify-between">
          <button
            type="button"
            onClick={onPrev}
            disabled={number === 1}
            aria-label="Предыдущее упражнение"
            className="flex h-11 w-11 items-center justify-center rounded-full bg-white/5 text-accent-ice disabled:opacity-30"
          >
            <i className="ti ti-chevron-left text-xl" aria-hidden="true" />
          </button>
          <span className="font-display text-2xl font-semibold tracking-[0.06em] text-[#A9D6F5]">
            УПРАЖНЕНИЕ {number} / {total}
          </span>
          <button
            type="button"
            onClick={onNext}
            aria-label="Следующее упражнение"
            className="flex h-11 w-11 items-center justify-center rounded-full bg-white/5 text-accent-ice"
          >
            <i className="ti ti-chevron-right text-xl" aria-hidden="true" />
          </button>
        </div>
        <button
          type="button"
          onClick={onOpenDescription}
          disabled={drill.description === null}
          aria-label={drill.description !== null ? `${drill.title} — описание` : undefined}
          className="font-display text-[25px] font-bold uppercase leading-tight tracking-wide disabled:cursor-default"
        >
          {drill.title}
        </button>
        {keywords.length > 0 && (
          <p className="text-xs uppercase tracking-[0.1em] text-[#9AA6B8]">{keywords.join('  /  ')}</p>
        )}
      </div>
    </div>
  )
}

// The scheme playing on a loop: the whole of it, each frame in turn (the
// players ride their arrows), a pause on the last, again. A tap pauses or
// resumes; with reduced motion nothing moves until ▶ is tapped.
function SchemePlayer({ drill, reducedMotion }: { drill: TeamEventDrillRead; reducedMotion: boolean }) {
  const diagram = drill.diagram!
  const frames = useMemo(() => diagramFrames(diagram), [diagram])
  const viewBox = useMemo(() => diagramViewBox(diagram, SCHEME_ASPECT), [diagram])
  const [playing, setPlaying] = useState(!reducedMotion && frames.length > 0)
  // Position in the loop: 0 = whole scheme, 1..k = frame k, then the hold.
  const [beat, setBeat] = useState(0)
  const [loop, setLoop] = useState(0)
  const steps = frames.length
  const loopLength = 1 + steps + HOLD_BEATS

  useEffect(() => {
    if (!playing || steps === 0) {
      return
    }
    const timer = setTimeout(() => {
      setBeat((current) => {
        const next = (current + 1) % loopLength
        if (next === 0) {
          setLoop((value) => value + 1)
        }
        return next
      })
    }, beat === 0 ? PLAY_FRAME_MS * 0.8 : PLAY_FRAME_MS)
    return () => clearTimeout(timer)
  }, [playing, beat, steps, loopLength])

  const frameIndex = beat === 0 ? null : Math.min(beat, steps) - 1
  const frame = frameIndex === null ? null : frames[frameIndex]
  // A new key each time a frame starts (not during the hold): RinkDiagram
  // replays the ride on every change.
  const playKey = playing && beat >= 1 && beat <= steps ? loop * 100 + beat : null
  const label = frame === null ? 'ВСЯ СХЕМА' : `ТАКТ ${(frameIndex ?? 0) + 1} / ${steps}`

  function toggle() {
    if (steps === 0) {
      return
    }
    setPlaying((value) => !value)
  }

  return (
    <div className="relative min-h-0 flex-1 overflow-hidden rounded-2xl bg-[#E9F4FA] shadow-[0_0_0_1px_rgba(215,239,255,0.25),0_18px_40px_-18px_rgba(0,0,0,0.8)]">
      <button
        type="button"
        onClick={toggle}
        aria-label={playing ? 'Пауза' : 'Воспроизвести схему'}
        className="absolute inset-0 flex h-full w-full items-center justify-center"
      >
        <RinkDiagram
          diagram={diagram}
          viewBox={viewBox}
          frame={frame}
          playKey={playKey}
          moveTokens
          className={`h-full w-full transition-opacity duration-500 ${
            playing && frame === null && steps > 0 ? 'opacity-60' : 'opacity-100'
          }`}
        />
      </button>
      {steps > 0 && (
        <div className="pointer-events-none absolute bottom-2.5 left-2.5 flex items-center gap-2 rounded-full bg-[#0B111C]/80 px-2.5 py-1.5">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="#D7EFFF" aria-hidden="true">
            <path d={playing ? 'M7 5h4v14H7zM13 5h4v14h-4z' : 'M7 4l13 8-13 8z'} />
          </svg>
          <span className="font-display text-xs tracking-[0.1em] text-accent-ice" aria-live="off">
            {label}
          </span>
        </div>
      )}
    </div>
  )
}

function Segments({ drills, index, onPick }: { drills: ReelDrill[]; index: number; onPick: (index: number) => void }) {
  const scroller = useRef<HTMLDivElement>(null)
  const scrolls = drills.length > SEGMENTS_FIT

  useEffect(() => {
    if (!scrolls) {
      return
    }
    const active = scroller.current?.querySelector<HTMLElement>('[aria-selected="true"]')
    active?.scrollIntoView({ block: 'nearest', inline: 'center', behavior: 'smooth' })
  }, [index, scrolls])

  return (
    <div
      ref={scroller}
      role="tablist"
      aria-label="Упражнения"
      className={scrolls ? 'flex gap-2 overflow-x-auto overscroll-x-contain pb-1' : 'grid gap-2'}
      style={scrolls ? undefined : { gridTemplateColumns: `repeat(${drills.length}, minmax(0, 1fr))` }}
    >
      {drills.map((item, k) => {
        const selected = k === index
        const done = k < index
        return (
          <button
            key={item.drill.id}
            type="button"
            role="tab"
            aria-selected={selected}
            aria-label={`Упражнение ${k + 1}: ${item.drill.title}`}
            onClick={() => onPick(k)}
            className={`h-11 shrink-0 rounded-[10px] border font-display text-base font-semibold tracking-wide ${
              scrolls ? 'w-12' : ''
            } ${
              selected
                ? 'border-[#A9D6F5] bg-[#A9D6F5] text-[#0B111C]'
                : done
                  ? 'border-accent-ice/15 bg-[#A9D6F5]/20 text-accent-ice'
                  : 'border-accent-ice/15 bg-[#141C2B] text-[#6B7588]'
            }`}
          >
            {pad2(k + 1)}
          </button>
        )
      })}
    </div>
  )
}

function EndScreen({
  teamId,
  event,
  startsAt,
  onRestart,
}: {
  teamId: string
  event: TeamEventRead
  startsAt: Date
  onRestart: () => void
}) {
  const { accessToken, user } = useAuth()
  const online = useOnline()
  const [roster, setRoster] = useState<TeamEventAttendanceRosterRead | null>(null)
  const [isSaving, setIsSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (accessToken === null) {
      return
    }
    let cancelled = false
    teamEventsApi
      .getAttendanceRoster(teamId, event.id, accessToken)
      .then((result) => {
        if (!cancelled) {
          setRoster(result)
        }
      })
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
  }, [accessToken, teamId, event.id])

  const going = roster?.going.length ?? null
  const total = roster === null ? null : roster.going.length + roster.not_going.length + roster.unmarked.length
  const imGoing = roster?.going.some((member) => member.user_id === user?.id) === true
  const canMark = roster !== null && !roster.is_locked && !imGoing

  async function markGoing() {
    if (accessToken === null) {
      return
    }
    setIsSaving(true)
    setError(null)
    try {
      await teamEventsApi.setMyAttendance(teamId, event.id, { status: 'going' }, accessToken)
      setRoster(await teamEventsApi.getAttendanceRoster(teamId, event.id, accessToken))
    } catch {
      setError('Не получилось отметиться. Попробуйте ещё раз.')
    } finally {
      setIsSaving(false)
    }
  }

  const day = startsAt.toLocaleDateString('ru-RU', { weekday: 'long' })
  const time = startsAt.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })

  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-3.5 px-3 text-center">
      <i className="ti ti-ice-skating text-5xl text-accent-ice" aria-hidden="true" />
      <h2 className="font-display text-[30px] font-bold leading-tight tracking-wide">УВИДИМСЯ НА ЛЬДУ</h2>
      <p className="text-[15px] leading-relaxed text-[#9AA6B8]">
        {day.charAt(0).toUpperCase() + day.slice(1)}, {time}
        {going !== null && total !== null && (
          <>
            <br />
            Идут {going} из {total}
          </>
        )}
      </p>
      {imGoing && <p className="text-sm text-accent-ice">Ты отметился: иду</p>}
      {canMark && (
        <>
          <button
            type="button"
            onClick={() => void markGoing()}
            disabled={isSaving || !online}
            className="mt-2 h-[54px] w-full rounded-[14px] bg-accent-persimmon text-base font-semibold text-[#111827] disabled:opacity-50"
          >
            {isSaving ? 'Отмечаем...' : 'Иду'}
          </button>
          <NeedsNetworkHint className="justify-center" />
        </>
      )}
      {error !== null && (
        <p role="alert" className="text-sm text-red-400">
          {error}
        </p>
      )}
      <button type="button" onClick={onRestart} className="h-11 px-4 text-sm text-[#A9D6F5]">
        Посмотреть ещё раз
      </button>
    </div>
  )
}

function DescriptionSheet({ drill, onClose }: { drill: TeamEventDrillRead; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-[60] flex flex-col justify-end bg-black/50" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-label={drill.title}
        onClick={(e) => e.stopPropagation()}
        className="mx-auto flex max-h-[70svh] w-full max-w-md flex-col gap-3 rounded-t-2xl border-t border-white/10 bg-[#141C2B] px-5 pb-[calc(1.25rem+env(safe-area-inset-bottom,0px))] pt-4"
      >
        <div className="flex items-start justify-between gap-3">
          <h3 className="font-display text-xl font-semibold uppercase tracking-wide">{drill.title}</h3>
          <button
            type="button"
            onClick={onClose}
            aria-label="Закрыть описание"
            className="-mr-2 -mt-1 flex h-11 w-11 shrink-0 items-center justify-center text-[#8A94A6]"
          >
            <i className="ti ti-x text-xl" aria-hidden="true" />
          </button>
        </div>
        <p className="overflow-y-auto whitespace-pre-line text-sm leading-relaxed text-[#C9D1DC]">{drill.description}</p>
      </div>
    </div>
  )
}
