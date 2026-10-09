import { API_BASE_URL } from '../api/client'
import type { UserPublicRead } from '../types/user'
import { cardTeamFrom } from '../hooks/useMyTeam'
import { PlayerCard } from './PlayerCard'
import { cardStyleFor } from './playerCardLook'
import { cardStatsFrom, overallRatingOf } from './playerCardStats'

// Someone else's player card, read-only, from UserPublicRead -- on their
// profile, in the friend search sheet and on the invite-link page. Never
// the age: UserPublicRead doesn't carry it.
export function PublicPlayerCard({ profile }: { profile: UserPublicRead }) {
  const subtitle = [
    profile.first_name,
    profile.years_of_experience != null ? `${profile.years_of_experience} лет стажа` : null,
  ]
    .filter(Boolean)
    .join(' · ')

  return (
    <PlayerCard
      cardStyle={cardStyleFor(profile.level, profile.avatar_ring_accent)}
      premium={profile.has_premium}
      jerseyColor={profile.jersey_color}
      rating={overallRatingOf(profile.stats)}
      position={profile.position}
      jerseyNumber={profile.jersey_number}
      surname={profile.last_name || profile.first_name}
      subtitle={subtitle}
      level={profile.level}
      xp={profile.xp}
      avatarUrl={profile.avatar_url != null ? `${API_BASE_URL}${profile.avatar_url}` : null}
      team={cardTeamFrom(profile.team)}
      stats={cardStatsFrom(profile.stats)}
    />
  )
}
