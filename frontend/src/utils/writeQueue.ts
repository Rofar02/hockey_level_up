// The offline workout queue (Б2, 2026-10-13). Every workout write -- a set,
// its feedback, an exercise done or skipped, the ice report -- goes in here
// first, even online: one road for all of them. The screen updates at once;
// the queue sends in order, one at a time, each with its own
// Idempotency-Key, so a resend after a lost answer is never applied twice
// (app/core/idempotency.py). Behind the server's `offline_queue` feature
// flag; off, new writes go straight to the API as before -- but whatever is
// already queued is still sent (a flag switched off must not strand it).
//
// Sending: at app start, on "online", on return to the app, after each new
// action. A network error, a 5xx, a 429 (or an expired session) stops the
// run and retries later with a growing pause. A 2xx removes the action. Any
// other 4xx (day rebuilt, exercise gone) removes it too and is kept as a
// "не сохранилось" notice -- never lost silently. Correcting a set is a new
// action with a new key.
//
// One sender at a time: a flag in this tab plus a Web Lock across tabs;
// tabs tell each other about changes over a BroadcastChannel.
import { ApiError, apiSendQueued } from '../api/client'
import { getStoredAccessToken } from '../api/tokenStorage'
import { isNetworkError, isOnline } from './networkStatus'
import { getOfflineUser } from './offlineData'

export interface QueuedAction {
  key: string
  userId: string
  method: 'POST' | 'PUT'
  path: string
  body: Record<string, unknown>
  // What the player did, for the "не сохранилось" notice.
  label: string
  createdAt: number
}

export interface FailedAction {
  key: string
  userId: string
  label: string
  detail: string
  at: number
}

type Outcome = { kind: 'done'; data: unknown } | { kind: 'rejected'; error: ApiError } | { kind: 'queued' }

const DB_NAME = 'icelevel-queue'
const DB_VERSION = 1
const ACTIONS = 'actions'
const FAILED = 'failed'
const FLAG_KEY = 'icelevel.offlineQueue'
const LOCK_NAME = 'icelevel-write-queue'
// Online, a write waits this long for the server's own answer before the
// screen goes ahead on its optimistic copy.
const ONLINE_WAIT_MS = 6000
const RETRY_DELAYS_MS = [3000, 10_000, 30_000, 60_000]
// Older than this, an action isn't sent at all -- the server would not trust
// its time any more (performed_at, -48 h) and the day has long moved on.
export const MAX_ACTION_AGE_MS = 48 * 60 * 60 * 1000

// -- feature flag (remembered: an offline start has to know it too) --

export function isQueueEnabled(): boolean {
  try {
    return localStorage.getItem(FLAG_KEY) === '1'
  } catch {
    return false
  }
}

export function setQueueEnabled(enabled: boolean): void {
  try {
    if (enabled) {
      localStorage.setItem(FLAG_KEY, '1')
    } else {
      localStorage.removeItem(FLAG_KEY)
    }
  } catch {
    // Storage blocked: the queue just stays off.
  }
}

// -- storage --

let dbPromise: Promise<IDBDatabase> | null = null

function openDb(): Promise<IDBDatabase> {
  if (dbPromise === null) {
    dbPromise = new Promise<IDBDatabase>((resolve, reject) => {
      if (typeof indexedDB === 'undefined') {
        reject(new Error('IndexedDB unavailable'))
        return
      }
      const request = indexedDB.open(DB_NAME, DB_VERSION)
      request.onupgradeneeded = () => {
        const db = request.result
        if (!db.objectStoreNames.contains(ACTIONS)) {
          db.createObjectStore(ACTIONS, { keyPath: 'key' }).createIndex('createdAt', 'createdAt')
        }
        if (!db.objectStoreNames.contains(FAILED)) {
          db.createObjectStore(FAILED, { keyPath: 'key' })
        }
      }
      request.onsuccess = () => resolve(request.result)
      request.onerror = () => reject(request.error)
    }).catch((err: unknown) => {
      dbPromise = null
      throw err
    })
  }
  return dbPromise
}

function promisify<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
  })
}

async function readAll<T>(store: string): Promise<T[]> {
  const db = await openDb()
  return (await promisify(db.transaction(store).objectStore(store).getAll())) as T[]
}

async function writeOne(store: string, value: unknown): Promise<void> {
  const db = await openDb()
  await promisify(db.transaction(store, 'readwrite').objectStore(store).put(value))
}

async function deleteOne(store: string, key: string): Promise<void> {
  const db = await openDb()
  await promisify(db.transaction(store, 'readwrite').objectStore(store).delete(key))
}

// -- in-memory mirror (what the UI reads synchronously) --

let actions: QueuedAction[] = []
let failed: FailedAction[] = []
// Actions IndexedDB refused to store (private mode, full disk): they live
// only here, so a reload from storage must not drop them.
const memoryOnly = new Set<string>()
// Bumped on every action this tab adds -- an add that lands while a reload
// is reading storage is kept rather than overwritten by the older read.
let addGeneration = 0
const addedAt = new Map<string, number>()
const listeners = new Set<() => void>()
const channel = typeof BroadcastChannel !== 'undefined' ? new BroadcastChannel(LOCK_NAME) : null
let loaded: Promise<void> | null = null

