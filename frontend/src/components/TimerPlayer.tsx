import { useEffect, useRef, useState } from 'react'
import { CountdownRing } from './ui/CountdownRing'
import { Stepper } from './ui/Stepper'
import { ExerciseFeedbackPrompt } from './ExerciseFeedbackPrompt'
import { LastTimeHint } from './ExerciseHistory'
import * as progressApi from '../api/progress'
import * as setCompletionsApi from '../api/setCompletions'
import * as trainingSessionsApi from '../api/trainingSessions'
import type { ExerciseRead } from '../types/exercise'
import type { ExerciseHistorySession } from '../types/setCompletion'
import {
  alertTimerDone,
  ensureNotificationPermission,
  scheduleRestDoneNotification,
  type ScheduledRestNotification,
} from '../utils/restNotification'
import { renderLockScreenArtwork } from '../utils/lockScreenArtwork'
import { exercisePosterUrl } from '../utils/media'
import {
  cancelScheduledBeeps,
  holdLockScreen,
  isLockScreenHandoffPending,
  isLockScreenPlayerEnabled,
  isLockScreenPlayerSupported,
  markLockScreenHandoff,
  takeLockScreenHandoff,
  scheduleSegmentBeeps,
  startLockScreenSession,
  stopLockScreenSession,
  updateLockScreenInfo,
  updateLockScreenProgress,
  type SegmentEnd,
} from '../utils/workoutAudio'

// Where the timer stood, kept across leaving the app (2026-10-03: an iPhone
// home-screen app is often reloaded from scratch when reopened, and the
// round started over). Device-local and short-lived on purpose: the rounds
// already finished are on the server anyway (re-read on mount), this only
// adds the segment in progress -- work or rest, its deadline, paused or not.
const SNAPSHOT_PREFIX = 'icelevel.timer.'
const SNAPSHOT_MAX_AGE_MS = 3 * 60 * 60 * 1000

interface TimerSnapshot {
  phase: 'work' | 'rest'
  completedRounds: number
  running: boolean
  deadline: number | null
  remaining: number
  durationSeconds: number
  savedAt: number
}

function readSnapshot(key: string): TimerSnapshot | null {
  try {
    const raw = localStorage.getItem(SNAPSHOT_PREFIX + key)
    if (raw === null) {
      return null
    }
    const snapshot = JSON.parse(raw) as TimerSnapshot
    if (Date.now() - snapshot.savedAt > SNAPSHOT_MAX_AGE_MS) {
      localStorage.removeItem(SNAPSHOT_PREFIX + key)
      return null
    }
    return snapshot
  } catch {
    return null
  }
}

function writeSnapshot(key: string, snapshot: TimerSnapshot | null): void {
  try {
    if (snapshot === null) {
      localStorage.removeItem(SNAPSHOT_PREFIX + key)
    } else {
      localStorage.setItem(SNAPSHOT_PREFIX + key, JSON.stringify(snapshot))
    }
  } catch {
    // Private mode / full storage -- the timer just won't survive a reload.
  }
}

// Continuous warm-up / cool-down: the pause between one exercise and the
// next, announced on the lock screen ("ДАЛЕЕ ...") and closed by the
// face-off whistle, after which the next timed exercise starts by itself.
const TRANSITION_SECONDS = 5

// Fallback rest between rounds when the exercise has no configured
// rest_seconds -- preserves the old always-advances behavior instead of
// skipping straight to the next round with zero pause.
const FALLBACK_REST_SECONDS = 3

