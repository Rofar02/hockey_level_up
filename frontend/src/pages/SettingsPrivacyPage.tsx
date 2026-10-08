import { useState } from 'react'
import * as usersApi from '../api/users'
import { ApiError } from '../api/client'
import { BackLink } from '../components/ui/BackLink'
import { FormError } from '../components/ui/FormError'
import { IceGlowBackground } from '../components/ui/IceGlowBackground'
import { useAuth } from '../hooks/useAuth'

const ADULT_AGE = 18

const SHOWN = ['Имя и фото', 'Команда', 'Позиция', 'Уровень', 'Карточка со статами']
const FRIENDS_ONLY = ['Возраст', 'Лента тренировок']

function Chip({ label, open }: { label: string; open: boolean }) {
  return (
    <span
      className={`rounded-full px-2.5 py-1 text-[13px] ${
        open ? 'bg-accent-ice/10 text-accent-ice' : 'border border-white/15 text-text-secondary'
      }`}
    >
      {label}
    </span>
  )
}

// "Меня можно найти по имени" (2026-10-08): on by default from 18, off
// below it; the player's own choice overrides the default either way.
export function SettingsPrivacyPage() {
  const { user, accessToken, updateUser } = useAuth()
  const [isSaving, setIsSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const findable = user?.findable_by_name ?? false
  const isMinor = user?.age == null || user.age < ADULT_AGE

  async function toggle() {
    if (accessToken === null) {
      return
    }
    setError(null)
    setIsSaving(true)
    try {
      updateUser(await usersApi.updateProfile({ name_search: !findable }, accessToken))
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Не удалось сохранить. Попробуйте ещё раз.')
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <div className="relative min-h-svh overflow-hidden">
      <IceGlowBackground />
      <div className="relative z-[1] mx-auto flex max-w-2xl flex-col gap-5 px-4 py-8">
        <div className="flex flex-col gap-2">
          <BackLink />
          <h1 className="text-xl font-semibold">Приватность</h1>
        </div>

        <section className="flex flex-col gap-3 rounded-2xl bg-dark-card p-4">
          <div className="flex items-center gap-3">
            <div className="flex min-w-0 flex-1 flex-col gap-0.5">
              <span id="name-search-label" className="text-[15px] font-semibold">
                Меня можно найти по имени
              </span>
              <span className="text-[13px] leading-snug text-text-secondary">
                {findable ? 'Другие игроки увидят тебя в поиске друзей' : 'Сейчас тебя не видно в поиске'}
              </span>
            </div>
            <button
              type="button"
              role="switch"
              aria-checked={findable}
              aria-labelledby="name-search-label"
              onClick={() => void toggle()}
              disabled={isSaving || user === null}
              className={`relative h-8 w-[52px] shrink-0 rounded-full transition-colors disabled:opacity-60 ${
                findable ? 'bg-accent-ice' : 'border border-white/20 bg-dark-bg'
              }`}
            >
              <span
                className={`absolute top-1/2 h-6 w-6 -translate-y-1/2 rounded-full transition-all ${
                  findable ? 'right-1 bg-dark-bg' : 'left-1 bg-text-secondary'
                }`}
              />
            </button>
          </div>
          <FormError message={error} />

          <div className="h-px bg-white/10" />
          <div className="flex flex-col gap-2">
            <span className="text-[13px] text-text-secondary">В поиске видно</span>
            <div className="flex flex-wrap gap-1.5">
              {SHOWN.map((label) => (
                <Chip key={label} label={label} open />
              ))}
            </div>
            <span className="mt-1 text-[13px] text-text-secondary">Только друзьям</span>
            <div className="flex flex-wrap gap-1.5">
              {FRIENDS_ONLY.map((label) => (
                <Chip key={label} label={label} open={false} />
              ))}
            </div>
          </div>
        </section>

        {isMinor && (
          <div className="flex gap-2.5 rounded-xl bg-dark-card p-3.5 text-[13px] leading-relaxed text-text-secondary">
            <i className="ti ti-shield mt-0.5 text-base" aria-hidden="true" />
            <p>
              Игроков младше 18 по умолчанию не найти по имени. Сокомандники всё равно видят тебя в списке команды, а
              остальным можно отправить свою ссылку из раздела «Друзья».
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
