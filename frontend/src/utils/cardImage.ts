import { COLLAR_PATH, JERSEY_PATH } from '../components/ui/JerseyBadge'
import type { TierLook } from '../components/playerCardLook'

// The player card as a PNG for sharing, painted straight onto a canvas.
//
// Not a DOM snapshot (html-to-image and the like wrap the page in an SVG
// image): Safari on an iPhone refused to load that SVG -- "Не удалось
// подготовить карточку" -- and before that dropped its images and fonts.
// Canvas has none of those problems: fonts are the page's own, loaded ones,
// images are drawn directly.
//
// The backdrop (frame, arena, tint, photo fade, lines, emblem) is drawn from
// the same values PlayerCard uses; the text is read off the live card --
// each [data-card-text] element's box, font, colour and spacing -- so the
// picture matches what's on screen without duplicating the layout.

const SCALE = 2
const CARD_BG = '#0E1524'
// Upper bounds on the waits, so a stuck font or image costs a detail of the
// picture, not the whole share (the button spun forever otherwise).
const FONTS_WAIT_MS = 3000
const IMAGE_WAIT_MS = 8000
const SHIELD_PATH = 'M12 3a12 12 0 0 0 8.5 3a12 12 0 0 1 -8.5 15a12 12 0 0 1 -8.5 -15a12 12 0 0 0 8.5 -3'

interface Box {
  x: number
  y: number
  w: number
  h: number
}

function boxOf(element: Element, origin: DOMRect): Box {
  const rect = element.getBoundingClientRect()
  return { x: rect.left - origin.left, y: rect.top - origin.top, w: rect.width, h: rect.height }
}

// Loads an image the canvas may read back. A cross-origin one (the dev API
// on another port) needs a CORS request, and a cache-busting query so the
// browser doesn't reuse the copy the <img> fetched without one.
function withTimeout<T>(promise: Promise<T>, ms: number, fallback: T): Promise<T> {
  return new Promise((resolve) => {
    const timer = setTimeout(() => resolve(fallback), ms)
    promise.then(
      (value) => {
        clearTimeout(timer)
        resolve(value)
      },
      () => {
        clearTimeout(timer)
        resolve(fallback)
      },
    )
  })
}

async function loadImage(src: string): Promise<HTMLImageElement | null> {
  const image = new Image()
  const url = new URL(src, window.location.href)
  if (url.origin !== window.location.origin) {
    image.crossOrigin = 'anonymous'
    url.searchParams.set('card', '1')
  }
  image.src = url.href
  const decoded = image.decode().then(() => image)
  return withTimeout<HTMLImageElement | null>(decoded, IMAGE_WAIT_MS, null)
}

function roundRectPath(ctx: CanvasRenderingContext2D, box: Box, radius: number) {
  const r = Math.min(radius, box.w / 2, box.h / 2)
  ctx.beginPath()
  ctx.moveTo(box.x + r, box.y)
  ctx.arcTo(box.x + box.w, box.y, box.x + box.w, box.y + box.h, r)
  ctx.arcTo(box.x + box.w, box.y + box.h, box.x, box.y + box.h, r)
  ctx.arcTo(box.x, box.y + box.h, box.x, box.y, r)
  ctx.arcTo(box.x, box.y, box.x + box.w, box.y, r)
  ctx.closePath()
}

// Frosted glass for the canvas, which has no backdrop-filter: what's already
// painted under the box (plus a margin, so the edges blur into their
// neighbours) is shrunk and stretched back -- a cheap blur -- and drawn
// clipped to the pill. Without it the plate came out see-through in the
// shared PNG while on screen it's frosted.
function frostBehind(ctx: CanvasRenderingContext2D, canvas: HTMLCanvasElement, box: Box, radius: number) {
  const margin = 12
  const sx = Math.max(0, Math.floor((box.x - margin) * SCALE))
  const sy = Math.max(0, Math.floor((box.y - margin) * SCALE))
  const sw = Math.min(canvas.width - sx, Math.ceil((box.w + margin * 2) * SCALE))
  const sh = Math.min(canvas.height - sy, Math.ceil((box.h + margin * 2) * SCALE))
  if (sw <= 0 || sh <= 0) {
    return
  }
  const small = document.createElement('canvas')
  small.width = Math.max(1, Math.round(sw / 14))
  small.height = Math.max(1, Math.round(sh / 14))
  const smallCtx = small.getContext('2d')
  if (smallCtx === null) {
    return
  }
  smallCtx.imageSmoothingQuality = 'high'
  // backdrop-saturate-150; browsers without canvas filters just skip it.
  smallCtx.filter = 'saturate(1.5)'
  smallCtx.drawImage(canvas, sx, sy, sw, sh, 0, 0, small.width, small.height)
  ctx.save()
  roundRectPath(ctx, box, radius)
  ctx.clip()
  ctx.setTransform(1, 0, 0, 1, 0, 0)
  ctx.imageSmoothingEnabled = true
  ctx.imageSmoothingQuality = 'high'
  ctx.drawImage(small, sx, sy, sw, sh)
  ctx.restore()
}

