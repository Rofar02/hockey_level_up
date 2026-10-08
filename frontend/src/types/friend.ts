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

// By the friend's code (typed in or from their invite link) or, from the
// search/teammate/suggestion lists, by their id -- one of the two.
export type FriendCodePayload = { code: string } | { user_id: string }

export type FriendRelation = 'none' | 'outgoing' | 'incoming' | 'friend'

// GET /friends/search, /friends/teammates, /friends/suggestions (2026-10-08):
// what anyone may see about a player before being friends -- no age.
export interface PlayerSuggestionRead {
  id: string
  first_name: string
  last_name: string
  avatar_url: string | null
  level: number
  jersey_number: number | null
  position: Position | null
  team_name: string | null
  mutual_friends: number
  relation: FriendRelation
  // Search only: "similar" for a spelling-tolerant hit (Питров -> Петров).
  match: 'exact' | 'similar'
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
