// Registration no longer collects a username, so it's never shown as a name
// anymore -- first_name/last_name are the required registration fields and
// take over everywhere username used to be displayed (Home, Profile,
// Leaderboard). `username` is optional here since LeaderboardEntryRead
// doesn't carry one at all (see app/schemas/leaderboard.py) -- callers that
// have it (UserRead) pass it as a fallback for legacy rows from before
// first_name/last_name existed (the DB server_default is ""); callers that
// don't get a generic placeholder instead.
export function getDisplayName(user: {
  last_name: string
  first_name: string
  patronymic?: string | null
  username?: string
}): string {
  if (user.last_name === '' || user.first_name === '') {
    return user.username ?? 'Без имени'
  }
  return [user.last_name, user.first_name, user.patronymic].filter(Boolean).join(' ')
}
