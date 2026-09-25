import type { DiagramArrow, DiagramArrowKind, DiagramPoint, DrillDiagram } from '../types/teamEvent'

// The rink is drawn in a fixed 200x360 viewBox (vertical, our goal at the
// bottom) -- a real rink is ~2.35:1, squashed a little so a whole rink plus
// the editor toolbar fits a phone screen. Diagram coordinates are 0..1
// fractions of this box.
export const RINK_WIDTH = 200
export const RINK_HEIGHT = 360

export const TOKEN_RADIUS = { own: 10, opponent: 9, puck: 4.5 } as const

export const ARROW_COLORS: Record<DiagramArrowKind, string> = {
  pass: '#D64E27',
  repass: '#D64E27',
  // Darker than a pass (told apart by lightness, not just hue) and drawn
  // as a double line.
  shot: '#8E1B24',
  skate: '#1A2634',
  skate_puck: '#0078A8',
}

// The middle of each goal mouth, just in front of the goal line (see
// RinkMarkings): a shot ending anywhere near a goal lands exactly here.
const GOAL_MOUTHS: DiagramPoint[] = [
  { x: 0.5, y: 22 / RINK_HEIGHT },
  { x: 0.5, y: (RINK_HEIGHT - 22) / RINK_HEIGHT },
]
const GOAL_SNAP_RADIUS = 60

export function snapToGoal(point: DiagramPoint): DiagramPoint {
  const at = toRink(point)
  for (const mouth of GOAL_MOUTHS) {
    const goal = toRink(mouth)
    if (Math.hypot(goal.x - at.x, goal.y - at.y) <= GOAL_SNAP_RADIUS) {
      return mouth
    }
  }
  return point
}

export function toRink(point: DiagramPoint): { x: number; y: number } {
  return { x: point.x * RINK_WIDTH, y: point.y * RINK_HEIGHT }
}

export function clamp01(value: number): number {
  return Math.min(1, Math.max(0, value))
}

export function newDiagramId(): string {
  return Math.random().toString(36).slice(2, 10)
}

export function emptyDiagram(): DrillDiagram {
  return { tokens: [], arrows: [] }
}

export function isEmptyDiagram(diagram: DrillDiagram): boolean {
  return diagram.tokens.length === 0 && diagram.arrows.length === 0
}

const WAVE_AMPLITUDE = 3
const WAVE_LENGTH = 10
// The last stretch before the arrowhead stays straight so the head sits
// cleanly on the line.
const STRAIGHT_TAIL = 8

type Pt = { x: number; y: number }

function distance(a: Pt, b: Pt): number {
  return Math.hypot(b.x - a.x, b.y - a.y)
}

function polylineLength(points: Pt[]): number {
  let total = 0
  for (let i = 1; i < points.length; i++) {
    total += distance(points[i - 1], points[i])
  }
  return total
}

// Centripetal Catmull-Rom spline through the control points, sampled
// densely: a smooth curve through every stored point that, unlike the
// uniform variant, never loops or overshoots on a sharp turn.
function smoothPolyline(points: Pt[], samplesPerSegment = 12): Pt[] {
  if (points.length <= 2) {
    return points
  }
  const out: Pt[] = [points[0]]
  for (let i = 0; i < points.length - 1; i++) {
    const p1 = points[i]
    const p2 = points[i + 1]
    // Mirrored phantom points at the ends keep the first/last segments
    // pointing where the path actually goes.
    const p0 = i > 0 ? points[i - 1] : { x: 2 * p1.x - p2.x, y: 2 * p1.y - p2.y }
    const p3 = i + 2 < points.length ? points[i + 2] : { x: 2 * p2.x - p1.x, y: 2 * p2.y - p1.y }
    const knot = (a: Pt, b: Pt) => Math.max(Math.sqrt(distance(a, b)), 1e-4)
    const t0 = 0
    const t1 = t0 + knot(p0, p1)
    const t2 = t1 + knot(p1, p2)
    const t3 = t2 + knot(p2, p3)
    const lerp = (a: Pt, b: Pt, ta: number, tb: number, t: number): Pt => ({
      x: ((tb - t) / (tb - ta)) * a.x + ((t - ta) / (tb - ta)) * b.x,
      y: ((tb - t) / (tb - ta)) * a.y + ((t - ta) / (tb - ta)) * b.y,
    })
    for (let step = 1; step <= samplesPerSegment; step++) {
      const t = t1 + ((t2 - t1) * step) / samplesPerSegment
      const a1 = lerp(p0, p1, t0, t1, t)
      const a2 = lerp(p1, p2, t1, t2, t)
      const a3 = lerp(p2, p3, t2, t3, t)
      const b1 = lerp(a1, a2, t0, t2, t)
      const b2 = lerp(a2, a3, t1, t3, t)
      out.push(lerp(b1, b2, t1, t2, t))
    }
  }
  return out
}

