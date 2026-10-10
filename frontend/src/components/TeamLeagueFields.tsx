import { useEffect, useState } from 'react'
import * as teamsApi from '../api/teams'
import { useAuth } from '../hooks/useAuth'
import type { LeagueRead, TeamLeagueFields as TeamLeagueValues } from '../types/team'
import { SelectField } from './ui/SelectField'
import { TextField } from './ui/TextField'

export const EMPTY_TEAM_LEAGUE: TeamLeagueValues = {
  city: null,
  league_code: 'none',
  division_code: null,
  league_other_name: null,
}

// "Другая лига" is the only one that needs its own name.
export function isTeamLeagueComplete(value: TeamLeagueValues): boolean {
  return value.league_code !== 'other' || (value.league_other_name ?? '').trim() !== ''
}

interface TeamLeagueFieldsProps {
  value: TeamLeagueValues
  onChange: (value: TeamLeagueValues) => void
}

/** City, league and division -- shared by the create form and the
 * captain's team settings. The division appears only for a league that
 * has divisions (Ночная лига), the name field only for "Другая лига". */
export function TeamLeagueFields({ value, onChange }: TeamLeagueFieldsProps) {
  const { accessToken } = useAuth()
  const [leagues, setLeagues] = useState<LeagueRead[] | null>(null)

  useEffect(() => {
    if (accessToken === null) {
      return
    }
    let cancelled = false
    teamsApi
      .listLeagues(accessToken)
      .then((result) => {
        if (!cancelled) {
          setLeagues(result)
        }
      })
      .catch(() => {
        // Without the list the team simply stays "без лиги" -- the form
        // still works for the name and the city.
      })
    return () => {
      cancelled = true
    }
  }, [accessToken])

  const league = leagues?.find((item) => item.code === value.league_code)

  return (
    <div className="flex flex-col gap-3">
      <TextField
        label="Город"
        value={value.city ?? ''}
        onChange={(event) => onChange({ ...value, city: event.target.value === '' ? null : event.target.value })}
        maxLength={100}
        placeholder="Например, Москва"
      />
      {leagues !== null && (
        <SelectField
          label="Лига"
          value={value.league_code}
          options={leagues.map((item) => ({ value: item.code, label: item.name }))}
          onChange={(event) =>
            onChange({ ...value, league_code: event.target.value, division_code: null, league_other_name: null })
          }
        />
      )}
      {league !== undefined && league.divisions.length > 0 && (
        <SelectField
          label="Дивизион"
          value={value.division_code ?? ''}
          placeholder="Не выбран"
          options={league.divisions.map((item) => ({ value: item.code, label: item.name }))}
          onChange={(event) => onChange({ ...value, division_code: event.target.value === '' ? null : event.target.value })}
        />
      )}
      {value.league_code === 'other' && (
        <TextField
          label="Название лиги"
          value={value.league_other_name ?? ''}
          onChange={(event) => onChange({ ...value, league_other_name: event.target.value })}
          maxLength={100}
        />
      )}
      <p className="text-xs text-text-secondary">
        Место в рейтинге появится, когда в вашей лиге и городе будет хотя бы три команды.
      </p>
    </div>
  )
}
