// The token from an email link. New links carry it after "#" -- a fragment
// never reaches the server, so it stays out of access logs (step 8,
// security, 6); links sent before that carry it as ?token=.
export function linkToken(hash: string, search: string): string | null {
  const fromHash = new URLSearchParams(hash.replace(/^#/, '')).get('token')
  return fromHash ?? new URLSearchParams(search).get('token')
}
