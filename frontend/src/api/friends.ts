import { apiDeleteAuth, apiGet, apiPostAuth } from './client'
import type {
  FriendCodePayload,
  FriendRead,
  FriendRequestRead,
  FriendRequestSentRead,
} from '../types/friend'
import type { ActivityFeedEntryRead } from '../types/friendActivity'
import type { LeaderboardEntryRead } from '../types/leaderboard'

export function listFriends(accessToken: string): Promise<FriendRead[]> {
  return apiGet<FriendRead[]>('/friends', accessToken)
}

export function getFriendLeaderboard(accessToken: string): Promise<LeaderboardEntryRead[]> {
  return apiGet<LeaderboardEntryRead[]>('/friends/leaderboard', accessToken)
}

const ACTIVITY_FEED_PAGE_SIZE = 50

export function getFriendActivityFeed(accessToken: string): Promise<ActivityFeedEntryRead[]> {
  return apiGet<ActivityFeedEntryRead[]>(
    `/friends/feed?limit=${ACTIVITY_FEED_PAGE_SIZE}`,
    accessToken,
  )
}

export function listIncomingFriendRequests(accessToken: string): Promise<FriendRequestRead[]> {
  return apiGet<FriendRequestRead[]>('/friends/requests', accessToken)
}

export function sendFriendRequest(
  payload: FriendCodePayload,
  accessToken: string,
): Promise<FriendRequestSentRead> {
  return apiPostAuth<FriendRequestSentRead>('/friends/requests', payload, accessToken)
}

export function acceptFriendRequest(
  requestId: string,
  accessToken: string,
): Promise<FriendRequestRead> {
  return apiPostAuth<FriendRequestRead>(`/friends/requests/${requestId}/accept`, {}, accessToken)
}

export function declineFriendRequest(
  requestId: string,
  accessToken: string,
): Promise<FriendRequestRead> {
  return apiPostAuth<FriendRequestRead>(`/friends/requests/${requestId}/decline`, {}, accessToken)
}

export function removeFriend(friendId: string, accessToken: string): Promise<void> {
  return apiDeleteAuth<void>(`/friends/${friendId}`, accessToken)
}
