import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App.tsx'
import { AuthProvider } from './context/AuthContext.tsx'
import { registerServiceWorker } from './push.ts'
import { installForegroundReflowFix, resetStaleBodyScrollLock } from './utils/bodyScrollLock.ts'
import { installAudioUnlockOnFirstGesture } from './utils/restNotification.ts'
import './index.css'

registerServiceWorker()

// 2026-09-17 fix (audit item #8): must run before anything in the app tree
// gets a chance to call lockBodyScroll for real -- see
// resetStaleBodyScrollLock's own docstring for why a fresh load/bfcache-
// restore can otherwise inherit a stuck scroll lock from a previous
// session.
resetStaleBodyScrollLock()
installForegroundReflowFix()
// 2026-09-17 fix (audit item #9): unlocks the shared timer-beep
// AudioContext from inside the session's first real tap -- see
// installAudioUnlockOnFirstGesture's own docstring.
installAudioUnlockOnFirstGesture()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <App />
      </AuthProvider>
    </BrowserRouter>
  </StrictMode>,
)