// object-fit: cover with an object-position, like the <img>s on the card.
function drawCover(ctx: CanvasRenderingContext2D, image: HTMLImageElement, box: Box, posX: number, posY: number) {
  const scale = Math.max(box.w / image.naturalWidth, box.h / image.naturalHeight)
  const w = image.naturalWidth * scale
  const h = image.naturalHeight * scale
  ctx.drawImage(image, box.x + (box.w - w) * posX, box.y + (box.h - h) * posY, w, h)
}

function horizontal(ctx: CanvasRenderingContext2D, box: Box, stops: [number, string][]) {
  const gradient = ctx.createLinearGradient(box.x, 0, box.x + box.w, 0)
  for (const [at, color] of stops) {
    gradient.addColorStop(at, color)
  }
  return gradient
}

// CSS linear-gradient(<angle>deg, ...) over a box.
function angled(ctx: CanvasRenderingContext2D, box: Box, degrees: number, stops: [number, string][]) {
  const radians = (degrees * Math.PI) / 180
  const dx = Math.sin(radians)
  const dy = -Math.cos(radians)
  const half = (Math.abs(box.w * dx) + Math.abs(box.h * dy)) / 2
  const cx = box.x + box.w / 2
  const cy = box.y + box.h / 2
  const gradient = ctx.createLinearGradient(cx - dx * half, cy - dy * half, cx + dx * half, cy + dy * half)
  for (const [at, color] of stops) {
    gradient.addColorStop(at, color)
  }
  return gradient
}

function drawTexts(ctx: CanvasRenderingContext2D, root: HTMLElement, origin: DOMRect) {
  for (const element of Array.from(root.querySelectorAll<HTMLElement>('[data-card-text]'))) {
    const text = element.textContent?.trim() ?? ''
    if (text === '') {
      continue
    }
    const style = getComputedStyle(element)
    const box = boxOf(element, origin)
    ctx.save()
    ctx.font = `${style.fontStyle} ${style.fontWeight} ${style.fontSize} ${style.fontFamily}`
    ctx.fillStyle = style.color
    if ('letterSpacing' in ctx) {
      ctx.letterSpacing = style.letterSpacing === 'normal' ? '0px' : style.letterSpacing
    }
    if (style.textShadow !== 'none') {
      ctx.shadowColor = 'rgba(0,0,0,0.75)'
      ctx.shadowBlur = 12
      ctx.shadowOffsetY = 2
    }
    ctx.textBaseline = 'middle'
    const alignRight = element.dataset.cardText === 'right'
    ctx.textAlign = alignRight ? 'right' : 'left'
    const content = style.textTransform === 'uppercase' ? text.toUpperCase() : text
    ctx.fillText(content, alignRight ? box.x + box.w : box.x, box.y + box.h / 2)
    ctx.restore()
  }
}

function drawJersey(ctx: CanvasRenderingContext2D, svg: Element, origin: DOMRect) {
  const box = boxOf(svg, origin)
  // The jersey is drawn in the number's colour (PlayerCard sets it on the svg).
  const color = getComputedStyle(svg).color
  const unit = box.w / 130
  const [surnameText, numberText] = Array.from(svg.querySelectorAll('text'))
  ctx.save()
  ctx.globalAlpha = 0.9
  ctx.translate(box.x, box.y)
  ctx.scale(unit, unit)
  ctx.lineJoin = 'round'
  ctx.lineWidth = 1.5
  ctx.strokeStyle = color
  ctx.fillStyle = 'rgba(14,21,36,0.55)'
  const jersey = new Path2D(JERSEY_PATH)
  ctx.fill(jersey)
  ctx.stroke(jersey)
  ctx.stroke(new Path2D(COLLAR_PATH))
  ctx.fillStyle = color
  ctx.textAlign = 'center'
  ctx.textBaseline = 'alphabetic'
  ctx.font = '600 10px Oswald'
  ctx.fillText((surnameText?.textContent ?? '').toUpperCase(), 65, 34)
  ctx.font = '700 30px Oswald'
  ctx.fillText(numberText?.textContent ?? '', 65, 70)
  ctx.restore()
}