function emit() {
  pendingSnapshot = null
  for (const listener of listeners) {
    listener()
  }
}

async function reload(): Promise<void> {
  const readStartedAt = addGeneration
  try {
    const [nextActions, nextFailed] = await Promise.all([readAll<QueuedAction>(ACTIONS), readAll<FailedAction>(FAILED)])
    const stored = new Set(nextActions.map((item) => item.key))
    const keep = actions.filter(
      (item) => !stored.has(item.key) && (memoryOnly.has(item.key) || (addedAt.get(item.key) ?? 0) > readStartedAt),
    )
    actions = [...nextActions, ...keep].sort((a, b) => a.createdAt - b.createdAt)
    failed = nextFailed.sort((a, b) => a.at - b.at)
  } catch {
    // Storage unavailable: the queue is whatever this tab holds in memory.
  }
  emit()
}

export function whenQueueLoaded(): Promise<void> {
  if (loaded === null) {
    loaded = reload()
  }
  return loaded
}

function changed() {
  emit()
  channel?.postMessage('changed')
}

channel?.addEventListener('message', () => void reload())

export function subscribeQueue(listener: () => void): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

function mine<T extends { userId: string }>(items: T[]): T[] {
  const userId = getOfflineUser()
  return userId === null ? [] : items.filter((item) => item.userId === userId)
}

let pendingSnapshot: QueuedAction[] | null = null

export function pendingActions(): QueuedAction[] {
  if (pendingSnapshot === null) {
    pendingSnapshot = mine(actions)
  }
  return pendingSnapshot
}

export function pendingCount(): number {
  return pendingActions().length
}

export function failedActions(): FailedAction[] {
  return mine(failed)
}

export async function dismissFailed(): Promise<void> {
  const mineNow = failedActions()
  failed = failed.filter((item) => !mineNow.includes(item))
  changed()
  for (const item of mineNow) {
    await deleteOne(FAILED, item.key).catch(() => undefined)
  }
}

// -- what's queued, for screens rebuilt from saved data --

// The time an exercise was marked done/skipped while its write is still
// queued -- so a workout reopened offline shows it done.
export function pendingBlockResolution(blockId: string): { completed_at?: string; skipped_at?: string } | null {
  for (const action of pendingActions()) {
    if (action.path === `/session-blocks/${blockId}/complete`) {
      return { completed_at: String(action.body.performed_at) }
    }
    if (action.path === `/session-blocks/${blockId}/skip`) {
      return { skipped_at: String(action.body.performed_at) }
    }
  }
  return null
}

// Sets logged for an exercise and still queued, last write per set wins.
export function pendingSets(trainingSessionId: string, exerciseId: string): Record<string, unknown>[] {
  const bySet = new Map<number, Record<string, unknown>>()
  for (const action of pendingActions()) {
    if (
      action.path === '/set-completions' &&
      action.body.training_session_id === trainingSessionId &&
      action.body.exercise_id === exerciseId
    ) {
      bySet.set(Number(action.body.set_number), action.body)
    }
  }
  return [...bySet.values()]
}

// -- enqueue --

const waiters = new Map<string, (outcome: Outcome) => void>()

function newKey(): string {
  const cryptoApi: Crypto = globalThis.crypto
  if (typeof cryptoApi.randomUUID === 'function') {
    return cryptoApi.randomUUID()
  }
  // Old WebViews (randomUUID needs iOS 15.4+): RFC 4122 v4 by hand.
  const bytes = cryptoApi.getRandomValues(new Uint8Array(16))
  bytes[6] = (bytes[6] & 0x0f) | 0x40
  bytes[8] = (bytes[8] & 0x3f) | 0x80
  const hex = [...bytes].map((b) => b.toString(16).padStart(2, '0')).join('')
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
}

export interface QueuedWrite<T> {
  method: 'POST' | 'PUT'
  path: string
  body: Record<string, unknown>
  label: string
  // What the screen shows until (or instead of) the server's answer.
  optimistic: (performedAt: string) => T
}

// Puts a write in the queue and answers with the server's response when it
// comes quickly, or with the optimistic copy when it doesn't (offline, slow
// network). A 4xx while the player waits throws the usual ApiError, so the
// screens keep their own error handling.
export async function enqueueWrite<T>(write: QueuedWrite<T>): Promise<T> {
  await whenQueueLoaded()
  const userId = getOfflineUser()
  const performedAt = new Date().toISOString()
  const action: QueuedAction = {
    key: newKey(),
    userId: userId ?? '',
    method: write.method,
    path: write.path,
    body: { ...write.body, performed_at: performedAt },
    label: write.label,
    createdAt: Date.now(),
  }
  addGeneration += 1
  addedAt.set(action.key, addGeneration)
  actions = [...actions, action]
  changed()
  try {
    await writeOne(ACTIONS, action)
  } catch {
    // Not persisted (private mode): still sent from memory while the app runs.
    memoryOnly.add(action.key)
  }

  const outcome = new Promise<Outcome>((resolve) => {
    waiters.set(action.key, resolve)
    setTimeout(() => resolve({ kind: 'queued' }), isOnline() ? ONLINE_WAIT_MS : 0)
  })
  void flushQueue()
  const result = await outcome
  waiters.delete(action.key)
  if (result.kind === 'done') {
    return result.data as T
  }
  if (result.kind === 'rejected') {
    throw result.error
  }
  return write.optimistic(performedAt)
}

