import { useEffect, useRef, useState } from 'react'
import type { PointerEvent as ReactPointerEvent } from 'react'
import { Button } from './ui/Button'
import { Modal } from './ui/Modal'

// Square framing for a new avatar, before it's uploaded: drag the photo,
// zoom with the slider. The bottom of the frame previews the player card's
// fade, so the player sees what will dissolve. The crop happens here, in
// the browser -- the server gets a square and has nothing left to guess
// (its own automatic crop used to cut heads off tall photos).

const FRAME_SIZE = 280
const OUTPUT_SIZE = 800
const MAX_ZOOM = 3
// A tall photo opens with its top in frame (that's where the face is).
const INITIAL_TOP_BIAS = 0.1
// How far the photo may slide down, leaving room above a head that touches
// the photo's own top edge. The gap is filled with the card's dark colour
// and blends into the arena behind it.
const MAX_HEADROOM = FRAME_SIZE * 0.35
const FILL_COLOR = '#0E1524'
// Height of the soft blend from that fill into the photo's top edge.
const TOP_BLEND = 48

interface Offset {
  x: number
  y: number
}

interface AvatarCropModalProps {
  file: File
  onCancel: () => void
  onConfirm: (cropped: File) => void
  // Browser can't open the file (HEIC on some phones): upload it as is and
  // let the server do its automatic crop.
  onUnreadable: (original: File) => void
}

