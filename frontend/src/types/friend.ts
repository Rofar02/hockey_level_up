import type { Position } from './user'

export const FRIEND_REQUEST_STATUSES = ['pending', 'accepted', 'declined'] as const
export type FriendRequestStatus = (typeof FRIEND_REQUEST_STATUSES)[number]

// GET /friends -- one row per accepted friendship.
export interface FriendRead {
  id: string
  first_name: string
  last_name: string
  avatar_url: string | null
  level: number
  jersey_number: number | null
  position: Position | null
}

export interface FriendCodePayload {
  code: string
}

// Response to POST /friends/requests -- the receiver's info, since the
// sender only typed in a code and doesn't already know who that is.
export interface FriendRequestSentRead {
  id: string
  status: FriendRequestStatus
  receiver_id: string
  receiver_first_name: string
  receiver_last_name: string
  receiver_avatar_url: string | null
}

// GET /friends/requests -- requests sent *to* the caller.
export interface FriendRequestRead {
  id: string
  sender_id: string
  sender_first_name: string
  sender_last_name: string
  sender_avatar_url: string | null
  status: FriendRequestStatus
  created_at: string
}