async function drawEmblem(ctx: CanvasRenderingContext2D, emblem: Element, origin: DOMRect) {
  const box = boxOf(emblem, origin)
  const cx = box.x + box.w / 2
  const cy = box.y + box.h / 2
  const radius = box.w / 2
  const logo = emblem.querySelector<HTMLImageElement>('[data-card="emblem-logo"]')
  const logoImage = logo !== null ? await loadImage(logo.currentSrc || logo.src) : null
  ctx.save()
  ctx.beginPath()
  ctx.arc(cx, cy, radius, 0, Math.PI * 2)
  ctx.fillStyle = '#22304A'
  ctx.fill()
  if (logoImage !== null) {
    ctx.save()
    ctx.clip()
    drawCover(ctx, logoImage, box, 0.5, 0.5)
    ctx.restore()
  } else {
    ctx.save()
    ctx.translate(cx - 8, cy - 8)
    ctx.scale(16 / 24, 16 / 24)
    ctx.strokeStyle = '#D7EFFF'
    ctx.lineWidth = 2
    ctx.lineCap = 'round'
    ctx.lineJoin = 'round'
    ctx.stroke(new Path2D(SHIELD_PATH))
    ctx.restore()
  }
  ctx.beginPath()
  ctx.arc(cx, cy, radius - 0.5, 0, Math.PI * 2)
  ctx.strokeStyle = 'rgba(215,239,255,0.35)'
  ctx.lineWidth = 1
  ctx.stroke()
  ctx.restore()
}

// The photo, faded out towards the bottom like PlayerCard's mask.
function drawFadedPhoto(ctx: CanvasRenderingContext2D, image: HTMLImageElement, box: Box) {
  const layer = document.createElement('canvas')
  layer.width = Math.round(box.w * SCALE)
  layer.height = Math.round(box.h * SCALE)
  const layerCtx = layer.getContext('2d')
  if (layerCtx === null) {
    return
  }
  layerCtx.scale(SCALE, SCALE)
  drawCover(layerCtx, image, { x: 0, y: 0, w: box.w, h: box.h }, 0.5, 0.15)
  layerCtx.globalCompositeOperation = 'destination-in'
  const fade = layerCtx.createLinearGradient(0, 0, 0, box.h)
  fade.addColorStop(0.52, 'rgba(0,0,0,1)')
  fade.addColorStop(0.94, 'rgba(0,0,0,0)')
  layerCtx.fillStyle = fade
  layerCtx.fillRect(0, 0, box.w, box.h)
  ctx.drawImage(layer, box.x, box.y, box.w, box.h)
}

function drawLines(ctx: CanvasRenderingContext2D, frame: HTMLElement, origin: DOMRect, look: TierLook) {
  const stripe = (box: Box) =>
    horizontal(ctx, box, [
      [0, look.stripeStops[0]],
      [1, look.stripeStops[1]],
    ])
  // The top stripe and the nameplate's two rules.
  for (const line of Array.from(frame.querySelectorAll('[data-card="stripe-line"]'))) {
    const box = boxOf(line, origin)
    ctx.fillStyle = stripe(box)
    ctx.fillRect(box.x, box.y, box.w, box.h)
  }
  // The rating column's divider.
  ctx.fillStyle = 'rgba(255,255,255,0.25)'
  for (const rule of Array.from(frame.querySelectorAll('[data-card="rule"]'))) {
    const box = boxOf(rule, origin)
    ctx.fillRect(box.x, box.y, box.w, box.h)
  }
  // The divider between the two stat columns.
  ctx.fillStyle = 'rgba(255,255,255,0.15)'
  for (const cell of Array.from(frame.querySelectorAll('[data-card="stat-left"]'))) {
    const box = boxOf(cell, origin)
    ctx.fillRect(box.x + box.w - 1, box.y, 1, box.h)
  }
  // The XP strip: its top rule, the track, the fill.
  const xpRow = frame.querySelector('[data-card="xp-row"]')
  if (xpRow !== null) {
    const box = boxOf(xpRow, origin)
    ctx.fillStyle = 'rgba(255,255,255,0.10)'
    ctx.fillRect(box.x, box.y, box.w, 1)
  }
  const track = frame.querySelector('[data-card="xp-track"]')
  if (track !== null) {
    const box = boxOf(track, origin)
    roundRectPath(ctx, box, box.h / 2)
    ctx.fillStyle = 'rgba(255,255,255,0.10)'
    ctx.fill()
  }
  const fill = frame.querySelector('[data-card="xp-fill"]')
  if (fill !== null) {
    const box = boxOf(fill, origin)
    if (box.w > 0) {
      roundRectPath(ctx, box, box.h / 2)
      ctx.fillStyle = stripe(box)
      ctx.fill()
    }
  }
}

