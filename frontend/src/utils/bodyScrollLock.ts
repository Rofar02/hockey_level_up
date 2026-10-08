import { getAppScroller } from './appScroller'

// Reference-counted so stacked overlays (Modal, PhasePreviewSheet, a Modal
// opened on top of another Modal -- see ProfilePage's skills-detail-over-
// profile-details case) share one lock: only the first to mount actually
// applies it, every later one just bumps the count, and only the last one to unmount lifts it.
let bodyLockCount = 0

// 2026-10-08: the page scrolls #root, not the document (see index.css and
// appScroller.ts), so the lock is `overflow: hidden` on that container --
// unlike the document body, an element scroller with overflow hidden really
// stops touch scrolling on iOS too, and keeps its scrollTop, so there is no
// position to save and restore. (It used to pin body with position: fixed
// and a negative top, because body's own overflow: hidden doesn't stop a
// touch drag of the page on iOS.)
export function lockBodyScroll(): void {
  if (bodyLockCount === 0) {
    getAppScroller().style.overflowY = 'hidden'
  }
  bodyLockCount += 1
}

export function unlockBodyScroll(): void {
  bodyLockCount = Math.max(0, bodyLockCount - 1)
  if (bodyLockCount === 0) {
    getAppScroller().style.overflowY = ''
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
  getAppScroller().style.overflowY = ''
  // Leftovers of the old body-pinning lock, in case a pre-2026-10-08 page
  // state is restored from bfcache.
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
