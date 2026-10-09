import { useState } from 'react'
import type { FormEvent } from 'react'
import * as teamsApi from '../../api/teams'
import { ApiError } from '../../api/client'
import { useAuth } from '../../hooks/useAuth'
import type { TeamLeagueFields as TeamLeagueValues, TeamRead } from '../../types/team'
import { TeamLeagueFields, isTeamLeagueComplete } from '../TeamLeagueFields'
import { Button } from '../ui/Button'
import { FormError } from '../ui/FormError'
import { TextField } from '../ui/TextField'

interface TeamSettingsFormProps {
  team: TeamRead
  onSaved: (team: TeamRead) => void
  onCancel: () => void
}

/** The captain's team settings: name, city, league, division. */
export function TeamSettingsForm({ team, onSaved, onCancel }: TeamSettingsFormProps) {
  const { accessToken } = useAuth()
  const [name, setName] = useState(team.name)
  const [league, setLeague] = useState<TeamLeagueValues>({
    city: team.city,
    league_code: team.league_code,
    division_code: team.division_code,
    league_other_name: team.league_other_name,
  })
  const [isSaving, setIsSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const canSave = name.trim() !== '' && isTeamLeagueComplete(league)

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (accessToken === null || !canSave) {
      return
    }
    setError(null)
    setIsSaving(true)
    try {
      onSaved(await teamsApi.updateTeam(team.id, { ...league, name: name.trim() }, accessToken))
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Не удалось сохранить настройки команды.')
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-3">
      <TextField label="Название" value={name} onChange={(event) => setName(event.target.value)} maxLength={100} />
      <TeamLeagueFields value={league} onChange={setLeague} />
      <FormError message={error} />
      <div className="flex gap-2">
        <Button type="submit" isLoading={isSaving} disabled={!canSave}>
          Сохранить
        </Button>
        <Button type="button" variant="neutral" onClick={onCancel} disabled={isSaving}>
          Отмена
        </Button>
      </div>
    </form>
  )
}
