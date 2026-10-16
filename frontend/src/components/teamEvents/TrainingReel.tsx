import { useEffect, useLayoutEffect, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent, type RefObject, type TouchEvent as ReactTouchEvent } from 'react'
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
// last screen says when and asks «Иду». What a player sees of the plan: the
// event page's plan, the push about a published plan (?reel=1), the home
// screen's team day card and the captain's «Как видит игрок». Works offline
// from the saved event (Б1).
//
// Review 14.10: a modal dialog (focus inside, the app underneath inert,
// Escape closes, ←/→ turn the page); swipes only on the drill itself, with
// vertical scrolling left to the browser; the scheme fits the box it's
// actually given.

interface ReelDrill {
  drill: TeamEventDrillRead
  sectionName: string
}

const HOLD_BEATS = 2
const SWIPE_MIN_PX = 50
const SECTION_SPLASH_MS = 900
const SEGMENTS_FIT = 6
const WEEKDAYS = ['ВС', 'ПН', 'ВТ', 'СР', 'ЧТ', 'ПТ', 'СБ']
// Between the cues under the title -- never broken onto a line of its own.
const KEYWORD_SEPARATOR = '\u00a0/\u00a0'

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

// While a modal is up: focus goes to `initial`, the app underneath (#root)
// is inert -- no tabbing or screen-reader wandering behind it -- and focus
// returns to where it was once the modal closes.
function useModalFocus(initial: RefObject<HTMLElement | null>, enabled = true) {
  useEffect(() => {
    if (!enabled) {
      return
    }
    const before = document.activeElement instanceof HTMLElement ? document.activeElement : null
    const root = document.getElementById('root')
    const wasInert = root?.inert ?? false
    if (root) {
      root.inert = true
    }
    initial.current?.focus()
    return () => {
      if (root) {
        root.inert = wasInert
      }
      before?.focus?.()
    }
  }, [initial, enabled])
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
  const online = useOnline()
  const [index, setIndex] = useState(0)
  const [splash, setSplash] = useState<string | null>(null)
  const [isDescriptionOpen, setIsDescriptionOpen] = useState(false)
  const atEnd = index >= drills.length
  const current = atEnd ? null : drills[index]
  const closeButton = useRef<HTMLButtonElement>(null)
  useModalFocus(closeButton)

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

  // Escape closes (the description first), ←/→ turn the page.
  const keys = useRef({ go, onClose, index, isDescriptionOpen })
  useEffect(() => {
    keys.current = { go, onClose, index, isDescriptionOpen }
  })
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const { go: turn, onClose: close, index: at, isDescriptionOpen: sheetOpen } = keys.current
      if (e.key === 'Escape') {
        e.preventDefault()
        if (sheetOpen) {
          setIsDescriptionOpen(false)
        } else {
          close()
        }
      } else if (!sheetOpen && e.key === 'ArrowRight') {
        e.preventDefault()
        turn(at + 1)
      } else if (!sheetOpen && e.key === 'ArrowLeft') {
        e.preventDefault()
        turn(at - 1)
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [])

  // Swipe left/right on the drill (not the header, not the segments). The
  // zone is touch-action: pan-y, so a vertical drag still scrolls a long
  // card while a horizontal one stays ours; a cancelled gesture (the system
  // took it over) is forgotten.
  // A finger is read from touch events: the browser may cancel the pointer
  // stream mid-gesture (pointercancel) while touchend still arrives. The
  // mouse (desktop) goes through pointer events.
  const swipeStart = useRef<{ x: number; y: number } | null>(null)
  function swipeEnd(x: number, y: number) {
    const start = swipeStart.current
    swipeStart.current = null
    if (start === null) {
      return
    }
    const dx = x - start.x
    const dy = y - start.y
    if (Math.abs(dx) >= SWIPE_MIN_PX && Math.abs(dx) > Math.abs(dy) * 1.5) {
      go(index + (dx < 0 ? 1 : -1))
    }
  }
  function onPointerDown(e: ReactPointerEvent) {
    if (e.pointerType !== 'touch') {
      swipeStart.current = { x: e.clientX, y: e.clientY }
    }
  }
  function onPointerUp(e: ReactPointerEvent) {
    if (e.pointerType !== 'touch') {
      swipeEnd(e.clientX, e.clientY)
    }
  }
  function onTouchStart(e: ReactTouchEvent) {
    const touch = e.touches[0]
    swipeStart.current = e.touches.length === 1 && touch ? { x: touch.clientX, y: touch.clientY } : null
  }
  function onTouchEnd(e: ReactTouchEvent) {
    const touch = e.changedTouches[0]
    if (touch) {
      swipeEnd(touch.clientX, touch.clientY)
    }
  }
  function onSwipeCancel() {
    swipeStart.current = null
  }

  return (
    <FullScreenOverlay className="flex flex-col bg-[#0B111C] text-[#F5F7FA]">
      <div
        role="dialog"
        aria-modal="true"
        aria-label="План тренировки"
        className={`mx-auto flex h-full w-full max-w-md flex-col gap-3 px-4 pb-[calc(1.25rem+env(safe-area-inset-bottom,0px))] ${
          // The «Нет связи» pill sits at the very top -- the header goes below it.
          online ? 'pt-[calc(0.75rem+env(safe-area-inset-top,0px))]' : 'pt-[calc(3.25rem+env(safe-area-inset-top,0px))]'
        }`}
      >
        <div className="flex h-11 items-center justify-between">
          <button
            ref={closeButton}
            type="button"
            aria-label="Закрыть"
            onClick={onClose}
            className="-ml-2 flex h-11 w-11 items-center justify-center rounded-full text-[#8A94A6] focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent-ice"
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

        <div
          data-testid="reel-swipe-zone"
          className="flex min-h-0 flex-1 touch-pan-y flex-col"
          onPointerDown={onPointerDown}
          onPointerUp={onPointerUp}
          onTouchStart={onTouchStart}
          onTouchEnd={onTouchEnd}
          onTouchCancel={onSwipeCancel}
        >
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
        </div>

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
        // No scheme: the description fills the box -- the title is right
        // below it already, not repeated here.
        <div className="flex min-h-0 flex-1 flex-col overflow-y-auto overscroll-contain rounded-2xl border border-white/10 bg-[#141C2B] p-5">
          <p className="whitespace-pre-line text-[15px] leading-relaxed text-[#C9D1DC]">
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
        {hasScheme && drill.description !== null ? (
          <button
            type="button"
            onClick={onOpenDescription}
            aria-label={`${drill.title} — описание`}
            className="line-clamp-2 text-left font-display text-[25px] font-bold uppercase leading-tight tracking-wide"
          >
            {drill.title}
            {/* 15.10: says the title opens the coach's description. */}
            <i className="ti ti-info-circle ml-2 align-[0.1em] text-lg text-accent-ice" aria-hidden="true" />
          </button>
        ) : (
          <h2 className="line-clamp-2 font-display text-[25px] font-bold uppercase leading-tight tracking-wide">
            {drill.title}
          </h2>
        )}
        {keywords.length > 0 && (
          <p className="text-xs uppercase tracking-[0.1em] text-[#9AA6B8]">{keywords.join(KEYWORD_SEPARATOR)}</p>
        )}
      </div>
    </div>
  )
}

