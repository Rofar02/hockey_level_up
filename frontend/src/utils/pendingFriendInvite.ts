// An invite link opened before logging in (2026-10-08): its code waits here
// until the player has an account, then the request goes out by itself
// (PendingFriendInvite). Best-effort storage -- a private window just loses
// it, and the player can still use the link again.
const KEY = 'icelevel.pendingFriendCode'

export function savePendingFriendCode(code: string): void {
  try {
    localStorage.setItem(KEY, code)
  } catch {
    // Storage blocked -- nothing to do.
  }
}

export function takePendingFriendCode(): string | null {
  try {
    const code = localStorage.getItem(KEY)
    localStorage.removeItem(KEY)
    return code
  } catch {
    return null
  }
}

// The same for a team's invite link: the join request goes out once the
// player has an account.
const TEAM_KEY = 'icelevel.pendingTeamCode'

export function savePendingTeamCode(code: string): void {
  try {
    localStorage.setItem(TEAM_KEY, code)
  } catch {
    // Storage blocked -- nothing to do.
  }
}

export function takePendingTeamCode(): string | null {
  try {
    const code = localStorage.getItem(TEAM_KEY)
    localStorage.removeItem(TEAM_KEY)
    return code
  } catch {
    return null
  }
}

// The server's English 409s for joining a team, in Russian.
export function teamJoinErrorText(message: string): string {
  if (message === 'Already a member of a team -- leave it first') {
    return 'Ты уже в команде — сначала выйди из неё'
  }
  if (message === 'Already a member of this team') {
    return 'Ты уже в этой команде'
  }
  if (message === 'A join request for this team is already pending') {
    return 'Заявка в эту команду уже отправлена'
  }
  if (message === 'Invalid invite code') {
    return 'Приглашение не найдено'
  }
  return message
}

// The server's English 409s for the cases a link can hit, in Russian.
export function friendRequestErrorText(message: string): string {
  if (message === 'Already friends') {
    return 'Вы уже друзья'
  }
  if (message === 'Friend request already sent') {
    return 'Заявка уже отправлена'
  }
  if (message === "Can't send a friend request to yourself") {
    return 'Это твоя собственная ссылка'
  }
  if (message === 'Invalid friend code') {
    return 'Приглашение не найдено'
  }
  return message
}
