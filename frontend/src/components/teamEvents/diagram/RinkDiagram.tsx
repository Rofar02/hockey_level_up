import { forwardRef, useId, type PointerEvent as ReactPointerEvent } from 'react'
import { DIAGRAM_POSITION_LETTERS } from '../../../types/teamEvent'
import type { DiagramArrow, DiagramArrowKind, DiagramPoint, DiagramToken, DrillDiagram } from '../../../types/teamEvent'
import {
  ARROW_COLORS,
  RINK_HEIGHT,
  RINK_WIDTH,
  STEP_BADGE_RADIUS,
  TOKEN_RADIUS,
  arrowBadgePoint,
  arrowPath,
  arrowSteps,
  toRink,
} from '../../../utils/rinkDiagram'

interface RinkDiagramProps {
  diagram: DrillDiagram
  className?: string
  selectedTokenId?: string | null
  selectedArrowId?: string | null
  // Editor-only hooks -- the static viewer passes none of them.
  onBackgroundPointerDown?: (event: ReactPointerEvent<SVGSVGElement>) => void
  onTokenPointerDown?: (token: DiagramToken, event: ReactPointerEvent<SVGGElement>) => void
  onArrowPointerDown?: (arrow: DiagramArrow, event: ReactPointerEvent<SVGPathElement>) => void
  onPointerMove?: (event: ReactPointerEvent<SVGSVGElement>) => void
  onPointerUp?: (event: ReactPointerEvent<SVGSVGElement>) => void
  // The arrow currently being drawn with a finger, shown as it's drawn.
  draft?: { kind: DiagramArrowKind; points: DiagramPoint[] } | null
}

const RED_LINE = '#C94A3A'
const BLUE_LINE = '#2F6FB0'
const SELECTION = '#FF6A3D'
const ICE = '#E9F4FA'

