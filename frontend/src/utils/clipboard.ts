// navigator.clipboard is only defined in a secure context (https, or
// localhost) -- a phone hitting the dev server over plain http at the PC's
// LAN IP (see README) doesn't get it at all, so this falls back to the
// old-but-universal execCommand trick rather than silently doing nothing.
function copyTextFallback(text: string): boolean {
  const textarea = document.createElement('textarea')
  textarea.value = text
  textarea.style.position = 'fixed'
  textarea.style.opacity = '0'
  document.body.appendChild(textarea)
  textarea.focus()
  textarea.select()
  let succeeded = false
  try {
    succeeded = document.execCommand('copy')
  } catch {
    succeeded = false
  }
  document.body.removeChild(textarea)
  return succeeded
}

// True when the text made it to the clipboard either way.
export async function copyText(text: string): Promise<boolean> {
  if (navigator.clipboard !== undefined && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(text)
      return true
    } catch {
      // Fall through to the fallback.
    }
  }
  return copyTextFallback(text)
}
