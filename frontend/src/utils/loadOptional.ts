import { ApiError } from '../api/client'

// 404 is the expected shape of "not declared yet" for some resources, not a
// real failure -- surfaces it as `null` so callers can render an empty
// state instead of an error banner.
export async function loadOptional<T>(promise: Promise<T>): Promise<T | null> {
  try {
    return await promise
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) {
      return null
    }
    throw err
  }
}
