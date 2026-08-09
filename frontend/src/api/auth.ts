import { apiGet, apiPost, apiPostForm } from './client'
import type { RegisterPayload, UserRead } from '../types/user'

export interface TokenPair {
  access_token: string
  refresh_token: string
  token_type: string
}

export function login(identifier: string, password: string): Promise<TokenPair> {
  // POST /auth/login expects OAuth2PasswordRequestForm: form-urlencoded,
  // field is named "username" per the OAuth2 spec, but AuthService.authenticate
  // accepts either a username or an email in it -- new accounts have no
  // client-chosen username (see AuthService._generate_username), so they log
  // in by email; pre-existing accounts can still use their username.
  return apiPostForm<TokenPair>('/auth/login', { username: identifier, password })
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
