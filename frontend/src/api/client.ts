import {
  clearStoredTokens,
  getStoredRefreshToken,
  persistTokens,
  SESSION_EXPIRED_EVENT,
  TOKENS_REFRESHED_EVENT,
} from './tokenStorage'

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL

interface FastApiValidationError {
  loc: (string | number)[]
  msg: string
  type: string
}

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

// 2026-09-19: fallback wording when the backend itself never got a chance
// to say what went wrong -- an nginx/gateway error page (502/503/504,
// server crashed or mid-deploy, no FastAPI JSON `detail` at all) or any
// other non-JSON response. Every call site trusts ApiError.message as
// something worth showing the player as-is (`err.message` straight into a
// FormError), so this has to already be the real, Russian, human sentence
// -- not a placeholder like the old "Request failed" that leaked English
// straight into the UI the one time it actually fired (a real prod outage).
function fallbackErrorMessage(status: number): string {
  if (status === 502 || status === 503 || status === 504) {
    return 'Сервер временно недоступен. Попробуйте ещё раз через минуту.'
  }
  if (status >= 500) {
    return 'Что-то пошло не так на сервере. Попробуйте ещё раз.'
  }
  return 'Не удалось выполнить запрос. Попробуйте ещё раз.'
}

function extractErrorMessage(body: unknown, status: number): string {
  if (typeof body === 'object' && body !== null && 'detail' in body) {
    const detail = (body as { detail: unknown }).detail
    if (typeof detail === 'string') {
      return detail
    }
    if (Array.isArray(detail)) {
      return (detail as FastApiValidationError[])
        .map((error) => error.msg)
        .join('; ')
    }
  }
  return fallbackErrorMessage(status)
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let body: unknown = null
    try {
      body = await response.json()
    } catch {
      // response had no JSON body -- fall through with a generic message
    }
    throw new ApiError(response.status, extractErrorMessage(body, response.status))
  }
  if (response.status === 204) {
    return undefined as T
  }
  return (await response.json()) as T
}

interface RequestOptions {
  body?: unknown
  form?: Record<string, string>
  formData?: FormData
  accessToken?: string
}

interface RawTokenPair {
  access_token: string
  refresh_token: string
}

// Access tokens live 15 minutes (app/core/config.py); refresh tokens live
// much longer. Without this, a SPA left open past 15 minutes starts failing
// every request with 401 even though a valid refresh_token is sitting in
// localStorage -- the user just sees "everything is broken" until a hard
// reload. De-duped so concurrent 401s from several in-flight requests only
// trigger one /auth/refresh call.
let refreshInFlight: Promise<string> | null = null

