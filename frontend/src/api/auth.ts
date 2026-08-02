import { apiGet, apiPost, apiPostForm } from './client'
import type { RegisterPayload, UserRead } from '../types/user'

export interface TokenPair {
  access_token: string
  refresh_token: string
  token_type: string
}

export function login(username: string, password: string): Promise<TokenPair> {
  // POST /auth/login expects OAuth2PasswordRequestForm: form-urlencoded,
  // field is named "username" even though it authenticates against the
  // user's username (the backend has no login-by-email path yet).
  return apiPostForm<TokenPair>('/auth/login', { username, password })
}

export function register(payload: RegisterPayload): Promise<UserRead> {
  return apiPost<UserRead>('/auth/register', payload)
}

export function getCurrentUser(accessToken: string): Promise<UserRead> {
  return apiGet<UserRead>('/auth/me', accessToken)
}

export function refresh(refreshToken: string): Promise<TokenPair> {
  return apiPost<TokenPair>('/auth/refresh', { refresh_token: refreshToken })
}
