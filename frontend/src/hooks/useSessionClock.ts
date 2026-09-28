import { useEffect, useState } from 'react'
import type { SessionBlockRead } from '../types/schedule'

const STORAGE_PREFIX = 'icelevel.sessionStartedAt.'

function readStoredStart(trainingSessionId: string): number | null {
  try {
    const raw = localStorage.getItem(STORAGE_PREFIX + trainingSessionId)
    const parsed = raw === null ? NaN : Number(raw)
    return Number.isFinite(parsed) ? parsed : null
  } catch {
    return null
  }
}

function storeStart(trainingSessionId: string, startedAt: number) {
  try {
    localStorage.setItem(STORAGE_PREFIX + trainingSessionId, String(startedAt))
  } catch {
    // Private mode / blocked storage -- the clock still runs for this
    // visit, it just restarts from the fallback on a reload.
  }
}

function earliestCompletion(blocks: SessionBlockRead[]): number | null {
  const times = blocks
    .flatMap((block) => [block.completed_at, block.skipped_at])
    .filter((value): value is string => value !== null)
    .map((value) => new Date(value).getTime())
  return times.length > 0 ? Math.min(...times) : null
}

// Elapsed workout time for the player header (user request 2026-09-28,
// modelled on a competitor's "0:35" in the exercise header). The backend
// has no session start timestamp, so the start is the moment the athlete
// first opened an exercise in this session on this device -- remembered in
// localStorage so it survives a reload or a switch back to the list. With
// nothing stored (other device, cleared storage) the earliest completed or
// skipped block stands in, and failing that, now. Returns null once
// `running` is false (session finished) -- a clock that keeps counting past
// the end would just be wrong.
export function useSessionClock(
  trainingSessionId: string | null,
  blocks: SessionBlockRead[],
  running: boolean,
): number | null {
  const [startedAt, setStartedAt] = useState<number | null>(null)
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    if (trainingSessionId === null || !running) {
      return
    }
    if (startedAt !== null) {
      return
    }
    const resolved = readStoredStart(trainingSessionId) ?? earliestCompletion(blocks) ?? Date.now()
    storeStart(trainingSessionId, resolved)
    setStartedAt(resolved)
  }, [trainingSessionId, blocks, running, startedAt])

  useEffect(() => {
    if (!running) {
      return
    }
    const interval = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(interval)
  }, [running])

  if (!running || startedAt === null) {
    return null
  }
  return Math.max(0, Math.floor((now - startedAt) / 1000))
}

export function formatElapsed(totalSeconds: number): string {
  const hours = Math.floor(totalSeconds / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  const seconds = totalSeconds % 60
  const mmss = `${String(minutes).padStart(hours > 0 ? 2 : 1, '0')}:${String(seconds).padStart(2, '0')}`
  return hours > 0 ? `${hours}:${mmss}` : mmss
}
