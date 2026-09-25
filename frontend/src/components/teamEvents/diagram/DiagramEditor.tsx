import { useEffect, useRef, useState, type PointerEvent as ReactPointerEvent, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { Button } from '../../ui/Button'
import { FormError } from '../../ui/FormError'
import { RinkDiagram } from './RinkDiagram'
import { useSuppressCoachmarks } from '../../../hooks/useSuppressCoachmarks'
import { lockBodyScroll, unlockBodyScroll } from '../../../utils/bodyScrollLock'
import { DIAGRAM_ARROW_LABELS, DIAGRAM_POSITION_LABELS, DIAGRAM_POSITION_LETTERS } from '../../../types/teamEvent'
import type {
  DiagramArrow,
  DiagramArrowKind,
  DiagramPoint,
  DiagramPosition,
  DiagramToken,
  DrillDiagram,
} from '../../../types/teamEvent'
import {
  RINK_HEIGHT,
  RINK_WIDTH,
  MAX_ARROW_STEP,
  TOKEN_RADIUS,
  arrowSteps,
  clamp01,
  emptyDiagram,
  isEmptyDiagram,
  newDiagramId,
  smoothStroke,
  snapToGoal,
  strokeLength,
  toRink,
} from '../../../utils/rinkDiagram'

type Selection = { type: 'token'; id: string } | { type: 'arrow'; id: string } | null

// Waiting for the tap that ends a new arrow, which starts at a token
// (and follows it) or at the end of an existing arrow (a chained move).
type Drawing = { kind: DiagramArrowKind; fromToken: string | null; start: DiagramPoint } | null

interface DragState {
  tokenId: string
  before: DrillDiagram
  moved: boolean
}

const ARROW_KINDS: DiagramArrowKind[] = ['pass', 'repass', 'shot', 'skate_puck', 'skate']

// Full-screen scheme editor for one drill (captain only). Everything is
// local until "Сохранить" sends the whole diagram in one PUT.
export function DiagramEditor({
  title,
  initial,
  onSave,
  onClose,
}: {
  title: string
  initial: DrillDiagram | null
  onSave: (diagram: DrillDiagram | null) => Promise<void>
  onClose: () => void
}) {
  const svgRef = useRef<SVGSVGElement>(null)
  const [diagram, setDiagram] = useState<DrillDiagram>(initial ?? emptyDiagram())
  const [past, setPast] = useState<DrillDiagram[]>([])
  const [selection, setSelection] = useState<Selection>(null)
  const [drawing, setDrawing] = useState<Drawing>(null)
  const [drag, setDrag] = useState<DragState | null>(null)
  // Raw pointer samples of the arrow being drawn with a finger.
  const [stroke, setStroke] = useState<DiagramPoint[] | null>(null)
  const [isAddingPlayer, setIsAddingPlayer] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)

  useEffect(() => {
    lockBodyScroll()
    return unlockBodyScroll
  }, [])
  useSuppressCoachmarks(true)

  function commit(next: DrillDiagram) {
    setPast((previous) => [...previous, diagram])
    setDiagram(next)
    // Any edit makes a "Схема пустая" (or failed-save) message stale.
    setSaveError(null)
  }

  function undo() {
    const previous = past[past.length - 1]
    if (previous === undefined) {
      return
    }
    setPast(past.slice(0, -1))
    setDiagram(previous)
    setSelection(null)
    setDrawing(null)
  }

  // Through the SVG's own screen transform, not its bounding box: on some
  // phone sizes the <svg> box is taller than the drawn rink (letterboxed),
  // and box-relative maths put every point a few pixels off.
  function pointFromEvent(event: { clientX: number; clientY: number }): DiagramPoint | null {
    const svg = svgRef.current
    const matrix = svg?.getScreenCTM()
    if (svg == null || matrix == null) {
      return null
    }
    const inRink = new DOMPoint(event.clientX, event.clientY).matrixTransform(matrix.inverse())
    return { x: clamp01(inRink.x / RINK_WIDTH), y: clamp01(inRink.y / RINK_HEIGHT) }
  }

  // New tokens land near the centre, nudged so they don't stack exactly.
  function freeSpot(): DiagramPoint {
    const offset = (diagram.tokens.length % 6) * 0.05
    return { x: clamp01(0.4 + offset), y: 0.5 }
  }

  function addToken(token: Omit<DiagramToken, 'id' | 'x' | 'y'>) {
    const id = newDiagramId()
    commit({ ...diagram, tokens: [...diagram.tokens, { ...token, id, ...freeSpot() }] })
    setSelection({ type: 'token', id })
    setDrawing(null)
  }

  // A stroke ending on (or a tap on) another token snaps to its centre --
  // a pass to a teammate lands exactly on him.
  function snapToToken(point: DiagramPoint): DiagramPoint {
    const at = toRink(point)
    const hit = diagram.tokens.find((token) => {
      if (token.id === drawing?.fromToken) {
        return false
      }
      const center = toRink(token)
      return Math.hypot(center.x - at.x, center.y - at.y) <= TOKEN_RADIUS.own + 3
    })
    return hit !== undefined ? { x: hit.x, y: hit.y } : point
  }

  // A tap (barely any movement) makes a straight arrow to that point, like
  // before; a drawn path becomes a curve through its simplified points.
  function finishStroke(points: DiagramPoint[]) {
    if (drawing === null || points.length === 0) {
      return
    }
    // A shot flies straight and ends in the goal when aimed near one.
    const isShot = drawing.kind === 'shot'
    const end = isShot ? snapToGoal(points[points.length - 1]) : snapToToken(points[points.length - 1])
    const isTap = strokeLength(points) < 12
    // A tap on the player the arrow starts from isn't a destination --
    // stay in drawing mode instead of making a zero-length arrow.
    if (isTap && strokeLength([drawing.start, end]) < TOKEN_RADIUS.own + 3) {
      return
    }
    const via = isTap || isShot ? [] : smoothStroke([drawing.start, ...points.slice(0, -1), end]).slice(1, -1)
    finishArrow(end, via)
  }

  function finishArrow(end: DiagramPoint, via: DiagramPoint[] = []) {
    if (drawing === null) {
      return
    }
    const draftArrow: DiagramArrow = {
      id: newDiagramId(),
      kind: drawing.kind,
      from_token: drawing.fromToken,
      start: drawing.start,
      via,
      end,
    }
    // Store the step it would get anyway (1 from a player, previous + 1 when
    // continuing an arrow), so later edits elsewhere never renumber it.
    const step = arrowSteps({ ...diagram, arrows: [...diagram.arrows, draftArrow] }).get(draftArrow.id) ?? 1
    const arrow: DiagramArrow = { ...draftArrow, step }
    commit({ ...diagram, arrows: [...diagram.arrows, arrow] })
    setDrawing(null)
    // Select the new arrow so the next move can chain straight from its end.
    setSelection({ type: 'arrow', id: arrow.id })
  }

  function startArrow(kind: DiagramArrowKind) {
    if (selection === null) {
      return
    }
    if (selection.type === 'token') {
      const token = diagram.tokens.find((candidate) => candidate.id === selection.id)
      if (token !== undefined) {
        setDrawing({ kind, fromToken: token.id, start: { x: token.x, y: token.y } })
      }
    } else {
      const arrow = diagram.arrows.find((candidate) => candidate.id === selection.id)
      if (arrow !== undefined) {
        setDrawing({ kind, fromToken: null, start: arrow.end })
      }
    }
  }

  function changeStep(arrowId: string, delta: -1 | 1) {
    const current = arrowSteps(diagram).get(arrowId) ?? 1
    const next = Math.min(MAX_ARROW_STEP, Math.max(1, current + delta))
    if (next === current) {
      return
    }
    commit({
      ...diagram,
      arrows: diagram.arrows.map((arrow) => (arrow.id === arrowId ? { ...arrow, step: next } : arrow)),
    })
  }

  function removeSelected() {
    if (selection === null) {
      return
    }
    if (selection.type === 'token') {
      commit({
        tokens: diagram.tokens.filter((token) => token.id !== selection.id),
        arrows: diagram.arrows.filter((arrow) => arrow.from_token !== selection.id),
      })
    } else {
      commit({ ...diagram, arrows: diagram.arrows.filter((arrow) => arrow.id !== selection.id) })
    }
    setSelection(null)
  }

  // Keeps move/up events coming to the rink even when the finger leaves a
  // token. Throws for a pointer that's already gone -- harmless, the stroke
  // or drag still works from the events that do arrive.
  function capturePointer(pointerId: number) {
    try {
      svgRef.current?.setPointerCapture(pointerId)
    } catch {
      // Pointer already released.
    }
  }

  function beginStroke(event: { clientX: number; clientY: number; pointerId: number }) {
    const point = pointFromEvent(event)
    if (point !== null) {
      setStroke([point])
      capturePointer(event.pointerId)
    }
  }

  function handleBackgroundPointerDown(event: ReactPointerEvent<SVGSVGElement>) {
    if (drawing !== null) {
      beginStroke(event)
      return
    }
    setSelection(null)
  }

  function handleTokenPointerDown(token: DiagramToken, event: ReactPointerEvent<SVGGElement>) {
    event.stopPropagation()
    if (drawing !== null) {
      // Starting the stroke on the player himself is the natural gesture
      // (draw from the player); a tap on another token ends there.
      beginStroke(event)
      return
    }
    setSelection({ type: 'token', id: token.id })
    setDrag({ tokenId: token.id, before: diagram, moved: false })
    capturePointer(event.pointerId)
  }

  function handleArrowPointerDown(arrow: DiagramArrow, event: ReactPointerEvent<SVGPathElement>) {
    event.stopPropagation()
    if (drawing !== null) {
      beginStroke(event)
      return
    }
    setSelection({ type: 'arrow', id: arrow.id })
  }

  function handlePointerMove(event: ReactPointerEvent<SVGSVGElement>) {
    if (stroke !== null) {
      const point = pointFromEvent(event)
      const last = stroke[stroke.length - 1]
      // Skip sub-pixel jitter -- ~1.5 rink units between samples is plenty.
      if (point !== null && strokeLength([last, point]) >= 1.5) {
        setStroke([...stroke, point])
      }
      return
    }
    if (drag === null) {
      return
    }
    const point = pointFromEvent(event)
    if (point === null) {
      return
    }
    // Live update without history -- the whole drag becomes one undo step
    // on pointer up. Arrows starting at the token move with it.
    setDiagram((current) => ({
      tokens: current.tokens.map((token) => (token.id === drag.tokenId ? { ...token, ...point } : token)),
      arrows: current.arrows.map((arrow) =>
        arrow.from_token === drag.tokenId ? { ...arrow, start: point } : arrow,
      ),
    }))
    if (!drag.moved) {
      setDrag({ ...drag, moved: true })
    }
  }

  function handlePointerUp(event: ReactPointerEvent<SVGSVGElement>) {
    if (stroke !== null) {
      setStroke(null)
      // A cancelled gesture (the browser took the touch over) carries 0,0
      // coordinates -- using them sent the arrow flying to the top corner.
      // Drop the stroke and stay in drawing mode instead.
      if (event.type === 'pointercancel') {
        return
      }
      const point = pointFromEvent(event)
      finishStroke(point !== null ? [...stroke, point] : stroke)
      return
    }
    if (drag?.moved === true) {
      setPast((previous) => [...previous, drag.before])
    }
    setDrag(null)
  }

  async function handleSave() {
    // An empty rink saves nothing a player could see -- say so instead of
    // silently closing (clearing an existing scheme is still allowed).
    if (isEmptyDiagram(diagram) && initial === null) {
      setSaveError('Схема пустая — добавь хотя бы одну фишку кнопкой «Свой» внизу.')
      return
    }
    setIsSaving(true)
    setSaveError(null)
    try {
      await onSave(isEmptyDiagram(diagram) ? null : diagram)
      onClose()
    } catch {
      setSaveError('Не удалось сохранить схему. Попробуй ещё раз.')
    } finally {
      setIsSaving(false)
    }
  }

  const selectedToken =
    selection?.type === 'token' ? diagram.tokens.find((token) => token.id === selection.id) ?? null : null
  // A puck doesn't skate or pass on its own -- only players get arrows.
  const canDrawFromSelection = selection?.type === 'arrow' || (selectedToken !== null && selectedToken.kind !== 'puck')
  // Where the action is: the palette moves to the top of the rink when it
  // would otherwise cover the selected player (it wraps to two rows on a
  // narrow phone and hides the whole bottom zone).
  const selectedArrow = selection?.type === 'arrow' ? diagram.arrows.find((arrow) => arrow.id === selection.id) : undefined
  const focusY = selectedToken?.y ?? selectedArrow?.end.y ?? 0
  const paletteAtTop = focusY > 0.55

  // Portaled to <body>: rendered in place it sits inside the page's own
  // stacking context and BottomNav (z-40, fixed) paints over its toolbar.
  return createPortal(
    // touch-none on the whole screen: the browser must never treat a stroke
    // as a scroll/zoom gesture and cancel it half-way.
    <div className="fixed inset-0 z-50 flex touch-none flex-col bg-[#0B0F14]" role="dialog" aria-modal="true" aria-label={`Схема: ${title}`}>
      <header className="flex shrink-0 items-center gap-3 border-b border-white/10 px-4 py-3">
        <button type="button" onClick={onClose} className="text-sm text-[#8A94A6] transition-colors hover:text-[#F5F7FA]">
          Отмена
        </button>
        <p className="min-w-0 flex-1 truncate text-center text-sm font-semibold text-[#F5F7FA]">{title}</p>
        <Button type="button" onClick={handleSave} isLoading={isSaving} className="!px-3 !py-1.5 !text-xs">
          Сохранить
        </Button>
      </header>

      {/* Above the rink, never on it: while drawing, this strip swaps the
          legend for the instructions -- a bar over the rink could cover the
          very spot to tap (the top goal for a shot). Same height either way
          so the rink doesn't jump when the mode changes. */}
      <div className="flex min-h-[52px] shrink-0 items-center px-4 pt-2">
        {drawing !== null ? (
          <div className="flex w-full items-center gap-3 rounded-xl border border-accent-ice/30 bg-accent-ice/10 py-1 pl-3 pr-1">
            <ArrowSwatch kind={drawing.kind} />
            <p className="min-w-0 flex-1 text-xs leading-snug text-[#F5F7FA]">
              {drawing.kind === 'shot'
                ? 'Бросок: коснись ворот — стрелка встанет точно в створ'
                : `${DIAGRAM_ARROW_LABELS[drawing.kind]}: веди пальцем по траектории или коснись точки — будет прямая`}
            </p>
            <button
              type="button"
              onClick={() => setDrawing(null)}
              aria-label="Отменить стрелку"
              className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg text-[#C9D1DC] transition-colors hover:bg-white/10"
            >
              <i className="ti ti-x" aria-hidden="true" />
            </button>
          </div>
        ) : (
          <div className="flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-[#8A94A6]">
            {ARROW_KINDS.map((kind) => (
              <span key={kind} className="flex items-center gap-1">
                <ArrowSwatch kind={kind} />
                {DIAGRAM_ARROW_LABELS[kind].toLowerCase()}
              </span>
            ))}
            <span className="flex items-center gap-1">
              <StepSwatch />
              такт: одинаковые — одновременно
            </span>
          </div>
        )}
      </div>
      <FormError message={saveError} />

      <div className="relative flex min-h-0 flex-1 items-center justify-center p-3">
        <RinkDiagram
          ref={svgRef}
          diagram={diagram}
          className="h-full max-h-full w-auto max-w-full rounded-[18px]"
          selectedTokenId={selection?.type === 'token' ? selection.id : null}
          selectedArrowId={selection?.type === 'arrow' ? selection.id : null}
          onBackgroundPointerDown={handleBackgroundPointerDown}
          onTokenPointerDown={handleTokenPointerDown}
          onArrowPointerDown={handleArrowPointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
          draft={drawing !== null && stroke !== null ? { kind: drawing.kind, points: [drawing.start, ...stroke] } : null}
        />

        {isEmptyDiagram(diagram) && (
          <div className="pointer-events-none absolute inset-x-8 top-1/2 flex -translate-y-1/2 flex-col items-center gap-2 rounded-2xl bg-[#0B0F14]/85 p-4 text-center backdrop-blur">
            <i className="ti ti-hand-finger text-2xl text-accent-ice" aria-hidden="true" />
            <p className="text-sm font-medium text-[#F5F7FA]">Добавь игрока кнопкой «Свой» внизу</p>
            <p className="text-xs text-[#8A94A6]">
              Потом тяни фишку по катку и рисуй от неё стрелки — пальцем по траектории.
            </p>
          </div>
        )}

        {drawing === null && (
          selection !== null && (
            <FloatingBar atTop={paletteAtTop}>
              {canDrawFromSelection &&
                ARROW_KINDS.map((kind) => (
                  <PaletteButton key={kind} label={DIAGRAM_ARROW_LABELS[kind]} onClick={() => startArrow(kind)}>
                    <ArrowSwatch kind={kind} />
                  </PaletteButton>
                ))}
              {selection.type === 'arrow' && (
                <StepControl
                  step={arrowSteps(diagram).get(selection.id) ?? 1}
                  onChange={(delta) => changeStep(selection.id, delta)}
                />
              )}
              <PaletteButton label={selection.type === 'token' ? 'Убрать фишку' : 'Убрать стрелку'} onClick={removeSelected}>
                <i className="ti ti-trash text-[#8A94A6]" aria-hidden="true" />
              </PaletteButton>
            </FloatingBar>
          )
        )}
      </div>

      <nav className="flex shrink-0 gap-1.5 border-t border-white/10 bg-[#121820] px-3 pb-[calc(12px+env(safe-area-inset-bottom,0px))] pt-2.5">
        <ToolbarButton icon="ti-user" label="Свой" onClick={() => setIsAddingPlayer(true)} />
        <ToolbarButton icon="ti-user-x" label="Соперник" onClick={() => addToken({ kind: 'opponent' })} />
        <ToolbarButton
          icon={
            <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true">
              <ellipse cx="12" cy="12" rx="9" ry="5" fill="currentColor" />
            </svg>
          }
          label="Шайба"
          onClick={() => addToken({ kind: 'puck' })}
        />
        <ToolbarButton icon="ti-arrow-back-up" label="Отменить" onClick={undo} disabled={past.length === 0} />
      </nav>

      {isAddingPlayer && (
        <AddPlayerSheet
          onClose={() => setIsAddingPlayer(false)}
          onAdd={(position, number) => {
            addToken({ kind: 'own', position, number })
            setIsAddingPlayer(false)
          }}
        />
      )}
    </div>,
    document.body,
  )
}

function StepSwatch() {
  return (
    <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">
      <circle cx="6" cy="6" r="5.5" fill="#FF6A3D" />
      <text x="6" y="6.4" textAnchor="middle" dominantBaseline="central" fontSize="7" fontWeight="800" fill="#fff">1</text>
    </svg>
  )
}

// Legend/palette swatches sit on the dark UI, where the rink's navy skate
// colour would vanish -- lighter variants of the same three.
const SWATCH_COLORS: Record<DiagramArrowKind, string> = {
  pass: '#FF6A3D',
  repass: '#FF6A3D',
  shot: '#FF8A80',
  skate_puck: '#5FD4FF',
  skate: '#F2F5F8',
}

function ArrowSwatch({ kind }: { kind: DiagramArrowKind }) {
  const visible = SWATCH_COLORS[kind]
  return (
    <svg width="18" height="8" aria-hidden="true">
      {kind === 'skate_puck' ? (
        <path d="M0,4 Q2.25,0 4.5,4 T9,4 T13.5,4 T18,4" stroke={visible} strokeWidth="1.8" fill="none" />
      ) : kind === 'shot' ? (
        <path d="M0,2.5 L13,2.5 M0,5.5 L13,5.5 M12,0.5 L17.5,4 L12,7.5 Z" stroke={visible} strokeWidth="1.3" fill={visible} strokeLinejoin="round" />
      ) : kind === 'repass' ? (
        <path d="M4,4 L14,4 M4,1 L0,4 L4,7 M14,1 L18,4 L14,7" stroke={visible} strokeWidth="1.8" fill="none" strokeLinejoin="round" />
      ) : (
        <line x1="0" y1="4" x2="18" y2="4" stroke={visible} strokeWidth="2" strokeDasharray={kind === 'skate' ? '3 3' : undefined} />
      )}
    </svg>
  )
}

// "Такт" of the selected arrow: same number = at the same time.
function StepControl({ step, onChange }: { step: number; onChange: (delta: -1 | 1) => void }) {
  return (
    <div
      role="group"
      aria-label="Такт стрелки"
      className="flex h-11 items-center gap-0.5 rounded-xl bg-white/5 px-1 text-[#C9D1DC]"
    >
      <button
        type="button"
        onClick={() => onChange(-1)}
        disabled={step <= 1}
        aria-label="Такт раньше"
        className="flex h-9 w-9 items-center justify-center rounded-lg transition-colors hover:bg-white/10 disabled:opacity-30"
      >
        <i className="ti ti-minus" aria-hidden="true" />
      </button>
      <span className="flex min-w-12 flex-col items-center leading-tight">
        <span className="font-display text-base font-bold text-[#F5F7FA]" data-testid="arrow-step">
          {step}
        </span>
        <span className="text-[9px]">такт</span>
      </span>
      <button
        type="button"
        onClick={() => onChange(1)}
        disabled={step >= MAX_ARROW_STEP}
        aria-label="Такт позже"
        className="flex h-9 w-9 items-center justify-center rounded-lg transition-colors hover:bg-white/10 disabled:opacity-30"
      >
        <i className="ti ti-plus" aria-hidden="true" />
      </button>
    </div>
  )
}

function FloatingBar({ atTop, children }: { atTop: boolean; children: ReactNode }) {
  return (
    <div className={`absolute ${atTop ? 'top-5' : 'bottom-5'} left-1/2 flex w-max max-w-[calc(100%-16px)] -translate-x-1/2 flex-wrap items-center justify-center gap-1.5 rounded-2xl border border-white/10 bg-[#0B0F14]/90 p-2 backdrop-blur`}>
      {children}
    </div>
  )
}

function PaletteButton({ label, onClick, children }: { label: string; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      title={label}
      className="flex h-11 min-w-11 flex-col items-center justify-center gap-0.5 rounded-xl bg-white/5 px-2 text-[9px] text-[#C9D1DC] transition-colors hover:bg-white/10"
    >
      {children}
      <span>{label}</span>
    </button>
  )
}

function ToolbarButton({
  icon,
  label,
  onClick,
  disabled = false,
}: {
  // A tabler class name, or a node for glyphs the icon font lacks.
  icon: string | ReactNode
  label: string
  onClick: () => void
  disabled?: boolean
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="flex h-12 flex-1 flex-col items-center justify-center gap-0.5 rounded-xl border border-white/10 bg-white/5 text-[#F5F7FA] transition-colors hover:bg-white/10 disabled:opacity-40"
    >
      {typeof icon === 'string' ? <i className={`ti ${icon} text-lg`} aria-hidden="true" /> : icon}
      <span className="text-[10px] text-[#8A94A6]">{label}</span>
    </button>
  )
}

function AddPlayerSheet({
  onClose,
  onAdd,
}: {
  onClose: () => void
  onAdd: (position: DiagramPosition | null, number: number | null) => void
}) {
  const [position, setPosition] = useState<DiagramPosition | null>('F')
  const [number, setNumber] = useState('')
  const positions: DiagramPosition[] = ['F', 'D', 'G']

  return (
    <div className="absolute inset-0 z-10 flex items-end bg-black/50" onClick={onClose}>
      <div
        className="w-full rounded-t-2xl border-t border-white/10 bg-[#131A22] px-5 pb-[calc(24px+env(safe-area-inset-bottom,0px))] pt-4"
        onClick={(event) => event.stopPropagation()}
      >
        <p className="text-base font-bold text-[#F2F5F8]">Добавить игрока</p>
        <p className="mb-4 mt-1 text-xs text-[#8A94A6]">
          Позиция — буква на фишке. Для общего упражнения позиция не нужна.
        </p>
        <div className="mb-2 grid grid-cols-3 gap-2">
          {positions.map((candidate) => (
            <button
              key={candidate}
              type="button"
              onClick={() => setPosition(candidate)}
              aria-pressed={position === candidate}
              className={`flex h-16 flex-col items-center justify-center gap-1 rounded-xl border ${
                position === candidate
                  ? 'border-accent-ice bg-accent-ice/15 text-accent-ice'
                  : 'border-white/10 bg-white/5 text-[#F2F5F8]'
              }`}
            >
              <span className="text-xl font-extrabold">{DIAGRAM_POSITION_LETTERS[candidate]}</span>
              <span className="text-[10px]">{DIAGRAM_POSITION_LABELS[candidate]}</span>
            </button>
          ))}
        </div>
        <button
          type="button"
          onClick={() => setPosition(null)}
          aria-pressed={position === null}
          className={`mb-4 h-11 w-full rounded-xl border border-dashed text-sm ${
            position === null ? 'border-accent-ice text-accent-ice' : 'border-white/15 text-[#8A94A6]'
          }`}
        >
          Без позиции — общее упражнение
        </button>
        <label className="mb-5 flex items-center gap-3 text-xs text-[#8A94A6]">
          <input
            type="text"
            inputMode="numeric"
            value={number}
            onChange={(event) => setNumber(event.target.value.replace(/\D/g, '').slice(0, 2))}
            placeholder="17"
            className="h-12 w-16 rounded-xl border border-white/10 bg-white/5 text-center text-base font-bold text-[#F2F5F8] outline-none focus:border-accent-ice"
          />
          Номер (необязательно)
        </label>
        <Button className="w-full" onClick={() => onAdd(position, number === '' ? null : Number(number))}>
          Поставить на каток
        </Button>
      </div>
    </div>
  )
}