export function AvatarCropModal({ file, onCancel, onConfirm, onUnreadable }: AvatarCropModalProps) {
  const [imageUrl, setImageUrl] = useState<string | null>(null)
  const imageRef = useRef<HTMLImageElement>(null)
  const [natural, setNatural] = useState<{ width: number; height: number } | null>(null)
  const [zoom, setZoom] = useState(1)
  const [offset, setOffset] = useState<Offset>({ x: 0, y: 0 })
  const dragRef = useRef<{ pointerId: number; startX: number; startY: number; origin: Offset } | null>(null)

  // Created and revoked by the same effect -- a URL made once in useState
  // and revoked in a cleanup dies on StrictMode's mount-unmount-mount, and
  // the photo then "fails to load".
  useEffect(() => {
    const url = URL.createObjectURL(file)
    setImageUrl(url)
    return () => URL.revokeObjectURL(url)
  }, [file])

  const baseScale = natural !== null ? FRAME_SIZE / Math.min(natural.width, natural.height) : 1
  const scale = baseScale * zoom
  const shownWidth = (natural?.width ?? 0) * scale
  const shownHeight = (natural?.height ?? 0) * scale

  // The photo covers the frame's sides and bottom; at the top it may leave
  // some headroom (see MAX_HEADROOM).
  function clamp(next: Offset, width = shownWidth, height = shownHeight): Offset {
    return {
      x: Math.min(0, Math.max(FRAME_SIZE - width, next.x)),
      y: Math.min(MAX_HEADROOM, Math.max(FRAME_SIZE - height, next.y)),
    }
  }

  function handleLoad() {
    const image = imageRef.current
    if (image === null) {
      return
    }
    const size = { width: image.naturalWidth, height: image.naturalHeight }
    const fit = FRAME_SIZE / Math.min(size.width, size.height)
    const width = size.width * fit
    const height = size.height * fit
    setNatural(size)
    setOffset({ x: (FRAME_SIZE - width) / 2, y: -(height - FRAME_SIZE) * INITIAL_TOP_BIAS })
  }

  function handleZoom(nextZoom: number) {
    if (natural === null) {
      return
    }
    // Zoom around the frame's centre, not the photo's corner.
    const nextScale = baseScale * nextZoom
    const centre = FRAME_SIZE / 2
    const ratio = nextScale / scale
    const next = { x: centre - (centre - offset.x) * ratio, y: centre - (centre - offset.y) * ratio }
    setZoom(nextZoom)
    setOffset(clamp(next, natural.width * nextScale, natural.height * nextScale))
  }

  function handlePointerDown(event: ReactPointerEvent<HTMLDivElement>) {
    try {
      // Keeps the drag going when the finger slides off the frame.
      event.currentTarget.setPointerCapture(event.pointerId)
    } catch {
      // Not capturable (stale pointer) -- dragging still works inside the frame.
    }
    dragRef.current = { pointerId: event.pointerId, startX: event.clientX, startY: event.clientY, origin: offset }
  }

  function handlePointerMove(event: ReactPointerEvent<HTMLDivElement>) {
    const drag = dragRef.current
    if (drag === null || drag.pointerId !== event.pointerId) {
      return
    }
    setOffset(
      clamp({ x: drag.origin.x + event.clientX - drag.startX, y: drag.origin.y + event.clientY - drag.startY }),
    )
  }

  function handlePointerUp() {
    dragRef.current = null
  }

  function handleConfirm() {
    const image = imageRef.current
    if (image === null || natural === null) {
      return
    }
    // Exactly what the frame shows, scaled up to the output size.
    const outputSize = Math.min(OUTPUT_SIZE, Math.round(FRAME_SIZE / scale))
    const k = outputSize / FRAME_SIZE
    const canvas = document.createElement('canvas')
    canvas.width = outputSize
    canvas.height = outputSize
    const context = canvas.getContext('2d')
    if (context === null) {
      onUnreadable(file)
      return
    }
    context.fillStyle = FILL_COLOR
    context.fillRect(0, 0, outputSize, outputSize)
    context.drawImage(image, offset.x * k, offset.y * k, shownWidth * k, shownHeight * k)
    if (offset.y > 0) {
      // Soften the photo's own top edge into the fill above it.
      const gradient = context.createLinearGradient(0, offset.y * k, 0, (offset.y + TOP_BLEND) * k)
      gradient.addColorStop(0, FILL_COLOR)
      gradient.addColorStop(1, `${FILL_COLOR}00`)
      context.fillStyle = gradient
      context.fillRect(0, offset.y * k, outputSize, TOP_BLEND * k)
    }
    canvas.toBlob(
      (blob) => {
        if (blob === null) {
          onUnreadable(file)
          return
        }
        onConfirm(new File([blob], 'avatar.jpg', { type: 'image/jpeg' }))
      },
      'image/jpeg',
      0.9,
    )
  }

  return (
    <Modal title="Кадр для карточки" onClose={onCancel}>
      <div className="flex flex-col items-center gap-4">
        <p className="text-sm text-[#8A94A6]">Подвиньте фото пальцем, приблизьте ползунком. Если голова упирается в край — опустите фото ниже. Низ кадра растворится на карточке.</p>
        <div
          className="relative touch-none select-none overflow-hidden rounded-md bg-[#0E1524]"
          style={{ width: FRAME_SIZE, height: FRAME_SIZE, cursor: 'grab' }}
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
          onPointerCancel={handlePointerUp}
        >
          {imageUrl !== null && (
          <img
            ref={imageRef}
            src={imageUrl}
            alt="Новое фото"
            draggable={false}
            onLoad={handleLoad}
            onError={() => onUnreadable(file)}
            className="pointer-events-none absolute left-0 top-0 max-w-none"
            style={{
              width: shownWidth || undefined,
              height: shownHeight || undefined,
              transform: `translate(${offset.x}px, ${offset.y}px)`,
              visibility: natural === null ? 'hidden' : 'visible',
            }}
          />
          )}
          {offset.y > 0 && (
            <div
              className="pointer-events-none absolute inset-x-0"
              style={{
                top: offset.y,
                height: TOP_BLEND,
                background: `linear-gradient(to bottom, ${FILL_COLOR}, ${FILL_COLOR}00)`,
              }}
            />
          )}
          {/* Preview of the card's bottom fade. */}
          <div className="pointer-events-none absolute inset-x-0 bottom-0 h-[45%] bg-gradient-to-b from-transparent to-[#0E1524]/90" />
          <div className="pointer-events-none absolute inset-0 rounded-md ring-1 ring-inset ring-accent-ice/40" />
        </div>
        <label className="flex w-full max-w-[280px] items-center gap-3 text-xs text-[#8A94A6]">
          <i className="ti ti-zoom-out text-base" aria-hidden="true" />
          <input
            type="range"
            min={1}
            max={MAX_ZOOM}
            step={0.01}
            value={zoom}
            onChange={(event) => handleZoom(Number(event.target.value))}
            aria-label="Приближение"
            className="flex-1 accent-[#D7EFFF]"
          />
          <i className="ti ti-zoom-in text-base" aria-hidden="true" />
        </label>
        <div className="flex w-full gap-2">
          <Button type="button" variant="neutral" onClick={onCancel} className="flex-1">
            Отмена
          </Button>
          <Button type="button" onClick={handleConfirm} disabled={natural === null} className="flex-1">
            Готово
          </Button>
        </div>
      </div>
    </Modal>
  )
}
