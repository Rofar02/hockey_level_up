import { apiDeleteAuthWithBody, apiGet, apiPostAuth } from './client'

export interface VapidPublicKeyRead {
  public_key: string
}

// Matches the browser's own PushSubscription.toJSON() shape -- passed
// straight through to the backend with no reshaping.
export interface PushSubscriptionPayload {
  endpoint: string
  keys: {
    p256dh: string
    auth: string
  }
}

export interface PushSubscriptionRead {
  id: string
  endpoint: string
  user_agent: string | null
  created_at: string
}

export interface PushTestResult {
  total_subscriptions: number
  delivered: number
}

export function getVapidPublicKey(accessToken: string): Promise<VapidPublicKeyRead> {
  return apiGet<VapidPublicKeyRead>('/push/vapid-public-key', accessToken)
}

export function savePushSubscription(
  payload: PushSubscriptionPayload,
  accessToken: string,
): Promise<PushSubscriptionRead> {
  return apiPostAuth<PushSubscriptionRead>('/users/me/push-subscription', payload, accessToken)
}

export function deletePushSubscription(endpoint: string, accessToken: string): Promise<void> {
  return apiDeleteAuthWithBody<void>('/users/me/push-subscription', { endpoint }, accessToken)
}

export function sendTestPushNotification(accessToken: string): Promise<PushTestResult> {
  return apiPostAuth<PushTestResult>('/users/me/push-subscription/test', {}, accessToken)
}
