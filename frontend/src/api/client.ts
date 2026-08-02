const API_BASE_URL = import.meta.env.VITE_API_BASE_URL

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
  accessToken?: string
}

async function request<T>(path: string, method: string, options: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = {}
  let requestBody: BodyInit | undefined

  if (options.form !== undefined) {
    headers['Content-Type'] = 'application/x-www-form-urlencoded'
    requestBody = new URLSearchParams(options.form)
  } else if (options.body !== undefined) {
    headers['Content-Type'] = 'application/json'
    requestBody = JSON.stringify(options.body)
  }

  if (options.accessToken !== undefined) {
    headers.Authorization = `Bearer ${options.accessToken}`
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers,
    body: requestBody,
  })
  return handleResponse<T>(response)
}

export function apiPost<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, 'POST', { body })
}

export function apiGet<T>(path: string, accessToken: string): Promise<T> {
  return request<T>(path, 'GET', { accessToken })
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
