// Shared by the friend search, the team invite sheet and the player sheet
// (2026-10-08).

// The server's rule (FriendDiscoveryService.search): two letters to start;
// one word searches the people around me, a first and a last name -- all.
export function isSearchable(query: string): boolean {
  return query.trim().split(/\s+/)[0].length >= 2
}

export function isFullName(query: string): boolean {
  const words = query.trim().split(/\s+/)
  return words.length >= 2 && words.slice(0, 2).every((word) => word.length >= 2)
}

export function inviteLink(code: string): string {
  return `${window.location.origin}/f/${code}`
}

export function teamInviteLink(code: string): string {
  return `${window.location.origin}/t/${code}`
}

export function mutualLine(count: number): string | null {
  if (count === 0) {
    return null
  }
  const mod10 = count % 10
  const mod100 = count % 100
  const word =
    mod10 === 1 && mod100 !== 11
      ? 'общий друг'
      : mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)
        ? 'общих друга'
        : 'общих друзей'
  return `${count} ${word}`
}