// Vertical full rink in a 200x360 box (see utils/rinkDiagram), with the
// drill's tokens and arrows on top. Used as-is for the player's view and
// with the pointer hooks by DiagramEditor.
export const RinkDiagram = forwardRef<SVGSVGElement, RinkDiagramProps>(function RinkDiagram(
  {
    diagram,
    className = '',
    selectedTokenId = null,
    selectedArrowId = null,
    onBackgroundPointerDown,
    onTokenPointerDown,
    onArrowPointerDown,
    onPointerMove,
    onPointerUp,
    draft = null,
  },
  ref,
) {
  const markerPrefix = useId().replace(/:/g, '')
  const interactive = onTokenPointerDown !== undefined

  return (
    <svg
      ref={ref}
      viewBox={`0 0 ${RINK_WIDTH} ${RINK_HEIGHT}`}
      className={`block select-none ${interactive ? 'touch-none' : ''} ${className}`}
      role="img"
      aria-label="Схема упражнения на площадке"
      onPointerDown={onBackgroundPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
    >
      <defs>
        {/* A shot's double line is 4.4 wide -- its head is sized in rink
            units, not stroke widths, or it would come out huge. */}
        <marker
          id={`${markerPrefix}-shot`}
          markerWidth="11"
          markerHeight="11"
          refX="8"
          refY="5"
          orient="auto"
          markerUnits="userSpaceOnUse"
        >
          <path d="M0,0 L10,5 L0,10 Z" fill={ARROW_COLORS.shot} />
        </marker>
        {(Object.keys(ARROW_COLORS) as (keyof typeof ARROW_COLORS)[])
          .filter((kind) => kind !== 'shot')
          .map((kind) => (
          <marker
            key={kind}
            id={`${markerPrefix}-${kind}`}
            markerWidth="6"
            markerHeight="6"
            refX="5"
            refY="3"
            orient="auto-start-reverse"
            markerUnits="strokeWidth"
          >
            <path d="M0,0 L6,3 L0,6 Z" fill={ARROW_COLORS[kind]} />
          </marker>
          ))}
      </defs>

      <RinkMarkings />

      {diagram.arrows.map((arrow) => {
        const path = arrowPath(arrow)
        const selected = arrow.id === selectedArrowId
        return (
          <g key={arrow.id}>
            {selected && <path d={path} fill="none" stroke={SELECTION} strokeWidth="6" strokeOpacity="0.35" strokeLinecap="round" />}
            {arrow.kind === 'shot' ? (
              // Бросок: the standard double line -- a wide stroke with an
              // ice-coloured core, then the head drawn last so the core
              // doesn't cut through it.
              <>
                <path d={path} fill="none" stroke={ARROW_COLORS.shot} strokeWidth="4.4" strokeLinecap="butt" />
                <path d={path} fill="none" stroke={ICE} strokeWidth="1.6" strokeLinecap="butt" />
                <path d={path} fill="none" stroke="none" markerEnd={`url(#${markerPrefix}-shot)`} />
              </>
            ) : (
            <path
              d={path}
              fill="none"
              stroke={ARROW_COLORS[arrow.kind]}
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeDasharray={arrow.kind === 'skate' ? '4 3' : undefined}
              markerEnd={`url(#${markerPrefix}-${arrow.kind})`}
              // Перепас: the puck goes there and back -- a head at both ends.
              markerStart={arrow.kind === 'repass' ? `url(#${markerPrefix}-${arrow.kind})` : undefined}
            />
            )}
            {interactive && (
              // Wide invisible hit area -- a 1.8px line is impossible to tap.
              <path
                d={path}
                fill="none"
                stroke="transparent"
                strokeWidth="12"
                onPointerDown={(event) => onArrowPointerDown?.(arrow, event)}
              />
            )}
          </g>
        )
      })}

      {/* Order of play: a numbered badge where each movement starts; same
          number = at the same time. Pointless with a single arrow. */}
      {diagram.arrows.length > 1 && <StepBadges diagram={diagram} />}

      {draft !== null && draft.points.length > 1 && (
        <polyline
          points={draft.points.map((point) => `${toRink(point).x},${toRink(point).y}`).join(' ')}
          fill="none"
          stroke={ARROW_COLORS[draft.kind]}
          strokeWidth="2"
          strokeOpacity="0.7"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeDasharray={draft.kind === 'skate' ? '4 3' : undefined}
          pointerEvents="none"
        />
      )}

      {diagram.tokens.map((token) => (
        <Token
          key={token.id}
          token={token}
          selected={token.id === selectedTokenId}
          onPointerDown={onTokenPointerDown}
        />
      ))}
    </svg>
  )
})

function Token({
  token,
  selected,
  onPointerDown,
}: {
  token: DiagramToken
  selected: boolean
  onPointerDown?: (token: DiagramToken, event: ReactPointerEvent<SVGGElement>) => void
}) {
  const { x, y } = toRink(token)
  const handleDown = onPointerDown ? (event: ReactPointerEvent<SVGGElement>) => onPointerDown(token, event) : undefined
  const cursor = onPointerDown ? 'cursor-grab' : ''

  if (token.kind === 'puck') {
    return (
      <g onPointerDown={handleDown} className={cursor}>
        {selected && <circle cx={x} cy={y} r={TOKEN_RADIUS.puck + 4} fill={SELECTION} fillOpacity="0.35" />}
        {/* Invisible, larger tap target around the small puck. */}
        <circle cx={x} cy={y} r={10} fill="transparent" />
        <ellipse cx={x} cy={y} rx={TOKEN_RADIUS.puck} ry={TOKEN_RADIUS.puck * 0.7} fill="#10151C" />
      </g>
    )
  }

  if (token.kind === 'opponent') {
    const r = TOKEN_RADIUS.opponent
    return (
      <g onPointerDown={handleDown} className={cursor}>
        {selected && <circle cx={x} cy={y} r={r + 4} fill={SELECTION} fillOpacity="0.35" />}
        <circle cx={x} cy={y} r={r} fill="#1A2634" stroke="#0078A8" strokeWidth="1.8" />
        <path d={`M ${x - 3.5} ${y - 3.5} L ${x + 3.5} ${y + 3.5} M ${x + 3.5} ${y - 3.5} L ${x - 3.5} ${y + 3.5}`} stroke="#8FB8CC" strokeWidth="1.4" strokeLinecap="round" />
      </g>
    )
  }

  const r = TOKEN_RADIUS.own
  const isGoalie = token.position === 'G'
  const letter = token.position != null ? DIAGRAM_POSITION_LETTERS[token.position] : null
  const centerLabel = letter ?? (token.number != null ? String(token.number) : '')
  const showBadge = letter !== null && token.number != null
  return (
    <g onPointerDown={handleDown} className={cursor}>
      {selected && <circle cx={x} cy={y} r={r + 4} fill={SELECTION} fillOpacity="0.35" />}
      <circle cx={x} cy={y} r={r} fill={isGoalie ? '#FFCF5C' : '#F4F6F8'} stroke="#10151C" strokeWidth="1.6" />
      <text
        x={x}
        y={y}
        textAnchor="middle"
        dominantBaseline="central"
        fontSize={centerLabel.length > 1 ? 8 : 10}
        fontWeight="800"
        fill="#10151C"
      >
        {centerLabel}
      </text>
      {showBadge && (
        <g>
          <circle cx={x + 8} cy={y + 8} r={5} fill="#D64E27" stroke="#10151C" strokeWidth="1" />
          <text x={x + 8} y={y + 8} textAnchor="middle" dominantBaseline="central" fontSize="5.5" fontWeight="800" fill="#FFFFFF">
            {token.number}
          </text>
        </g>
      )}
    </g>
  )
}

function StepBadges({ diagram }: { diagram: DrillDiagram }) {
  const steps = arrowSteps(diagram)
  return (
    <g pointerEvents="none" aria-hidden="true">
      {diagram.arrows.map((arrow) => {
        const { x, y } = arrowBadgePoint(arrow)
        return (
          <g key={arrow.id} data-step={steps.get(arrow.id)}>
            <circle cx={x} cy={y} r={STEP_BADGE_RADIUS} fill={ARROW_COLORS[arrow.kind]} stroke="#E9F4FA" strokeWidth="1.2" />
            <text x={x} y={y} textAnchor="middle" dominantBaseline="central" fontSize="6.5" fontWeight="800" fill="#FFFFFF">
              {steps.get(arrow.id)}
            </text>
          </g>
        )
      })}
    </g>
  )
}

// Proportions follow a real rink loosely: goal lines 20 from the ends,
// blue lines splitting the length into thirds-ish zones, faceoff dots and
// circles in each end zone.
function RinkMarkings() {
  const dots = [
    [48, 64],
    [152, 64],
    [48, 296],
    [152, 296],
  ]
  return (
    <g pointerEvents="none">
      <rect x="1" y="1" width={RINK_WIDTH - 2} height={RINK_HEIGHT - 2} rx="28" fill="#E9F4FA" stroke="#9FB3C2" strokeWidth="2" />
      <line x1="4" y1="20" x2={RINK_WIDTH - 4} y2="20" stroke={RED_LINE} strokeWidth="1" />
      <line x1="4" y1={RINK_HEIGHT - 20} x2={RINK_WIDTH - 4} y2={RINK_HEIGHT - 20} stroke={RED_LINE} strokeWidth="1" />
      <line x1="1" y1="128" x2={RINK_WIDTH - 1} y2="128" stroke={BLUE_LINE} strokeWidth="3" />
      <line x1="1" y1="232" x2={RINK_WIDTH - 1} y2="232" stroke={BLUE_LINE} strokeWidth="3" />
      <line x1="1" y1="180" x2={RINK_WIDTH - 1} y2="180" stroke={RED_LINE} strokeWidth="3" />
      <circle cx="100" cy="180" r="26" fill="none" stroke={BLUE_LINE} strokeWidth="1.2" />
      <circle cx="100" cy="180" r="1.8" fill={BLUE_LINE} />
      {dots.map(([cx, cy]) => (
        <g key={`${cx}-${cy}`}>
          <circle cx={cx} cy={cy} r="26" fill="none" stroke={RED_LINE} strokeWidth="1" />
          <circle cx={cx} cy={cy} r="2" fill={RED_LINE} />
        </g>
      ))}
      {/* Goals + creases */}
      <path d="M 88 20 A 12 12 0 0 0 112 20" fill="#CFE7F5" stroke={RED_LINE} strokeWidth="1" />
      <rect x="93" y="14" width="14" height="6" fill="none" stroke={RED_LINE} strokeWidth="1.2" />
      <path d={`M 88 ${RINK_HEIGHT - 20} A 12 12 0 0 1 112 ${RINK_HEIGHT - 20}`} fill="#CFE7F5" stroke={RED_LINE} strokeWidth="1" />
      <rect x="93" y={RINK_HEIGHT - 20} width="14" height="6" fill="none" stroke={RED_LINE} strokeWidth="1.2" />
    </g>
  )
}