// The box's real width / height, kept up to date -- the scheme's crop is
// fitted to it, not to a guess.
function useBoxAspect(ref: RefObject<HTMLElement | null>, fallback: number): number {
  const [aspect, setAspect] = useState(fallback)
  useLayoutEffect(() => {
    const element = ref.current
    if (element === null) {
      return
    }
    const measure = () => {
      const { width, height } = element.getBoundingClientRect()
      if (width > 0 && height > 0) {
        setAspect(Math.round((width / height) * 100) / 100)
      }
    }
    measure()
    if (typeof ResizeObserver === 'undefined') {
      return
    }
    const observer = new ResizeObserver(measure)
    observer.observe(element)
    return () => observer.disconnect()
  }, [ref])
  return aspect
}

// The scheme playing on a loop: the whole of it, each frame in turn (the
// players ride their arrows), a pause on the last, again. A tap pauses or
// resumes; with reduced motion nothing moves until ▶ is tapped. A scheme
// without arrows has nothing to play -- just the picture.
function SchemePlayer({ drill, reducedMotion }: { drill: TeamEventDrillRead; reducedMotion: boolean }) {
  const diagram = drill.diagram!
  const box = useRef<HTMLDivElement>(null)
  const aspect = useBoxAspect(box, 1.2)
  const frames = useMemo(() => diagramFrames(diagram), [diagram])
  const viewBox = useMemo(() => diagramViewBox(diagram, aspect), [diagram, aspect])
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

  const picture = (
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
  )

  return (
    <div
      ref={box}
      className="relative min-h-0 flex-1 overflow-hidden rounded-2xl bg-[#E9F4FA] shadow-[0_0_0_1px_rgba(215,239,255,0.25),0_18px_40px_-18px_rgba(0,0,0,0.8)]"
    >
      {steps > 0 ? (
        <button
          type="button"
          onClick={() => setPlaying((value) => !value)}
          aria-label={playing ? 'Пауза' : 'Воспроизвести схему'}
          className="absolute inset-0 flex h-full w-full items-center justify-center"
        >
          {picture}
        </button>
      ) : (
        <div role="img" aria-label={`Схема: ${drill.title}`} className="absolute inset-0 flex items-center justify-center">
          {picture}
        </div>
      )}
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
  const [markedGoing, setMarkedGoing] = useState(false)
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
  }, [accessToken, teamId, event.id, online])

  const imGoing = markedGoing || roster?.going.some((member) => member.user_id === user?.id) === true
  const goingCount = roster === null ? null : roster.going.length + (markedGoing && !roster.going.some((m) => m.user_id === user?.id) ? 1 : 0)
  const total = roster === null ? null : roster.going.length + roster.not_going.length + roster.unmarked.length
  // No roster yet (offline, never loaded): «Иду» shows, greyed, with why.
  const canMark = !imGoing && (roster === null || !roster.is_locked)

  async function markGoing() {
    if (accessToken === null) {
      return
    }
    setIsSaving(true)
    setError(null)
    try {
      await teamEventsApi.setMyAttendance(teamId, event.id, { status: 'going' }, accessToken)
    } catch {
      setError('Не получилось отметиться. Попробуйте ещё раз.')
      setIsSaving(false)
      return
    }
    // Marked: shown at once. The fresh roster (the count) is a bonus -- its
    // failure is no failure to mark.
    setMarkedGoing(true)
    setIsSaving(false)
    teamEventsApi
      .getAttendanceRoster(teamId, event.id, accessToken)
      .then(setRoster)
      .catch(() => undefined)
  }

  const day = startsAt.toLocaleDateString('ru-RU', { weekday: 'long' })
  const time = startsAt.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })

  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-3.5 px-3 text-center">
      <i className="ti ti-ice-skating text-5xl text-accent-ice" aria-hidden="true" />
      <h2 className="font-display text-[30px] font-bold leading-tight tracking-wide">УВИДИМСЯ НА ЛЬДУ</h2>
      <p className="text-[15px] leading-relaxed text-[#9AA6B8]">
        {day.charAt(0).toUpperCase() + day.slice(1)}, {time}
        {goingCount !== null && total !== null && (
          <>
            <br />
            Идут {goingCount} из {total}
          </>
        )}
      </p>
      {imGoing && <p className="text-sm text-accent-ice">Вы отметились: иду</p>}
      {canMark && (
        <>
          <button
            type="button"
            onClick={() => void markGoing()}
            disabled={isSaving || !online || roster === null}
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
  const closeButton = useRef<HTMLButtonElement>(null)
  // Focus into the sheet and back to the title when it closes; Escape is
  // handled by the reel (it closes this first).
  useEffect(() => {
    const before = document.activeElement instanceof HTMLElement ? document.activeElement : null
    closeButton.current?.focus()
    return () => before?.focus?.()
  }, [])

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
            ref={closeButton}
            type="button"
            onClick={onClose}
            aria-label="Закрыть описание"
            className="-mr-2 -mt-1 flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-[#8A94A6] focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent-ice"
          >
            <i className="ti ti-x text-xl" aria-hidden="true" />
          </button>
        </div>
        <p className="overflow-y-auto whitespace-pre-line text-sm leading-relaxed text-[#C9D1DC]">{drill.description}</p>
      </div>
    </div>
  )
}
