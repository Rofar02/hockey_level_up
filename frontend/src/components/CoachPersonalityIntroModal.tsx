import { useState } from 'react'
import { Button } from './ui/Button'
import { ChoiceCard } from './ui/ChoiceCard'
import { FormError } from './ui/FormError'
import { Modal } from './ui/Modal'
import * as usersApi from '../api/users'
import { ApiError } from '../api/client'
import { COACH_PERSONALITY_CHOICES } from '../types/user'
import type { CoachPersonality } from '../types/user'
import { useAuth } from '../hooks/useAuth'

// Shown once, the first time a player opens /coach (2026-08-30 follow-up):
// coach_personality was silently defaulted to CALM with no explanation
// that it also drives reminder/check-in wording, not just this chat --
// see app.models.user.User's own comment. Picking a card saves it and
// dismisses; "Пропустить" keeps whatever's already set (CALM by default)
// and dismisses without a save. Either way, has_seen_coach_personality_intro
// flips to true so this never shows again.
export function CoachPersonalityIntroModal({ onClose }: { onClose: () => void }) {
  const { user, accessToken, updateUser } = useAuth()
  const [savingValue, setSavingValue] = useState<CoachPersonality | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function markSeen() {
    if (accessToken === null) {
      return
    }
    const updated = await usersApi.markCoachPersonalityIntroSeen(accessToken)
    updateUser(updated)
  }

  async function handleSelect(value: CoachPersonality) {
    if (accessToken === null || savingValue !== null) {
      return
    }
    setError(null)
    setSavingValue(value)
    try {
      await usersApi.updateProfile({ coach_personality: value }, accessToken)
      await markSeen()
      onClose()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Не удалось сохранить выбор. Попробуйте ещё раз.')
      setSavingValue(null)
    }
  }

  async function handleSkip() {
    try {
      await markSeen()
    } catch {
      // Best-effort -- worst case the intro shows again next visit.
    }
    onClose()
  }

  return (
    <Modal title="Личность тренера" onClose={handleSkip}>
      <div className="flex flex-col gap-4">
        <p className="text-sm text-text-secondary">
          Определяет тон, каким тренер общается с вами — включая напоминания о тренировках и утренние
          проверки самочувствия, а не только этот чат. Выбор можно изменить позже в настройках.
        </p>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {COACH_PERSONALITY_CHOICES.map((option) => (
            <ChoiceCard
              key={option.value}
              title={option.title}
              description={option.description}
              selected={user?.coach_personality === option.value}
              disabled={savingValue !== null}
              onClick={() => handleSelect(option.value)}
            />
          ))}
        </div>
        <FormError message={error} />
        <Button variant="neutral" onClick={handleSkip} disabled={savingValue !== null}>
          Пропустить
        </Button>
      </div>
    </Modal>
  )
}
