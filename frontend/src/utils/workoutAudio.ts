// Lock-screen player for the workout timer -- EXPERIMENT (2026-10-03), off
// unless the athlete turns it on in Settings → Уведомления.
//
// A web page can't draw on the lock screen, but every mobile browser shows
// its own media widget (title, artwork, progress bar, play/pause/next) for a
// page that is playing audio, filled from the Media Session API. Three
// tricks borrowed from small open-source workout/interval PWAs:
//  1. A silent looping <audio> element is what makes the page "media" in
//     the first place -- Chrome on Android then shows the widget and stops
//     suspending the page; iOS shows the widget too. An <audio>, never a
//     <video>: iOS cuts a video's sound the moment the screen locks.
//  2. navigator.audioSession.type = 'playback' (iOS 16.4+) asks iOS to keep
//     the page's audio running with the screen locked (and through the
//     silent switch). Reported reliable from iOS 17.5 on.
//  3. Beeps are scheduled ahead of time on the AudioContext clock rather
//     than fired from JS timers -- the audio thread keeps playing them on
//     time even while iOS has frozen the page's JavaScript. The timer's own
//     state catches up the moment the page wakes (see TimerPlayer).

import { getSharedAudioContext } from './restNotification'

const ENABLED_KEY = 'icelevel.lockScreenPlayer'

export function isLockScreenPlayerEnabled(): boolean {
  try {
    return localStorage.getItem(ENABLED_KEY) === '1'
  } catch {
    return false
  }
}

export function setLockScreenPlayerEnabled(enabled: boolean): void {
  try {
    if (enabled) {
      localStorage.setItem(ENABLED_KEY, '1')
    } else {
      localStorage.removeItem(ENABLED_KEY)
    }
  } catch {
    // Private mode / blocked storage -- the experiment just stays off.
  }
}

export function isLockScreenPlayerSupported(): boolean {
  return 'mediaSession' in navigator
}

// 2 s of 8 kHz 16-bit mono silence as an in-memory WAV -- no asset to ship.
function silentWavUrl(): string {
  const sampleRate = 8000
  const samples = sampleRate * 2
  const buffer = new ArrayBuffer(44 + samples * 2)
  const view = new DataView(buffer)
  const writeText = (offset: number, text: string) => {
    for (let i = 0; i < text.length; i += 1) {
      view.setUint8(offset + i, text.charCodeAt(i))
    }
  }
  writeText(0, 'RIFF')
  view.setUint32(4, 36 + samples * 2, true)
  writeText(8, 'WAVE')
  writeText(12, 'fmt ')
  view.setUint32(16, 16, true)
  view.setUint16(20, 1, true)
  view.setUint16(22, 1, true)
  view.setUint32(24, sampleRate, true)
  view.setUint32(28, sampleRate * 2, true)
  view.setUint16(32, 2, true)
  view.setUint16(34, 16, true)
  writeText(36, 'data')
  view.setUint32(40, samples * 2, true)
  return URL.createObjectURL(new Blob([buffer], { type: 'audio/wav' }))
}

let keepAliveAudio: HTMLAudioElement | null = null

export interface LockScreenHandlers {
  onPlay: () => void
  onPause: () => void
  onNext?: () => void
}

export interface LockScreenInfo {
  title: string
  subtitle: string
  artworkUrl?: string
}

// Must be called from inside a real tap (audio.play() needs a gesture).
export function startLockScreenSession(info: LockScreenInfo, handlers: LockScreenHandlers): void {
  if (!isLockScreenPlayerSupported()) {
    return
  }
  const audioSession = (navigator as Navigator & { audioSession?: { type: string } }).audioSession
  if (audioSession !== undefined) {
    try {
      audioSession.type = 'playback'
    } catch {
      // Older iOS -- the widget still works, background audio may not.
    }
  }
  if (keepAliveAudio === null) {
    keepAliveAudio = new Audio(silentWavUrl())
    keepAliveAudio.loop = true
  }
  void keepAliveAudio.play().catch(() => {})
  updateLockScreenInfo(info)
  const session = navigator.mediaSession
  session.setActionHandler('play', handlers.onPlay)
  session.setActionHandler('pause', handlers.onPause)
  session.setActionHandler('nexttrack', handlers.onNext ?? null)
}

