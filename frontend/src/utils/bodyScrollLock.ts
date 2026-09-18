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

// 2026-09-17 fix (audit item #8): "нижняя шапка уехала" after the app sat
// backgrounded a while on iOS. bodyLockCount only ever lived in JS memory
// -- if a modal was open the instant iOS suspended/evicted the PWA's tab
// (any backgrounding can do this, not just a crash) and later restored it
// from bfcache, the DOM/CSS snapshot comes back exactly as it was
// (body.style.position:'fixed'; top:-Npx still applied), but this module
// reloads fresh with bodyLockCount = 0 -- as far as the new JS instance is
// concerned, no lock was ever taken, so nothing ever calls
// unlockBodyScroll to clear it. BottomNav itself was never mis-positioned
// -- the whole page's content just sits shifted by the stuck negative
// `top`, which reads as "the bottom bar moved".
//
// Call once at app startup, before anything has a chance to call
// lockBodyScroll for real: a fresh load/restore should never inherit a
// lock from a previous session, since bodyLockCount can't have a
// legitimate non-zero value yet at that point.
export function resetStaleBodyScrollLock(): void {
  bodyLockCount = 0
  document.body.style.position = ''
  document.body.style.top = ''
  document.body.style.left = ''
  document.body.style.right = ''
  document.body.style.overflow = ''
}

// Companion fix, same root cause class: WebKit is known to leave other
// small visual artifacts stuck after a long background freeze on iOS
// standalone (home-screen PWA), beyond just this stuck body offset --
// forcing a reflow on return to foreground is a cheap, broad hedge against
// that whole family, not just this one bug. pageshow (persisted=true is
// the actual bfcache-restore signal) covers the bfcache-restore case
// directly; visibilitychange covers plain background/foreground without a
// full bfcache cycle.
export function installForegroundReflowFix(): () => void {
  function reflow() {
    // 2026-09-18 fix (round 2 audit item #1): dispatching a synthetic
    // 'resize' event alone only notifies JS listeners (e.g.
    // CoachmarkProvider's own measure-on-resize, still worth keeping
    // below for whenever a coachmark happens to be open at this moment)
    // -- it does not make WebKit itself redo layout/repaint its
    // `position: fixed` compositor layers, which is the actual mechanism
    // behind the stuck-visual-artifact family this function hedges
    // against. Reading a layout-dependent property forces a real,
    // synchronous reflow right here; `void` discards the value, since
    // only the side effect of reading it is wanted.
    void document.body.offsetHeight
    window.dispatchEvent(new Event('resize'))
  }
  function onVisibilityChange() {
    if (document.visibilityState === 'visible') {
      reflow()
    }
  }
  function onPageShow(event: PageTransitionEvent) {
    if (event.persisted) {
      resetStaleBodyScrollLock()
      reflow()
    }
  }
  document.addEventListener('visibilitychange', onVisibilityChange)
  window.addEventListener('pageshow', onPageShow)
  return () => {
    document.removeEventListener('visibilitychange', onVisibilityChange)
    window.removeEventListener('pageshow', onPageShow)
  }
}
