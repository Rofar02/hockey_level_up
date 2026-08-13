import { apiGet, apiGetPublic, apiPost, apiPostAuth, apiPostForm } from './client'
import type { RegisterPayload, UserRead } from '../types/user'

export interface TokenPair {
  access_token: string
  refresh_token: string
  token_type: string
}

// Shared response shape for every verify-email/password-reset endpoint --
// see app/schemas/auth.py's DetailResponse.
export interface DetailResponse {
  detail: string
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

// Authenticated -- resending only makes sense for whoever's asking.
export function resendVerificationEmail(accessToken: string): Promise<DetailResponse> {
  return apiPostAuth<DetailResponse>('/auth/verify-email/resend', {}, accessToken)
}

// Public -- reached from a link in an email, not necessarily a logged-in browser.
export function confirmEmailVerification(token: string): Promise<DetailResponse> {
  return apiGetPublic<DetailResponse>(`/auth/verify-email/confirm?token=${encodeURIComponent(token)}`)
}

// Public. Always resolves the same way regardless of whether `email` is a
// real account -- see AuthService.request_password_reset. Callers should
// show its `detail` verbatim rather than inferring success/failure from it.
export function requestPasswordReset(email: string): Promise<DetailResponse> {
  return apiPost<DetailResponse>('/auth/password-reset/request', { email })
}

export function confirmPasswordReset(token: string, newPassword: string): Promise<DetailResponse> {
  return apiPost<DetailResponse>('/auth/password-reset/confirm', {
    token,
    new_password: newPassword,
  })
}
