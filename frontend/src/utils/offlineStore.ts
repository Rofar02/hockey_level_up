// Saved API answers for offline use (Б1, 2026-10-13): the last good answer
// to each whitelisted GET, per player, in IndexedDB -- what the app shows
// when it starts with no connection, or when the network hangs. Memory
// (client.ts's getCache) stays the fast path; this is the fallback.
//
// One object store, key = "<userId> <path>". Bounded: at most MAX_ENTRIES
// (oldest go first), and weeks/days older than last week are dropped.
// Everything goes on sign-out.

const DB_NAME = 'icelevel-offline'
const DB_VERSION = 1
const STORE = 'responses'
const MAX_ENTRIES = 300
const PRUNE_EVERY_PUTS = 20

export interface SavedResponse {
  key: string
  userId: string
  path: string
  data: unknown
  storedAt: number
}

let dbPromise: Promise<IDBDatabase> | null = null
let putsSincePrune = 0

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
        if (!db.objectStoreNames.contains(STORE)) {
          const store = db.createObjectStore(STORE, { keyPath: 'key' })
          store.createIndex('storedAt', 'storedAt')
          store.createIndex('userId', 'userId')
        }
      }
      request.onsuccess = () => resolve(request.result)
      request.onerror = () => reject(request.error)
      request.onblocked = () => reject(new Error('IndexedDB blocked'))
    }).catch((err: unknown) => {
      // Private mode / blocked storage: offline data is simply unavailable,
      // and the next call may try again.
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

function done(tx: IDBTransaction): Promise<void> {
  return new Promise((resolve, reject) => {
    tx.oncomplete = () => resolve()
    tx.onerror = () => reject(tx.error)
    tx.onabort = () => reject(tx.error)
  })
}

export function savedKey(userId: string, path: string): string {
  return `${userId} ${path}`
}

export async function readSaved(userId: string, path: string): Promise<SavedResponse | null> {
  try {
    const db = await openDb()
    const entry = await promisify(db.transaction(STORE).objectStore(STORE).get(savedKey(userId, path)))
    return (entry as SavedResponse | undefined) ?? null
  } catch {
    return null
  }
}

export async function writeSaved(userId: string, path: string, data: unknown): Promise<void> {
  try {
    const db = await openDb()
    const tx = db.transaction(STORE, 'readwrite')
    const entry: SavedResponse = { key: savedKey(userId, path), userId, path, data, storedAt: Date.now() }
    tx.objectStore(STORE).put(entry)
    await done(tx)
    putsSincePrune += 1
    if (putsSincePrune >= PRUNE_EVERY_PUTS) {
      putsSincePrune = 0
      await pruneSaved()
    }
  } catch {
    // Full or blocked storage -- only the offline copy loses out.
  }
}

export async function clearSaved(): Promise<void> {
  try {
    const db = await openDb()
    const tx = db.transaction(STORE, 'readwrite')
    tx.objectStore(STORE).clear()
    await done(tx)
  } catch {
    // Nothing saved, or storage gone -- either way nothing is left to show.
  }
}

// The date a week/day answer is about, from its path -- null for anything
// that isn't tied to one.
export function pathDate(path: string): string | null {
  const match = /[?&](?:date|week_start_date)=(\d{4}-\d{2}-\d{2})/.exec(path)
  return match ? match[1] : null
}

function mondayOfLastWeek(now: Date): string {
  const day = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const weekday = (day.getDay() + 6) % 7
  day.setDate(day.getDate() - weekday - 7)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${day.getFullYear()}-${pad(day.getMonth() + 1)}-${pad(day.getDate())}`
}

// Which saved entries to drop: weeks/days before last week, then the oldest
// beyond MAX_ENTRIES. Pure, so it's testable on its own.
export function entriesToPrune(entries: Pick<SavedResponse, 'key' | 'path' | 'storedAt'>[], now: Date): string[] {
  const cutoff = mondayOfLastWeek(now)
  const drop = new Set<string>()
  for (const entry of entries) {
    const date = pathDate(entry.path)
    if (date !== null && date < cutoff) {
      drop.add(entry.key)
    }
  }
  const kept = entries.filter((entry) => !drop.has(entry.key)).sort((a, b) => b.storedAt - a.storedAt)
  for (const entry of kept.slice(MAX_ENTRIES)) {
    drop.add(entry.key)
  }
  return [...drop]
}

export async function pruneSaved(now: Date = new Date()): Promise<void> {
  try {
    const db = await openDb()
    const all = (await promisify(db.transaction(STORE).objectStore(STORE).getAll())) as SavedResponse[]
    const drop = entriesToPrune(all, now)
    if (drop.length === 0) {
      return
    }
    const tx = db.transaction(STORE, 'readwrite')
    const store = tx.objectStore(STORE)
    for (const key of drop) {
      store.delete(key)
    }
    await done(tx)
  } catch {
    // Best-effort housekeeping.
  }
}