// `frame` is PlayerCard's [data-card="frame"] element, as rendered.
export async function renderCardImage(frame: HTMLElement, look: TierLook): Promise<Blob> {
  await withTimeout(document.fonts.ready.then(() => undefined), FONTS_WAIT_MS, undefined)
  const origin = frame.getBoundingClientRect()
  const inner = frame.querySelector('[data-card="inner"]')
  if (inner === null) {
    throw new Error('card markup changed')
  }
  const arena = frame.querySelector<HTMLImageElement>('[data-card="arena"]')
  const photo = frame.querySelector<HTMLImageElement>('[data-card="photo"]')
  const [arenaImage, photoImage] = await Promise.all([
    arena !== null ? loadImage(arena.currentSrc || arena.src) : null,
    photo !== null ? loadImage(photo.currentSrc || photo.src) : null,
  ])

  const canvas = document.createElement('canvas')
  canvas.width = Math.round(origin.width * SCALE)
  canvas.height = Math.round(origin.height * SCALE)
  const ctx = canvas.getContext('2d')
  if (ctx === null) {
    throw new Error('no canvas')
  }
  ctx.scale(SCALE, SCALE)

  // The frame, then everything inside clipped to the inner rounded box.
  const full = { x: 0, y: 0, w: origin.width, h: origin.height }
  roundRectPath(ctx, full, 16)
  ctx.fillStyle = angled(ctx, full, look.frameAngle ?? 150, look.frameStops)
  ctx.fill()

  const card = boxOf(inner, origin)
  ctx.save()
  roundRectPath(ctx, card, 13)
  ctx.clip()
  ctx.fillStyle = CARD_BG
  ctx.fillRect(card.x, card.y, card.w, card.h)
  if (arenaImage !== null) {
    ctx.globalAlpha = 0.9
    drawCover(ctx, arenaImage, card, 0.7, 0.4)
    ctx.globalAlpha = 1
  }

  // Spotlight tint from above, then the darkening towards the bottom.
  const spotX = card.x + card.w * 0.75
  const spotY = card.y - card.h * 0.05
  const reach = Math.hypot(card.w * 0.75, card.h * 1.05) * 0.6
  const tint = ctx.createRadialGradient(spotX, spotY, 0, spotX, spotY, reach)
  tint.addColorStop(0, look.tint)
  tint.addColorStop(1, 'rgba(0,0,0,0)')
  ctx.fillStyle = tint
  ctx.fillRect(card.x, card.y, card.w, card.h)
  const shade = ctx.createLinearGradient(0, card.y, 0, card.y + card.h)
  shade.addColorStop(0, 'rgba(14,21,36,0.10)')
  shade.addColorStop(0.48, 'rgba(14,21,36,0.45)')
  shade.addColorStop(0.8, CARD_BG)
  ctx.fillStyle = shade
  ctx.fillRect(card.x, card.y, card.w, card.h)

  if (photo !== null && photoImage !== null) {
    drawFadedPhoto(ctx, photoImage, boxOf(photo, origin))
  }
  const jersey = frame.querySelector('[data-card="jersey"]')
  if (jersey !== null) {
    drawJersey(ctx, jersey, origin)
  }
  if (frame.querySelector('[data-card="scrim"]') !== null) {
    ctx.fillStyle = horizontal(ctx, card, [
      [0, 'rgba(14,21,36,0.78)'],
      [0.32, 'rgba(14,21,36,0.35)'],
      [0.55, 'rgba(14,21,36,0)'],
    ])
    ctx.fillRect(card.x, card.y, card.w, card.h)
  }

  drawLines(ctx, frame, origin, look)
  // Premium gold card: the "PREMIUM" plate (its text comes with drawTexts).
  const premiumBadge = frame.querySelector('[data-card="premium-badge"]')
  if (premiumBadge !== null) {
    const badge = boxOf(premiumBadge, origin)
    // The blurred backdrop, then the same tint and light rim as on screen;
    // the gold text comes with drawTexts.
    frostBehind(ctx, canvas, badge, badge.h / 2)
    roundRectPath(ctx, badge, badge.h / 2)
    ctx.fillStyle = angled(ctx, badge, 180, [
      [0, 'rgba(255,255,255,0.18)'],
      [1, 'rgba(10,14,24,0.55)'],
    ])
    ctx.fill()
    ctx.lineWidth = 1
    ctx.strokeStyle = 'rgba(255,255,255,0.35)'
    ctx.stroke()
  }
  const emblem = frame.querySelector('[data-card="emblem"]')
  if (emblem !== null) {
    await drawEmblem(ctx, emblem, origin)
  }
  drawTexts(ctx, frame, origin)
  ctx.restore()

  return new Promise((resolve, reject) => {
    canvas.toBlob((blob) => (blob !== null ? resolve(blob) : reject(new Error('empty card image'))), 'image/png')
  })
}
