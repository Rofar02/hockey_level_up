// Reference-counted so stacked overlays (Modal, PhasePreviewSheet, a Modal
// opened on top of another Modal -- see ProfilePage's skills-detail-over-
// profile-details case) share one lock: only the first to mount actually
// applies it (and records the scroll position to restore), every later one
// just bumps the count, and only the last one to unmount lifts it.
let bodyLockCount = 0
let scrollYBeforeLock = 0

// `overflow: hidden` on body alone (the previous approach) only stops
// wheel/keyboard scroll -- iOS Safari (and some Android WebViews) still
// let a touchmove drag the *page* behind a `position: fixed` backdrop,
// because overflow:hidden doesn't establish a new scroll container there
// the way it does on desktop. Found 2026-08-27: users could swipe inside an
// open overlay (DayPreviewModal, ExerciseDetailModal, ...) and watch the
// background page scroll instead of the overlay's own content. Pinning body
// itself to `position: fixed` during the lock removes it from the
// scrollable layout entirely, which is the actually-reliable cross-browser
// way to stop that -- `top` is offset by the saved scroll position so the
// page doesn't visibly jump to its top the instant the lock engages, and
// window.scrollTo restores it on unlock.
export function lockBodyScroll(): void {
  if (bodyLockCount === 0) {
    scrollYBeforeLock = window.scrollY
    document.body.style.position = 'fixed'
    document.body.style.top = `-${scrollYBeforeLock}px`
    document.body.style.left = '0'
    document.body.style.right = '0'
    document.body.style.overflow = 'hidden'
  }
  bodyLockCount += 1
}

export function unlockBodyScroll(): void {
  bodyLockCount = Math.max(0, bodyLockCount - 1)
  if (bodyLockCount === 0) {
    document.body.style.position = ''
    document.body.style.top = ''
    document.body.style.left = ''
    document.body.style.right = ''
    document.body.style.overflow = ''
    window.scrollTo(0, scrollYBeforeLock)
  }
}
