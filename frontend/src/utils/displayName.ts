// Registration no longer collects a username, so it's never shown as a name
// anymore -- first_name/last_name are the required registration fields and
// take over everywhere username used to be displayed (Home, Profile,
// Leaderboard). `username` is optional here since LeaderboardEntryRead
// doesn't carry one at all (see app/schemas/leaderboard.py) -- callers that
// have it (UserRead) pass it as a fallback for legacy rows from before
// first_name/last_name existed (the DB server_default is ""); callers that
// don't get a generic placeholder instead.
export function getDisplayName(
  user: {
    last_name: string
    first_name: string
    patronymic?: string | null
    username?: string
  },
  // LeaderboardPage passes { patronymic: false } -- a ranked list is
  // already tight on width per row, and "Фамилия Имя" reads fine there
  // without it. Every other caller wants the full legal name, so this
  // defaults to on.
  options?: { patronymic?: boolean },
): string {
  if (user.last_name === '' || user.first_name === '') {
    return user.username ?? 'Без имени'
  }
  const includePatronymic = options?.patronymic ?? true
  return [user.last_name, user.first_name, includePatronymic ? user.patronymic : null]
    .filter(Boolean)
    .join(' ')
}
