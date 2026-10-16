// The team's rating, one way everywhere (15.10 follow-up): the team page
// showed «1 234,5», the hub «1 235» and «1 235 XP» -- it isn't XP, and a
// tenth of a point on a number in the thousands says nothing.
export function formatTeamScore(value: number): string {
  return Math.round(value).toLocaleString('ru-RU')
}