async function refreshAccessToken(): Promise<string> {
  if (refreshInFlight === null) {
    refreshInFlight = (async () => {
      const storedRefreshToken = getStoredRefreshToken()
      if (storedRefreshToken === null) {
        throw new ApiError(401, 'No refresh token')
      }
      const response = await fetch(`${API_BASE_URL}/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: storedRefreshToken }),
      })
      const tokens = await handleResponse<RawTokenPair>(response)
      persistTokens(tokens.access_token, tokens.refresh_token)
      window.dispatchEvent(
        new CustomEvent(TOKENS_REFRESHED_EVENT, {
          detail: { accessToken: tokens.access_token, refreshToken: tokens.refresh_token },
        }),
      )
      return tokens.access_token
    })().finally(() => {
      refreshInFlight = null
    })
  }

  try {
    return await refreshInFlight
  } catch (err) {
    clearStoredTokens()
    window.dispatchEvent(new CustomEvent(SESSION_EXPIRED_EVENT))
    throw err
  }
}

function buildRequestInit(method: string, options: RequestOptions, accessToken: string | undefined): RequestInit {
  const headers: Record<string, string> = {}
  let requestBody: BodyInit | undefined

  if (options.form !== undefined) {
    headers['Content-Type'] = 'application/x-www-form-urlencoded'
    requestBody = new URLSearchParams(options.form)
  } else if (options.formData !== undefined) {
    // No Content-Type here -- the browser sets multipart/form-data with the
    // correct boundary itself, and overriding it manually breaks parsing.
    requestBody = options.formData
  } else if (options.body !== undefined) {
    headers['Content-Type'] = 'application/json'
    requestBody = JSON.stringify(options.body)
  }

  if (accessToken !== undefined) {
    headers.Authorization = `Bearer ${accessToken}`
  }

  return { method, headers, body: requestBody }
}

// -- GET cache (2026-10-04): "открываю вкладку ещё раз -- всё уже на месте" --
// A repeat GET is answered at once from memory and refreshed in the
// background for the next visit. Any successful mutation clears the whole
// cache (the player changed something -- nothing stale should show after
// that), and so does logging in or out. Live/polling and admin endpoints
// are never cached. Memory only: a fresh app start always asks the server.
const CACHE_MAX_AGE_MS = 15 * 60 * 1000
// Within this window a cached answer is served without a background refresh
// (several components asking for the same thing on one screen).
const CACHE_FRESH_MS = 5 * 1000
const UNCACHED_PREFIXES = ['/auth/', '/admin/', '/training-parties']

interface CacheEntry {
  data: unknown
  storedAt: number
}

const getCache = new Map<string, CacheEntry>()
const inFlight = new Map<string, Promise<unknown>>()
// Bumped on every clear: a response that left before a mutation must not
// land in the cache after it.
let cacheGeneration = 0

function isCacheable(path: string): boolean {
  return !UNCACHED_PREFIXES.some((prefix) => path.startsWith(prefix))
}

export function clearApiCache(): void {
  cacheGeneration += 1
  getCache.clear()
  inFlight.clear()
}

function fetchAndStore<T>(path: string, accessToken: string): Promise<T> {
  const pending = inFlight.get(path)
  if (pending !== undefined) {
    return pending as Promise<T>
  }
  const generation = cacheGeneration
  const promise = request<T>(path, 'GET', { accessToken })
    .then((data) => {
      if (generation === cacheGeneration) {
        getCache.set(path, { data, storedAt: Date.now() })
      }
      return data
    })
    .finally(() => {
      if (inFlight.get(path) === promise) {
        inFlight.delete(path)
      }
    })
  inFlight.set(path, promise)
  return promise
}

async function cachedGet<T>(path: string, accessToken: string): Promise<T> {
  if (!isCacheable(path)) {
    return request<T>(path, 'GET', { accessToken })
  }
  const entry = getCache.get(path)
  const age = entry !== undefined ? Date.now() - entry.storedAt : Infinity
  if (entry !== undefined && age < CACHE_MAX_AGE_MS) {
    if (age > CACHE_FRESH_MS) {
      void fetchAndStore<T>(path, accessToken).catch(() => undefined)
    }
    return entry.data as T
  }
  return fetchAndStore<T>(path, accessToken)
}

// Warms the cache for screens the player hasn't opened yet (used after login
// next to the page-code prefetch). Failures are ignored.
export function warmApiCache(paths: string[], accessToken: string): void {
  for (const path of paths) {
    if (!getCache.has(path)) {
      void fetchAndStore(path, accessToken).catch(() => undefined)
    }
  }
}

async function request<T>(path: string, method: string, options: RequestOptions = {}): Promise<T> {
  const isAuthedRequest = options.accessToken !== undefined

  let response = await fetch(`${API_BASE_URL}${path}`, buildRequestInit(method, options, options.accessToken))

  if (response.status === 401 && isAuthedRequest) {
    try {
      const freshAccessToken = await refreshAccessToken()
      response = await fetch(`${API_BASE_URL}${path}`, buildRequestInit(method, options, freshAccessToken))
    } catch {
      // Refresh failed (or there was no refresh token left) -- fall through
      // and let the original 401 response produce the usual ApiError below.
      // SESSION_EXPIRED_EVENT has already been dispatched by refreshAccessToken.
    }
  }

  const result = await handleResponse<T>(response)
  if (method !== 'GET') {
    clearApiCache()
  }
  return result
}

export function apiPost<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, 'POST', { body })
}

export function apiGet<T>(path: string, accessToken: string): Promise<T> {
  return cachedGet<T>(path, accessToken)
}

// Unauthenticated GET -- only for endpoints that don't need a logged-in
// session at all (e.g. GET /auth/verify-email/confirm, reached from an
// emailed link that may be opened in a browser with no session).
export function apiGetPublic<T>(path: string): Promise<T> {
  return request<T>(path, 'GET', {})
}

export function apiPostForm<T>(path: string, form: Record<string, string>): Promise<T> {
  return request<T>(path, 'POST', { form })
}

// -- authenticated JSON mutations, used from the onboarding flow onward --

export function apiPostAuth<T>(path: string, body: unknown, accessToken: string): Promise<T> {
  return request<T>(path, 'POST', { body, accessToken })
}

export function apiPatchAuth<T>(path: string, body: unknown, accessToken: string): Promise<T> {
  return request<T>(path, 'PATCH', { body, accessToken })
}

export function apiPutAuth<T>(path: string, body: unknown, accessToken: string): Promise<T> {
  return request<T>(path, 'PUT', { body, accessToken })
}

export function apiDeleteAuth<T>(path: string, accessToken: string): Promise<T> {
  return request<T>(path, 'DELETE', { accessToken })
}

export function apiDeleteAuthWithBody<T>(path: string, body: unknown, accessToken: string): Promise<T> {
  return request<T>(path, 'DELETE', { body, accessToken })
}

export function apiPostMultipartAuth<T>(
  path: string,
  formData: FormData,
  accessToken: string,
): Promise<T> {
  return request<T>(path, 'POST', { formData, accessToken })
}