export function updateLockScreenInfo(info: LockScreenInfo): void {
  if (!isLockScreenPlayerSupported()) {
    return
  }
  navigator.mediaSession.metadata = new MediaMetadata({
    title: info.title,
    artist: info.subtitle,
    album: 'IceLevel',
    artwork: info.artworkUrl
      ? [{ src: info.artworkUrl, sizes: '512x512', type: info.artworkUrl.startsWith('data:image/png') ? 'image/png' : 'image/jpeg' }]
      : [],
  })
}

// The lock-screen progress bar animates on its own from this snapshot.
export function updateLockScreenProgress(totalSeconds: number, remainingSeconds: number, playing: boolean): void {
  if (!isLockScreenPlayerSupported()) {
    return
  }
  navigator.mediaSession.playbackState = playing ? 'playing' : 'paused'
  if (totalSeconds <= 0) {
    return
  }
  try {
    navigator.mediaSession.setPositionState({
      duration: totalSeconds,
      position: Math.min(totalSeconds, Math.max(0, totalSeconds - remainingSeconds)),
      playbackRate: playing ? 1 : 1e-6,
    })
  } catch {
    // Some browsers reject an edge value mid-transition -- the next update fixes it.
  }
}

export function stopLockScreenSession(): void {
  cancelScheduledBeeps()
  if (keepAliveAudio !== null) {
    keepAliveAudio.pause()
  }
  if (!isLockScreenPlayerSupported()) {
    return
  }
  navigator.mediaSession.metadata = null
  navigator.mediaSession.playbackState = 'none'
  for (const action of ['play', 'pause', 'nexttrack'] as const) {
    navigator.mediaSession.setActionHandler(action, null)
  }
}

// One timer segment ahead of us: `endsIn` seconds from now, and which tone
// marks its end ('work' ends -> rest starts, 'rest' ends -> work starts,
// 'done' = last round over).
export interface SegmentEnd {
  endsIn: number
  kind: 'work' | 'rest' | 'done'
}

let scheduledNodes: OscillatorNode[] = []

export function cancelScheduledBeeps(): void {
  for (const node of scheduledNodes) {
    try {
      node.stop()
    } catch {
      // Already played.
    }
  }
  scheduledNodes = []
}

function tone(ctx: AudioContext, at: number, frequency: number, length: number): void {
  const oscillator = ctx.createOscillator()
  const gain = ctx.createGain()
  oscillator.frequency.value = frequency
  gain.gain.setValueAtTime(0.25, at)
  gain.gain.exponentialRampToValueAtTime(0.001, at + length)
  oscillator.connect(gain)
  gain.connect(ctx.destination)
  oscillator.start(at)
  oscillator.stop(at + length)
  scheduledNodes.push(oscillator)
}

// Replaces whatever was scheduled before: three short ticks counting down
// the last 3 s of each segment, then its end tone -- high for "go"
// (rest over), lower for "rest" (work over), a double tone when done.
export function scheduleSegmentBeeps(segments: SegmentEnd[]): void {
  cancelScheduledBeeps()
  const ctx = getSharedAudioContext()
  if (ctx === null) {
    return
  }
  if (ctx.state === 'suspended') {
    void ctx.resume()
  }
  const now = ctx.currentTime
  for (const segment of segments) {
    const end = now + segment.endsIn
    for (const before of [3, 2, 1]) {
      if (segment.endsIn - before > 0.05) {
        tone(ctx, end - before, 660, 0.12)
      }
    }
    if (segment.kind === 'rest') {
      tone(ctx, end, 1046, 0.5)
    } else if (segment.kind === 'work') {
      tone(ctx, end, 523, 0.5)
    } else {
      tone(ctx, end, 784, 0.25)
      tone(ctx, end + 0.3, 1046, 0.5)
    }
  }
}