// Mode A ("на время") -- one CountdownRing that IS the player (media-player
// redesign, 2026-08-28: "хочу чтобы это было прям как медиаплеер"). Tapping
// the ring itself starts/pauses a round; the same ring switches to a
// persimmon "Отдых" state between rounds using the exercise's real
// rest_seconds, then auto-continues into the next round -- no separate
// button, no fake pause-with-cancel.
export function TimerPlayer({
  exercise,
  trainingSessionId,
  accessToken,
  durationSeconds,
  history,
  rounds,
  isDone,
  onComplete,
  onSettled,
  nextExercise = null,
}: {
  exercise: ExerciseRead
  trainingSessionId: string
  accessToken: string
  durationSeconds: number
  // Past sessions (ExerciseDetailBody's single fetch) -- only for the
  // "В прошлый раз" line under the ring.
  history: ExerciseHistorySession[] | null
  rounds: number
  isDone: boolean
  onComplete?: () => void
  // Fires once the post-completion feedback prompt is answered -- see
  // ExerciseDetailBodyProps' own comment for how this differs from
  // onComplete (which fires earlier, right as the last round finishes).
  onSettled?: () => void
  // Next exercise of this phase (null = this is the last one). Used only by
  // the continuous warm-up / cool-down mode of the lock-screen player.
  nextExercise?: ExerciseRead | null
}) {
  const [completedRounds, setCompletedRounds] = useState(0)
  const [phase, setPhase] = useState<'work' | 'rest'>('work')
  const [remaining, setRemaining] = useState(durationSeconds)
  const [running, setRunning] = useState(false)
  // Honest-fact override for the round currently paused mid-count (referencing
  // a competitor's flow the athlete asked to bring over, 2026-08-31): null
  // means "not paused mid-round" (either still running, or never started).
  // Set to the elapsed seconds the instant the ring is paused, so the
  // athlete can confirm early with what they actually did instead of only
  // ever being able to log the full target duration -- editable via the
  // Stepper below before confirming, same "suggestion, not a mandate"
  // pattern SetLogger's reps/weight steppers already use.
  const [manualSeconds, setManualSeconds] = useState<number | null>(null)
  // Flips once the last round finishes -- gates the "Как ощущения?" prompt
  // below. Deliberately local-only (not derived from `isDone`): `isDone`
  // covers reopening an exercise that was ALREADY completed on a previous
  // visit, which must never re-show the prompt or re-fire onSettled.
  const [showFeedback, setShowFeedback] = useState(false)
  // Separate from showFeedback -- found live-testing this exact flow
  // (2026-08-28): when this is the LAST exercise in its phase,
  // handleExerciseSettled has nowhere to advance to, so this component
  // never unmounts and showFeedback never resets. Without this flag the
  // answered prompt just sat there, still tappable, instead of settling
  // into a plain "Готово" like SetLogger's own (`feedback !== null`)
  // read-only branch already does for the exact same last-exercise case.
  const [feedbackAnswered, setFeedbackAnswered] = useState(false)
  const onCompleteRef = useRef(onComplete)
  onCompleteRef.current = onComplete
  const onSettledRef = useRef(onSettled)
  onSettledRef.current = onSettled
  // Wall-clock deadline for the currently-running segment, not a tick
  // counter -- a plain "decrement once a second" timer stalls while the
  // screen is locked (mobile browsers throttle/suspend setTimeout in a
  // backgrounded tab), then just resumes counting from wherever it was
  // frozen once unlocked, silently eating however long the phone was
  // locked (found live-testing 2026-08-30: "поставил плей, заблокировал
  // экран, всё сбилось"). Anchoring to Date.now() means the countdown is
  // always correct the instant it's read, locked or not. A ref, not state
  // -- it's an implementation detail the effect below reads, never
  // something a render should react to.
  const deadlineRef = useRef<number | null>(null)
  // Background (on-device) notification for the current rest segment, same
  // mechanism as ExerciseDetailModal's RestTimer -- scheduled the instant
  // rest starts (see advanceWork below) and cancelled the instant it's no
  // longer relevant (rest ends naturally, is skipped, or this component
  // unmounts mid-rest), so it never fires stale.
  const scheduledRestNotificationRef = useRef<ScheduledRestNotification>({ cancel: () => {} })

  const restSeconds = exercise.rest_seconds ?? FALLBACK_REST_SECONDS

  // One-sided exercise done side by side (2026-10-03: each round is one
  // side, rounds alternate) -- "Правая" / "Левая" instead of "Раунд N".
  function sideLabel(roundNumber: number): string | null {
    if (exercise.is_unilateral !== true || rounds < 2 || rounds % 2 !== 0) {
      return null
    }
    return roundNumber % 2 === 1 ? 'Правая' : 'Левая'
  }

  const snapshotKey = `${trainingSessionId}:${exercise.id}`
  // Restore once on mount: first the local snapshot (the segment in
  // progress), then the server's logged rounds, which win if they're ahead
  // (e.g. the snapshot was lost). A deadline that passed while the app was
  // closed is handled by the normal end-of-segment path right after.
  const restoredRef = useRef(false)
  const restoredActiveRef = useRef(false)
  useEffect(() => {
    if (isDone) {
      writeSnapshot(snapshotKey, null)
      return
    }
    const snapshot = readSnapshot(snapshotKey)
    restoredActiveRef.current = snapshot !== null && snapshot.completedRounds < rounds
    if (snapshot !== null && snapshot.completedRounds < rounds) {
      setCompletedRounds(snapshot.completedRounds)
      setPhase(snapshot.phase)
      if (snapshot.running && snapshot.deadline !== null) {
        deadlineRef.current = snapshot.deadline
        setRemaining(Math.max(0, (snapshot.deadline - Date.now()) / 1000))
        setRunning(true)
      } else {
        setRemaining(snapshot.remaining)
      }
    }
    restoredRef.current = true
    let cancelled = false
    trainingSessionsApi
      .getExerciseSets(trainingSessionId, exercise.id, accessToken)
      .then((result) => {
        if (cancelled) {
          return
        }
        const logged = result.sets.filter((set) => set.set_number <= rounds).length
        if (logged > (snapshot?.completedRounds ?? 0) && logged < rounds) {
          setCompletedRounds(logged)
          setPhase('work')
          setRunning(false)
          deadlineRef.current = null
          setRemaining(durationSeconds)
        }
      })
      .catch(() => {
        // Best-effort -- the local snapshot (or a fresh start) stands.
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- mount only
  }, [])

  // Saved on every state change (not every tick -- the deadline is enough
  // to know the rest), and once more when the app goes to the background.
  const saveSnapshotRef = useRef(() => {})
  saveSnapshotRef.current = () => {
    if (!restoredRef.current) {
      return
    }
    if (completedRounds >= rounds || isDone) {
      writeSnapshot(snapshotKey, null)
      return
    }
    if (completedRounds === 0 && phase === 'work' && !running && remaining >= durationSeconds) {
      writeSnapshot(snapshotKey, null)
      return
    }
    writeSnapshot(snapshotKey, {
      phase,
      completedRounds,
      running,
      deadline: running ? deadlineRef.current : null,
      remaining,
      durationSeconds,
      savedAt: Date.now(),
    })
  }
  useEffect(() => {
    saveSnapshotRef.current()
  }, [phase, completedRounds, running, isDone])
  useEffect(() => {
    const save = () => saveSnapshotRef.current()
    document.addEventListener('visibilitychange', save)
    window.addEventListener('pagehide', save)
    return () => {
      document.removeEventListener('visibilitychange', save)
      window.removeEventListener('pagehide', save)
    }
  }, [])

  // Lock-screen player experiment (utils/workoutAudio.ts) -- read once per
  // mount; the session itself starts on the first tap of the ring.
  const [lockScreen] = useState(() => isLockScreenPlayerEnabled() && isLockScreenPlayerSupported())
  const lockScreenStartedRef = useRef(false)
  // Continuous mode: warm-up / cool-down with the lock-screen player on --
  // finishing an exercise leads straight into the next one (see
  // TRANSITION_SECONDS) instead of waiting for a tap on the next ring.
  const continuous = lockScreen && (exercise.phase === 'warmup' || exercise.phase === 'cooldown')
  const nextIsTimed = nextExercise !== null && nextExercise.target_duration_seconds !== null
  const [transitionEndsAt, setTransitionEndsAt] = useState<number | null>(null)
  const inTransitionRef = useRef(false)
  // Set once the lock screen was handed to whatever comes next -- leaving
  // this exercise must then not replace it with the idle card.
  const handedOverRef = useRef(false)

  // The per-athlete target (time progression) arrives a moment after mount;
  // pick it up as long as nothing has started yet. Once the first round is
  // running or logged, the target in hand stays for the whole exercise.
  const durationSecondsRef = useRef(durationSeconds)
  const notStarted =
    !running && completedRounds === 0 && phase === 'work' && manualSeconds === null && remaining === durationSecondsRef.current
  useEffect(() => {
    // Only a CHANGED target re-syncs -- on mount this must not undo a
    // restored snapshot (that effect runs earlier in the same commit).
    if (durationSecondsRef.current === durationSeconds) {
      return
    }
    if (notStarted) {
      setRemaining(durationSeconds)
    }
    durationSecondsRef.current = durationSeconds
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only a new target should re-sync
  }, [durationSeconds])

  // Ticks the visible countdown down from deadlineRef while running. Only
  // depends on `running`, not `remaining`/`phase` -- advanceWork/advanceRest
  // below flip running false then true again in the same batch when moving
  // between work and rest, which React collapses into a no-op transition,
  // so this effect keeps the same interval/listener alive across a phase
  // change rather than tearing down and missing that transition. Each
  // advance*() call moves deadlineRef itself, which is all this effect
  // needs to pick up the new segment.
  useEffect(() => {
    if (!running) {
      return
    }
    function sync() {
      const deadline = deadlineRef.current
      if (deadline === null) {
        return
      }
      setRemaining(Math.max(0, (deadline - Date.now()) / 1000))
    }
    sync()
    const interval = setInterval(sync, 1000)
    // Recompute immediately on regaining visibility (screen unlock, tab
    // refocus) instead of waiting for the next 1s tick -- the whole point
    // is snapping to the true elapsed time right away rather than however
    // long is left on the throttled interval.
    document.addEventListener('visibilitychange', sync)
    return () => {
      clearInterval(interval)
      document.removeEventListener('visibilitychange', sync)
    }
  }, [running])

  // Separate from the ticking effect above -- this one only reacts to
  // remaining actually crossing zero, regardless of how it got there.
  // alertTimerDone() (vibration + beep) fires here for both segments: the
  // work ring running out and the rest ring running out, matching what
  // RestTimer already does for the sets/reps flow. Deliberately not inside
  // advanceWork() itself -- that function is also called from the manual
  // early-confirm button below, which shouldn't play the "time's up" alert.
  useEffect(() => {
    if (!running || remaining > 0) {
      return
    }
    setRunning(false)
    // With the lock-screen player on, the end tone was already scheduled
    // on the audio clock (and may have played long ago with the screen
    // locked) -- don't beep a second time when the page wakes up.
    if (!lockScreenStartedRef.current) {
      alertTimerDone()
    }
    if (phase === 'work') {
      advanceWork(durationSeconds, true)
    } else {
      advanceRest(true)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [running, remaining, phase])

  // Cancels any still-pending background rest notification if the athlete
  // navigates away mid-rest -- same cleanup RestTimer's own unmount does.
  useEffect(() => {
    return () => {
      scheduledRestNotificationRef.current.cancel()
    }
  }, [])

  // actualSeconds defaults to the full target -- the natural "ring counted
  // down to zero" path below always means the whole thing was done. A
  // manual early confirm (see the paused-mid-round controls further down)
  // passes whatever the athlete actually logged instead.
  // Where the next segment starts counting from. Normally "now"; with the
  // lock-screen player on, a segment that ran out on its own continues
  // from its own scheduled end, so after the page was frozen with the
  // screen locked the on-screen timer catches up with the beeps the athlete
  // already heard instead of restarting the rest from the moment of unlock.
  function nextSegmentStart(fromDeadline: boolean): number {
    if (fromDeadline && lockScreenStartedRef.current && deadlineRef.current !== null) {
      return deadlineRef.current
    }
    return Date.now()
  }

  function advanceWork(actualSeconds: number = durationSeconds, fromDeadline = false) {
    const segmentStart = nextSegmentStart(fromDeadline)
    const finishedSetNumber = completedRounds + 1
    // Honest record of what was actually done -- previously duration-mode
    // exercises left zero SetCompletion rows at all (found 2026-08-28
    // reviewing this against the backend's own already-built
    // duration_seconds_completed column). Best-effort/fire-and-forget: a
    // dropped save shouldn't block the athlete from continuing their
    // workout, same "don't let a network blip stall the flow" choice
    // SetLogger's own suggestion fetches make elsewhere in this file.
    setCompletionsApi
      .saveSet(
        {
          exercise_id: exercise.id,
          training_session_id: trainingSessionId,
          set_number: finishedSetNumber,
          weight_kg: null,
          reps_completed: null,
          duration_seconds_completed: actualSeconds,
        },
        accessToken,
      )
      .catch(() => {})

    setManualSeconds(null)

    if (finishedSetNumber >= rounds) {
      setCompletedRounds(rounds)
      onCompleteRef.current?.()
      if (continuous && lockScreenStartedRef.current && nextExercise !== null) {
        inTransitionRef.current = true
        setTransitionEndsAt(segmentStart + TRANSITION_SECONDS * 1000)
        return
      }
      if (exercise.phase === 'warmup' || exercise.phase === 'cooldown') {
        // Warm-up / cool-down are not rated -- go straight to "Готово".
        setFeedbackAnswered(true)
        onSettledRef.current?.()
      } else {
        setShowFeedback(true)
      }
      return
    }
    setCompletedRounds(finishedSetNumber)
    setPhase('rest')
    deadlineRef.current = segmentStart + restSeconds * 1000
    setRemaining(restSeconds)
    setRunning(true)

    // Same local-notification safety net as RestTimer, for whenever the
    // athlete backgrounds the tab mid-rest -- see utils/restNotification.ts
    // for why this is web-PWA best-effort, not a native guarantee.
    ensureNotificationPermission()
      .then(() => progressApi.getRestDonePhrase(accessToken))
      .then((phrase) => {
        scheduledRestNotificationRef.current = scheduleRestDoneNotification(restSeconds, phrase.text)
      })
      .catch(() => {
        // Best-effort -- worst case this specific rest period just has no
        // background notification, the on-screen countdown still works.
      })
  }

  function advanceRest(fromDeadline = false) {
    scheduledRestNotificationRef.current.cancel()
    const segmentStart = nextSegmentStart(fromDeadline)
    setPhase('work')
    deadlineRef.current = segmentStart + durationSeconds * 1000
    setRemaining(durationSeconds)
    setRunning(true)
  }

  function setWorkRunning(next: boolean) {
    if (next === running) {
      return
    }
    if (next) {
      // Resuming (or starting fresh) anchors a new deadline off whatever
      // `remaining` currently is, and drops any honest-fact override from a
      // previous pause -- the athlete chose to keep going, so the round
      // isn't finishing early after all.
      deadlineRef.current = Date.now() + remaining * 1000
      setManualSeconds(null)
    } else {
      // Paused mid-round -- capture what's actually elapsed so far as the
      // starting point for an early honest confirm. From the deadline, not
      // `remaining`: a pause from the lock screen can arrive while the page
      // was frozen and `remaining` is whatever the last tick before that was.
      const left =
        deadlineRef.current !== null ? Math.max(0, (deadlineRef.current - Date.now()) / 1000) : remaining
      setRemaining(left)
      setManualSeconds(Math.round(durationSeconds - left))
    }
    setRunning(next)
  }

  // The idle card for unmount, built by the latest render's function (the
  // cleanup above only sees the first render; drawn lazily, not per tick).
  const idleCardRef = useRef(() => idleLockScreenInfo())
  idleCardRef.current = () => idleLockScreenInfo()

  // Lock-screen buttons call whatever the latest render's handlers are.
  const lockScreenHandlersRef = useRef({ play: () => {}, pause: (): boolean => false, next: () => {} })
  lockScreenHandlersRef.current = {
    play: () => {
      if (phase === 'work') {
        setWorkRunning(true)
      }
    },
    // Pauses the work round in the app too. Rest has no pause in the app,
    // so there the lock-screen button is ignored and the rest runs on.
    pause: () => {
      if (phase !== 'work') {
        return false
      }
      setWorkRunning(false)
      return true
    },
    next: () => {
      if (inTransitionRef.current) {
        finishTransitionRef.current()
      } else if (phase === 'rest') {
        skipRest()
      }
    },
  }

  function lockScreenInfo() {
    const nextSide = sideLabel(completedRounds + 1)
    const artworkUrl =
      renderLockScreenArtwork({
        phase,
        exerciseName: exercise.name,
        seconds: phase === 'work' ? durationSeconds : restSeconds,
        detail:
          nextSide === null
            ? undefined
            : phase === 'work'
              ? `${durationSeconds} сек · ${nextSide.toLowerCase()}`
              : `${restSeconds} сек · дальше ${nextSide.toLowerCase()}`,
        rounds,
        completedRounds,
      }) ??
      (exercise.video_source_type === 'file' && exercise.video_source_id !== null
        ? exercisePosterUrl(exercise.video_source_id)
        : '/icon-512.png')
    const subtitle =
      nextSide !== null
        ? phase === 'work'
          ? `${nextSide} сторона`
          : `Отдых · дальше ${nextSide.toLowerCase()} сторона`
        : phase === 'work'
          ? `Раунд ${completedRounds + 1} из ${rounds} · работа`
          : `Отдых · дальше раунд ${completedRounds + 1} из ${rounds}`
    return { title: exercise.name, subtitle, artworkUrl }
  }

  // Whole exercise as one timeline (all work rounds + the rests between):
  // the lock-screen progress bar shows this, not the current segment.
  function exerciseTimeline(): { total: number; left: number } {
    const total = rounds * durationSeconds + Math.max(0, rounds - 1) * restSeconds
    const segmentTotal = phase === 'work' ? durationSeconds : restSeconds
    const segmentLeft =
      running && deadlineRef.current !== null ? Math.max(0, (deadlineRef.current - Date.now()) / 1000) : remaining
    const before =
      phase === 'work'
        ? completedRounds * (durationSeconds + restSeconds)
        : completedRounds * durationSeconds + Math.max(0, completedRounds - 1) * restSeconds
    const elapsed = before + (segmentTotal - segmentLeft)
    return { total, left: Math.max(0, total - elapsed) }
  }

  function idleLockScreenInfo() {
    return {
      title: 'IceLevel',
      subtitle: 'Тренировка идёт',
      artworkUrl: renderLockScreenArtwork({ phase: 'idle', exerciseName: exercise.name, rounds, completedRounds }) ?? '/icon-512.png',
    }
  }

  // Called from the ring tap itself -- audio may only start inside a gesture.
  function startLockScreenIfOn() {
    if (!lockScreen || lockScreenStartedRef.current) {
      return
    }
    lockScreenStartedRef.current = true
    startLockScreenSession(lockScreenInfo(), {
      onPlay: () => lockScreenHandlersRef.current.play(),
      onPause: () => lockScreenHandlersRef.current.pause(),
      onNext: () => lockScreenHandlersRef.current.next(),
    })
  }

  // Keeps the widget and the pre-scheduled beeps in step with the timer:
  // on every start/pause/segment change (not every tick), everything still
  // ahead is re-laid out on the audio clock from the current deadline.
  useEffect(() => {
    if (!lockScreenStartedRef.current) {
      return
    }
    if (completedRounds >= rounds) {
      if (inTransitionRef.current) {
        return
      }
      // Last round over -- let the final double tone finish, then release
      // the lock-screen widget.
      const idle = idleLockScreenInfo()
      const timeoutId = window.setTimeout(() => stopLockScreenSession(idle), 1500)
      return () => window.clearTimeout(timeoutId)
    }
    updateLockScreenInfo(lockScreenInfo())
    const endsIn =
      running && deadlineRef.current !== null ? Math.max(0, (deadlineRef.current - Date.now()) / 1000) : remaining
    const timeline = exerciseTimeline()
    updateLockScreenProgress(timeline.total, timeline.left, running)
    if (!running) {
      cancelScheduledBeeps()
      return
    }
    const segments: SegmentEnd[] = []
    let at = endsIn
    let round = completedRounds + 1
    let segmentPhase = phase
    for (;;) {
      if (segmentPhase === 'work') {
        if (round >= rounds) {
          if (continuous && nextExercise !== null) {
            // Shift buzzer, then the hand-over: stick taps and the face-off
            // whistle as the next exercise starts (or just the buzzer when
            // the next one is done at the athlete's own pace).
            segments.push({ endsIn: at, kind: 'work' })
            if (nextIsTimed) {
              segments.push({ endsIn: at + TRANSITION_SECONDS, kind: 'rest' })
            }
          } else {
            segments.push({ endsIn: at, kind: 'done' })
          }
          break
        }
        segments.push({ endsIn: at, kind: 'work' })
        at += restSeconds
        segmentPhase = 'rest'
      } else {
        segments.push({ endsIn: at, kind: 'rest' })
        round += 1
        at += durationSeconds
        segmentPhase = 'work'
      }
    }
    scheduleSegmentBeeps(segments)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- re-plan on state changes, not on every tick
  }, [running, phase, completedRounds, durationSeconds])

  useEffect(() => {
    return () => {
      if (lockScreenStartedRef.current && !handedOverRef.current && !isLockScreenHandoffPending()) {
        stopLockScreenSession(idleCardRef.current())
      }
    }
  }, [])

  // Browsers (iOS especially) drop or reset the media session's position
  // when the page comes back from the background -- the widget's progress
  // bar then restarts from zero. Re-assert it from the real deadline every
  // time the page is shown again.
  const resyncLockScreenRef = useRef(() => {})
  resyncLockScreenRef.current = () => {
    if (!lockScreenStartedRef.current || completedRounds >= rounds) {
      return
    }
    updateLockScreenInfo(lockScreenInfo())
    const timeline = exerciseTimeline()
    updateLockScreenProgress(timeline.total, timeline.left, running)
  }
  useEffect(() => {
    const resync = () => resyncLockScreenRef.current()
    document.addEventListener('visibilitychange', resync)
    window.addEventListener('pageshow', resync)
    window.addEventListener('focus', resync)
    return () => {
      document.removeEventListener('visibilitychange', resync)
      window.removeEventListener('pageshow', resync)
      window.removeEventListener('focus', resync)
    }
  }, [])

  // The hand-over: "ДАЛЕЕ <next>" on the lock screen with its own 5 s bar,
  // "далее" there (or "Начать сейчас" here) cuts it short. At the end the
  // session is handed to the next exercise's player (timed) or left on the
  // next exercise's card (sets), then the page advances.
  const finishTransitionRef = useRef(() => {})
  finishTransitionRef.current = () => {
    if (!inTransitionRef.current) {
      return
    }
    inTransitionRef.current = false
    handedOverRef.current = true
    const next = nextExercise
    if (next !== null) {
      if (nextIsTimed) {
        markLockScreenHandoff()
      } else {
        holdLockScreen(nextCard(next.name))
      }
    }
    onSettledRef.current?.()
  }

  function nextCard(nextName: string) {
    return {
      title: nextName,
      subtitle: `Далее · ${exercise.phase === 'warmup' ? 'разминка' : 'заминка'}`,
      artworkUrl:
        renderLockScreenArtwork({
          phase: 'next',
          exerciseName: nextName,
          detail: nextIsTimed ? `через ${TRANSITION_SECONDS} сек` : 'в своём темпе',
          rounds: 0,
          completedRounds: 0,
        }) ?? '/icon-512.png',
    }
  }

  useEffect(() => {
    if (transitionEndsAt === null || nextExercise === null) {
      return
    }
    updateLockScreenInfo(nextCard(nextExercise.name))
    updateLockScreenProgress(
      TRANSITION_SECONDS,
      Math.max(0, (transitionEndsAt - Date.now()) / 1000),
      true,
    )
    const timeoutId = window.setTimeout(
      () => finishTransitionRef.current(),
      Math.max(0, transitionEndsAt - Date.now()),
    )
    return () => window.clearTimeout(timeoutId)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once per transition
  }, [transitionEndsAt])

  // The other half of the hand-over: started by the previous exercise, so
  // this one begins on its own -- no tap needed (the audio element was
  // unlocked by the first tap of the session). Never over a restored
  // round in progress.
  useEffect(() => {
    if (!continuous || restoredActiveRef.current || isDone) {
      takeLockScreenHandoff()
      return
    }
    if (!takeLockScreenHandoff()) {
      return
    }
    startLockScreenIfOn()
    deadlineRef.current = Date.now() + durationSeconds * 1000
    setManualSeconds(null)
    setRemaining(durationSeconds)
    setRunning(true)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- mount only
  }, [])

  function skipRest() {
    setRunning(false)
    advanceRest()
  }

  // showFeedback checked BEFORE isDone -- once the last round's advance()
  // fires onComplete, the parent's own completed_at updates and re-renders
  // this component with isDone now true (found live-testing this exact
  // flow, 2026-08-28: the terminal "Готово" state below was winning the
  // race and hiding the feedback prompt before the athlete ever saw it).
  // showFeedback captures "still mid-flow, waiting on the feedback tap" and
  // must take priority regardless of what isDone becomes in the meantime.
  if (transitionEndsAt !== null && nextExercise !== null) {
    return (
      <div className="flex flex-col items-center gap-3 py-4">
        <div className="flex h-20 w-20 items-center justify-center rounded-full border-2 border-accent-ice bg-accent-ice/15">
          <i className="ti ti-check text-4xl text-accent-ice" aria-hidden="true" />
        </div>
        <span className="text-sm font-medium text-accent-ice">Готово</span>
        <TransitionCountdown endsAt={transitionEndsAt} nextName={nextExercise.name} />
        <button
          type="button"
          onClick={() => finishTransitionRef.current()}
          className="text-xs text-text-secondary underline underline-offset-2 hover:text-text-primary"
        >
          Начать сейчас
        </button>
      </div>
    )
  }

  if (showFeedback && !feedbackAnswered) {
    return (
      <div className="flex flex-col items-center gap-3 py-4">
        <div className="flex h-20 w-20 items-center justify-center rounded-full border-2 border-accent-ice bg-accent-ice/15">
          <i className="ti ti-check text-4xl text-accent-ice" aria-hidden="true" />
        </div>
        <span className="text-sm font-medium text-accent-ice">Готово</span>
        <ExerciseFeedbackPrompt
          exercise={exercise}
          trainingSessionId={trainingSessionId}
          accessToken={accessToken}
          onSubmitted={() => {
            setFeedbackAnswered(true)
            onSettled?.()
          }}
        />
      </div>
    )
  }

  if (isDone || feedbackAnswered) {
    return (
      <div className="flex flex-col items-center gap-3 py-4">
        <div className="flex h-20 w-20 items-center justify-center rounded-full border-2 border-accent-ice bg-accent-ice/15">
          <i className="ti ti-check text-4xl text-accent-ice" aria-hidden="true" />
        </div>
        <span className="text-sm font-medium text-accent-ice">Готово</span>
      </div>
    )
  }

  return (
    <div className="flex flex-col items-center gap-4 py-2">
      {phase === 'work' ? (
        <div className="flex flex-col items-center gap-3">
          <CountdownRing
            totalSeconds={durationSeconds}
            remainingSeconds={remaining}
            label={
              sideLabel(completedRounds + 1) !== null
                ? `${sideLabel(completedRounds + 1)} · ${durationSeconds} сек`
                : `из ${durationSeconds} сек`
            }
            accent="ice"
            interactive
            running={running}
            onToggle={() => {
              if (!running) {
                startLockScreenIfOn()
              }
              setWorkRunning(!running)
            }}
          />
          <LastTimeHint history={history} setNumber={completedRounds + 1} tracksWeight={false} />
          {manualSeconds !== null && (
            <div className="flex flex-col items-center gap-2">
              <span className="text-xs text-text-secondary">Сколько сек. реально сделали</span>
              <div className="flex items-center gap-3">
                <Stepper
                  value={manualSeconds}
                  unit="сек"
                  step={1}
                  min={0}
                  ariaLabel="Секунд выполнено"
                  onChange={setManualSeconds}
                />
                <button
                  type="button"
                  onClick={() => advanceWork(manualSeconds)}
                  aria-label="Подтвердить подход"
                  className="flex h-9 w-9 items-center justify-center rounded-full bg-accent-ice text-dark-bg transition-opacity hover:opacity-90"
                >
                  <i className="ti ti-check text-lg" aria-hidden="true" />
                </button>
              </div>
            </div>
          )}
        </div>
      ) : (
        <div className="flex flex-col items-center gap-2">
          <CountdownRing
            totalSeconds={restSeconds}
            remainingSeconds={remaining}
            label={sideLabel(completedRounds + 1) !== null ? 'Смена стороны' : 'Отдых'}
            accent="persimmon"
          />
          <button
            type="button"
            onClick={skipRest}
            className="text-xs text-text-secondary underline underline-offset-2 hover:text-text-primary"
          >
            Пропустить
          </button>
        </div>
      )}

      {rounds > 1 && (
        <div className="flex items-center gap-2">
          {Array.from({ length: rounds }, (_, index) => index).map((index) => (
            <div
              key={index}
              className={`flex h-6 w-6 items-center justify-center rounded-full border-2 font-display text-xs ${
                index < completedRounds
                  ? 'border-accent-ice bg-accent-ice text-dark-bg'
                  : index === completedRounds
                    ? 'border-accent-persimmon text-accent-persimmon'
                    : 'border-white/15 text-text-secondary'
              }`}
            >
              {index < completedRounds ? <i className="ti ti-check text-xs" aria-hidden="true" /> : index + 1}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// "Дальше: <name> через N" under the hand-over's check mark.
function TransitionCountdown({ endsAt, nextName }: { endsAt: number; nextName: string }) {
  const [left, setLeft] = useState(() => Math.max(0, Math.ceil((endsAt - Date.now()) / 1000)))
  useEffect(() => {
    const interval = setInterval(() => setLeft(Math.max(0, Math.ceil((endsAt - Date.now()) / 1000))), 250)
    return () => clearInterval(interval)
  }, [endsAt])
  return (
    <p className="text-center text-sm text-text-secondary">
      Дальше: <span className="text-text-primary">{nextName}</span>
      {left > 0 ? ` через ${left}` : ''}
    </p>
  )
}