// -- sending --

let flushing = false
let retryTimer: ReturnType<typeof setTimeout> | null = null
let retryStep = 0

function scheduleRetry() {
  if (retryTimer !== null) {
    return
  }
  const delay = RETRY_DELAYS_MS[Math.min(retryStep, RETRY_DELAYS_MS.length - 1)]
  retryStep += 1
  retryTimer = setTimeout(() => {
    retryTimer = null
    void flushQueue()
  }, delay)
}

function isRetryable(err: unknown): boolean {
  return (
    isNetworkError(err) ||
    !(err instanceof ApiError) ||
    err.status >= 500 ||
    err.status === 429 ||
    err.status === 401 ||
    err.status === 408
  )
}

async function removeAction(key: string) {
  actions = actions.filter((item) => item.key !== key)
  memoryOnly.delete(key)
  addedAt.delete(key)
  changed()
  await deleteOne(ACTIONS, key).catch(() => undefined)
}

async function keepAsFailed(action: QueuedAction, detail: string) {
  await removeAction(action.key)
  const notice: FailedAction = { key: action.key, userId: action.userId, label: action.label, detail, at: Date.now() }
  failed = [...failed, notice]
  changed()
  await writeOne(FAILED, notice).catch(() => undefined)
}

async function drain(): Promise<void> {
  for (;;) {
    // Re-read from storage each time: another tab may have queued or sent.
    await reload()
    const userId = getOfflineUser()
    const accessToken = getStoredAccessToken()
    const next = actions.find((item) => item.userId === userId)
    if (next === undefined || userId === null || accessToken === null) {
      return
    }
    if (Date.now() - next.createdAt > MAX_ACTION_AGE_MS) {
      await keepAsFailed(next, 'Пролежало без связи больше двух суток — не отправлено')
      continue
    }
    try {
      const data = await apiSendQueued<unknown>(next.method, next.path, next.body, accessToken, next.key)
      await removeAction(next.key)
      retryStep = 0
      waiters.get(next.key)?.({ kind: 'done', data })
    } catch (err) {
      if (isRetryable(err)) {
        // Everyone waiting goes ahead on the optimistic copy.
        for (const action of actions) {
          waiters.get(action.key)?.({ kind: 'queued' })
        }
        scheduleRetry()
        return
      }
      const error = err as ApiError
      const waiter = waiters.get(next.key)
      if (waiter !== undefined) {
        await removeAction(next.key)
        waiter({ kind: 'rejected', error })
      } else {
        await keepAsFailed(next, error.message)
      }
    }
  }
}

// Asked to send while a run is going: that run may have already looked for
// the next action -- go round once more when it ends.
let dirty = false

// Sends whatever is queued, flag or not: the flag only decides whether new
// writes are queued (see the api wrappers).
export async function flushQueue(): Promise<void> {
  if (flushing) {
    dirty = true
    return
  }
  flushing = true
  try {
    await whenQueueLoaded()
    do {
      dirty = false
      const locks = typeof navigator !== 'undefined' ? navigator.locks : undefined
      if (locks?.request) {
        await locks.request(LOCK_NAME, { ifAvailable: true }, async (lock) => {
          if (lock !== null) {
            await drain()
          }
        })
      } else {
        await drain()
      }
    } while (dirty && retryTimer === null)
  } finally {
    flushing = false
  }
}

// -- signing out --

// Tries to send this player's queue right now; true when nothing is left.
export async function sendQueueNow(): Promise<boolean> {
  retryStep = 0
  if (retryTimer !== null) {
    clearTimeout(retryTimer)
    retryTimer = null
  }
  await flushQueue()
  return pendingCount() === 0
}

// Signing out on purpose: this player's unsent actions and notices go -- the
// next person on this phone must never send them under their own account.
export async function discardQueue(userId: string): Promise<void> {
  await whenQueueLoaded()
  const dropActions = actions.filter((item) => item.userId === userId)
  const dropFailed = failed.filter((item) => item.userId === userId)
  actions = actions.filter((item) => item.userId !== userId)
  failed = failed.filter((item) => item.userId !== userId)
  changed()
  for (const item of dropActions) {
    memoryOnly.delete(item.key)
    await deleteOne(ACTIONS, item.key).catch(() => undefined)
  }
  for (const item of dropFailed) {
    await deleteOne(FAILED, item.key).catch(() => undefined)
  }
}

// Start, "online", return to the app.
export function installWriteQueue(): void {
  void whenQueueLoaded().then(() => flushQueue())
  window.addEventListener('online', () => {
    retryStep = 0
    void flushQueue()
  })
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') {
      void flushQueue()
    }
  })
}
