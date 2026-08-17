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

function extractErrorMessage(body: unknown): string {
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
  return 'Request failed'
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let body: unknown = null
    try {
      body = await response.json()
    } catch {
      // response had no JSON body -- fall through with a generic message
    }
    throw new ApiError(response.status, extractErrorMessage(body))
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

  return handleResponse<T>(response)
}

export function apiPost<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, 'POST', { body })
}

export function apiGet<T>(path: string, accessToken: string): Promise<T> {
  return request<T>(path, 'GET', { accessToken })
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