// Point and unit tangent at arc length `s` along a polyline.
function pointAtLength(points: Pt[], s: number): { point: Pt; tangent: Pt } {
  let walked = 0
  for (let i = 1; i < points.length; i++) {
    const segment = distance(points[i - 1], points[i])
    if (segment > 0 && walked + segment >= s) {
      const t = (s - walked) / segment
      const a = points[i - 1]
      const b = points[i]
      return {
        point: { x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t },
        tangent: { x: (b.x - a.x) / segment, y: (b.y - a.y) / segment },
      }
    }
    walked += segment
  }
  const a = points[points.length - 2] ?? points[0]
  const b = points[points.length - 1]
  const segment = distance(a, b) || 1
  return { point: b, tangent: { x: (b.x - a.x) / segment, y: (b.y - a.y) / segment } }
}

// The part of a polyline from arc length `from` to its end.
function sliceFrom(points: Pt[], from: number): Pt[] {
  if (from <= 0) {
    return points
  }
  let walked = 0
  for (let i = 1; i < points.length; i++) {
    const segment = distance(points[i - 1], points[i])
    if (walked + segment >= from) {
      return [pointAtLength(points, from).point, ...points.slice(i)]
    }
    walked += segment
  }
  return [points[points.length - 1]]
}

function toPath(points: Pt[]): string {
  return points.map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x} ${point.y}`).join(' ')
}

// SVG path for an arrow in rink units: straight, or a smooth curve through
// its `via` points. An arrow that starts at a token starts at its edge, not
// its centre; skate_puck is drawn as a wave that follows the curve.
// The arrow's centre line in rink units: the smooth curve through its
// points, starting at the edge of the token it leaves from (if any).
function arrowLine(arrow: DiagramArrow): Pt[] {
  const control = [arrow.start, ...(arrow.via ?? []), arrow.end].map(toRink)
  const line = smoothPolyline(control)
  const fullLength = polylineLength(line)
  if (fullLength >= 1 && arrow.from_token != null) {
    return sliceFrom(line, Math.min(TOKEN_RADIUS.own + 1, fullLength / 2))
  }
  return line
}

export function arrowPath(arrow: DiagramArrow): string {
  const line = arrowLine(arrow)
  const length = polylineLength(line)
  if (length < 1) {
    return toPath([line[0], line[line.length - 1]])
  }
  if (arrow.kind !== 'skate_puck' || length <= STRAIGHT_TAIL + 2) {
    return toPath(line)
  }
  const waveEnd = length - STRAIGHT_TAIL
  const wave: Pt[] = [line[0]]
  // One sample per rink unit (10 per wave period) keeps the wave smooth
  // through a curve's bends.
  for (let s = 1; s <= waveEnd; s += 1) {
    const { point, tangent } = pointAtLength(line, s)
    const offset = WAVE_AMPLITUDE * Math.sin((2 * Math.PI * s) / WAVE_LENGTH)
    // Normal to the local direction of travel.
    wave.push({ x: point.x - tangent.y * offset, y: point.y + tangent.x * offset })
  }
  return toPath([...wave, ...sliceFrom(line, waveEnd)])
}

// Length of a stroke in rink units -- tells a tap from a drawn path.
export function strokeLength(points: DiagramPoint[]): number {
  return polylineLength(points.map(toRink))
}

// Ramer-Douglas-Peucker: indices of the points that keep the polyline's
// shape within `epsilon` rink units. Endpoints are always kept.
function rdp(points: Pt[], epsilon: number): number[] {
  const kept = new Set([0, points.length - 1])
  const stack: [number, number][] = [[0, points.length - 1]]
  while (stack.length > 0) {
    const [first, last] = stack.pop()!
    const a = points[first]
    const b = points[last]
    const span = distance(a, b) || 1
    let farthest = -1
    let farthestDistance = 0
    for (let i = first + 1; i < last; i++) {
      const p = points[i]
      const d = Math.abs((b.x - a.x) * (a.y - p.y) - (a.x - p.x) * (b.y - a.y)) / span
      if (d > farthestDistance) {
        farthestDistance = d
        farthest = i
      }
    }
    if (farthest !== -1 && farthestDistance > epsilon) {
      kept.add(farthest)
      stack.push([first, farthest], [farthest, last])
    }
  }
  return [...kept].sort((x, y) => x - y)
}

// Same points spaced evenly along the path, so smoothing below treats a
// slow and a fast part of the stroke alike.
function resample(points: Pt[], spacing: number): Pt[] {
  const total = polylineLength(points)
  if (total < spacing * 2) {
    return points
  }
  const out: Pt[] = []
  for (let s = 0; s < total; s += spacing) {
    out.push(pointAtLength(points, s).point)
  }
  out.push(points[points.length - 1])
  return out
}

const STROKE_SPACING = 3
const SMOOTHING_RADIUS = 3
// A stroke that strays from the straight line between its ends by less
// than this share of its length was meant to be straight.
const STRAIGHT_TOLERANCE = 0.07
const STRAIGHT_MIN_DEVIATION = 5

// Turns a raw finger stroke into a clean path: evenly resampled, hand
// jitter averaged out, a nearly straight stroke made exactly straight, and
// the rest reduced to at most `maxPoints` shape points (the renderer draws
// a smooth curve through them). Returns the path including both endpoints;
// just the two endpoints means "straight arrow".
export function smoothStroke(points: DiagramPoint[], maxPoints = 8): DiagramPoint[] {
  if (points.length <= 2) {
    return points
  }
  const first = points[0]
  const last = points[points.length - 1]
  const even = resample(points.map(toRink), STROKE_SPACING)

  // Moving average; the ends stay pinned where the stroke started/ended.
  const smoothed = even.map((point, index) => {
    if (index === 0 || index === even.length - 1) {
      return point
    }
    const from = Math.max(0, index - SMOOTHING_RADIUS)
    const to = Math.min(even.length - 1, index + SMOOTHING_RADIUS)
    let x = 0
    let y = 0
    for (let i = from; i <= to; i++) {
      x += even[i].x
      y += even[i].y
    }
    return { x: x / (to - from + 1), y: y / (to - from + 1) }
  })

  const a = smoothed[0]
  const b = smoothed[smoothed.length - 1]
  const chord = distance(a, b)
  const maxDeviation = Math.max(
    ...smoothed.map((p) => Math.abs((b.x - a.x) * (a.y - p.y) - (a.x - p.x) * (b.y - a.y)) / (chord || 1)),
  )
  if (chord > 0 && maxDeviation < Math.max(STRAIGHT_MIN_DEVIATION, chord * STRAIGHT_TOLERANCE)) {
    return [first, last]
  }

  let epsilon = 3
  let indices = rdp(smoothed, epsilon)
  while (indices.length > maxPoints) {
    epsilon *= 1.4
    indices = rdp(smoothed, epsilon)
  }
  const fromRink = (p: Pt): DiagramPoint => ({ x: clamp01(p.x / RINK_WIDTH), y: clamp01(p.y / RINK_HEIGHT) })
  return [first, ...indices.slice(1, -1).map((index) => fromRink(smoothed[index])), last]
}

export const MAX_ARROW_STEP = 20
export const STEP_BADGE_RADIUS = 5.5

// Where an arrow's step badge sits: a little way along the arrow from its
// start, so it marks where the movement begins without covering the
// arrowhead of the arrow it continues from.
export function arrowBadgePoint(arrow: DiagramArrow): { x: number; y: number } {
  const line = arrowLine(arrow)
  const length = polylineLength(line)
  if (length < 1) {
    return line[0]
  }
  return pointAtLength(line, Math.min(STEP_BADGE_RADIUS + 3, length / 3)).point
}

const SAME_POINT = 0.004

// Step of every arrow: its stored one, or derived -- 1 for an arrow from a
// player (different players start together by default), the step of the
// arrow it continues from + 1 for a chained one. Arrows are in the order
// they were drawn, so a predecessor is always resolved first.
export function arrowSteps(diagram: DrillDiagram): Map<string, number> {
  const steps = new Map<string, number>()
  for (const arrow of diagram.arrows) {
    if (arrow.step != null) {
      steps.set(arrow.id, arrow.step)
      continue
    }
    let step = 1
    if (arrow.from_token == null) {
      const previous = diagram.arrows.find(
        (candidate) =>
          candidate.id !== arrow.id &&
          steps.has(candidate.id) &&
          Math.abs(candidate.end.x - arrow.start.x) < SAME_POINT &&
          Math.abs(candidate.end.y - arrow.start.y) < SAME_POINT,
      )
      if (previous !== undefined) {
        step = Math.min(MAX_ARROW_STEP, (steps.get(previous.id) ?? 1) + 1)
      }
    }
    steps.set(arrow.id, step)
  }
  return steps
}
