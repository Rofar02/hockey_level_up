// The app's one scroll container (#root, see index.css): the document itself
// never scrolls, so window.scrollTo/scrollY do nothing -- scroll this instead.
export function getAppScroller(): HTMLElement {
  return document.getElementById('root') ?? document.documentElement
}

// iOS still pans the (non-scrollable) document to bring a focused field into
// view above the keyboard, and doesn't always pan it back when the keyboard
// closes -- which leaves every fixed element, the tab bar included, shifted.
// Snap the document back whenever it has moved and nobody is typing.
export function installDocumentScrollGuard(): void {
  const snapBack = () => {
    const element = document.activeElement
    const typing =
      element instanceof HTMLTextAreaElement ||
      (element instanceof HTMLElement && element.isContentEditable) ||
      (element instanceof HTMLInputElement && !['checkbox', 'radio', 'button', 'submit', 'reset', 'range', 'color', 'file', 'image'].includes(element.type))
    if (!typing && (window.scrollX !== 0 || window.scrollY !== 0)) {
      window.scrollTo(0, 0)
    }
  }
  const snapBackSoon = () => {
    // The keyboard animates away after blur.
    window.setTimeout(snapBack, 50)
    window.setTimeout(snapBack, 400)
  }
  window.addEventListener('scroll', snapBack, { passive: true })
  window.addEventListener('focusout', snapBackSoon)
  window.addEventListener('pageshow', snapBackSoon)
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') {
      snapBackSoon()
    }
  })
}
