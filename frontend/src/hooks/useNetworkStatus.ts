import { useSyncExternalStore } from 'react'
import { isOnline, subscribeNetworkStatus } from '../utils/networkStatus'

// True while the app can reach the server (see utils/networkStatus.ts).
export function useOnline(): boolean {
  return useSyncExternalStore(subscribeNetworkStatus, isOnline, () => true)
}
