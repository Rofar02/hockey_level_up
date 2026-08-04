import { useEffect, useRef, useState } from 'react'
import type { ChangeEvent } from 'react'
import { Link } from 'react-router-dom'
import { BackLink } from '../components/ui/BackLink'
import { FormError } from '../components/ui/FormError'
import { Modal } from '../components/ui/Modal'
import { ProgressBar } from '../components/ui/ProgressBar'
import { ShieldBadge } from '../components/ui/ShieldBadge'
import { SkillDetailModal } from '../components/SkillDetailModal'
import * as progressApi from '../api/progress'
import * as skillsApi from '../api/skills'
import * as usersApi from '../api/users'
import { API_BASE_URL, ApiError } from '../api/client'
import { useAuth } from '../hooks/useAuth'
import { TARGET_STATS, TARGET_STAT_DESCRIPTIONS, TARGET_STAT_LABELS } from '../types/exercise'
import type { TargetStat } from '../types/exercise'
import type { UserStatRead } from '../types/progress'
import type { SkillDetailRead, SkillSummaryRead } from '../types/skill'
import { POSITION_LABELS } from '../types/user'

const STAT_ABBREVIATIONS: Record<TargetStat, string> = {
  strength: 'СИЛ',
  agility: 'ЛОВ',
  intellect: 'ИНТ',
  endurance: 'ВЫН',
}

// Skills with a still-open next milestone sort first, closest (smallest
// points_remaining) at the very top -- "almost there" is the motivating
// view. Fully-maxed skills (next_milestone === null) sink to the bottom.
function sortByClosestMilestone(skills: SkillSummaryRead[]): SkillSummaryRead[] {
  return [...skills].sort((a, b) => {
    const aRemaining = a.next_milestone?.points_remaining ?? Infinity
    const bRemaining = b.next_milestone?.points_remaining ?? Infinity
    return aRemaining - bRemaining
  })
}

export function ProfilePage() {
  const { user, accessToken, updateUser } = useAuth()

  const [stats, setStats] = useState<UserStatRead[] | null>(null)
  const [skills, setSkills] = useState<SkillSummaryRead[] | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)

  const [skillsExpanded, setSkillsExpanded] = useState(false)

  const [selectedSkillId, setSelectedSkillId] = useState<string | null>(null)
  const [skillDetails, setSkillDetails] = useState<Record<string, SkillDetailRead>>({})
  const [loadingDetailId, setLoadingDetailId] = useState<string | null>(null)
  const [detailError, setDetailError] = useState<string | null>(null)

  const [selectedStatType, setSelectedStatType] = useState<TargetStat | null>(null)

  const avatarInputRef = useRef<HTMLInputElement>(null)
  const [isUploadingAvatar, setIsUploadingAvatar] = useState(false)
  const [avatarError, setAvatarError] = useState<string | null>(null)
  const [isAvatarPreviewOpen, setIsAvatarPreviewOpen] = useState(false)

  useEffect(() => {
    if (accessToken === null) {
      return
    }
    let cancelled = false
    Promise.all([progressApi.getMyStats(accessToken), skillsApi.listSkills(accessToken)])
      .then(([statsResult, skillsResult]) => {
        if (cancelled) {
          return
        }
        setStats(statsResult)
        setSkills(skillsResult)
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setLoadError(err instanceof ApiError ? err.message : 'Не удалось загрузить профиль.')
        }
      })
      .finally(() => {
        if (!cancelled) {
          setIsLoading(false)
        }
      })
    return () => {
      cancelled = true
    }
  }, [accessToken])

  async function openSkillModal(skillId: string) {
    setSelectedSkillId(skillId)
    if (skillDetails[skillId] !== undefined || accessToken === null) {
      return
    }
    setDetailError(null)
    setLoadingDetailId(skillId)
    try {
      const detail = await skillsApi.getSkillDetail(skillId, accessToken)
      setSkillDetails((previous) => ({ ...previous, [skillId]: detail }))
    } catch (err) {
      setDetailError(err instanceof ApiError ? err.message : 'Не удалось загрузить детали навыка.')
    } finally {
      setLoadingDetailId(null)
    }
  }

  async function handleAvatarChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    // Reset so selecting the same file again still fires onChange.
    event.target.value = ''
    if (file === undefined || accessToken === null) {
      return
    }
    setAvatarError(null)
    setIsUploadingAvatar(true)
    try {
      const updated = await usersApi.uploadAvatar(file, accessToken)
      updateUser(updated)
    } catch (err) {
      setAvatarError(err instanceof ApiError ? err.message : 'Не удалось загрузить фото. Попробуйте ещё раз.')
    } finally {
      setIsUploadingAvatar(false)
    }
  }

  const statsByType = new Map(stats?.map((stat) => [stat.stat_type, stat]))
  const overallRating =
    stats !== null && stats.length > 0
      ? Math.round(stats.reduce((sum, stat) => sum + stat.effective_value, 0) / stats.length)
      : null
  const sortedSkills = skills !== null ? sortByClosestMilestone(skills) : null
  const selectedSkill = sortedSkills?.find((skill) => skill.id === selectedSkillId)
  const selectedStat = selectedStatType !== null ? statsByType.get(selectedStatType) : undefined

  const hasFullName = user !== null && user !== undefined && user.last_name !== '' && user.first_name !== ''
  const displayName = hasFullName
    ? [user.last_name, user.first_name, user.patronymic].filter(Boolean).join(' ').toUpperCase()
    : (user?.username ?? '')
  const ageExperienceParts = [
    user?.age != null ? `${user.age} лет` : null,
    user?.years_of_experience != null ? `${user.years_of_experience} лет стажа` : null,
  ].filter((part): part is string => part !== null)
  const avatarUrl = user?.avatar_url != null ? `${API_BASE_URL}${user.avatar_url}` : null

  return (
    <div className="mx-auto flex min-h-svh max-w-2xl flex-col gap-6 px-4 py-8">
      <div className="flex flex-col gap-2">
        <div className="flex items-center justify-between">
          <BackLink />
          <div className="flex items-center gap-4">
            <Link
              to="/leaderboard"
              aria-label="Рейтинг"
              className="text-text-secondary transition-colors hover:text-text-primary"
            >
              <i className="ti ti-trophy text-xl" aria-hidden="true" />
            </Link>
            <Link
              to="/settings"
              aria-label="Настройки"
              className="text-text-secondary transition-colors hover:text-text-primary"
            >
              <i className="ti ti-settings text-xl" aria-hidden="true" />
            </Link>
          </div>
        </div>
        <h1 className="text-xl font-semibold">Профиль</h1>
      </div>

      <FormError message={loadError} />
      {isLoading && <p className="text-sm text-text-secondary">Загрузка...</p>}

      {!isLoading && stats !== null && (
        <div className="mx-auto flex w-[310px] flex-col">
          <div className="relative overflow-hidden rounded-md border border-white/10">
            <div className="absolute inset-0 bg-[url('/images/rink-pattern.webp')] bg-cover bg-center" />
            <div className="absolute inset-0 bg-dark-bg/[0.85]" />

            <div className="relative flex flex-col gap-4 p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="flex flex-col items-center gap-2">
                  <ShieldBadge value={overallRating ?? '—'} label="Рейтинг" accentColor="ice" />
                  {user?.position != null && (
                    <span className="inline-block rounded border border-white/15 px-2 py-1 text-xs uppercase tracking-wide text-text-secondary">
                      {POSITION_LABELS[user.position]}
                    </span>
                  )}
                </div>
                {user?.jersey_number != null && (
                  <ShieldBadge value={user.jersey_number} label="Номер" accentColor="persimmon" />
                )}
              </div>

              <div className="flex justify-center py-2">
                <div className="relative">
                  <button
                    type="button"
                    onClick={() => {
                      if (avatarUrl !== null) {
                        setIsAvatarPreviewOpen(true)
                      } else {
                        avatarInputRef.current?.click()
                      }
                    }}
                    disabled={isUploadingAvatar}
                    aria-label={avatarUrl !== null ? 'Просмотреть фото профиля' : 'Загрузить фото профиля'}
                    className="relative flex h-32 w-32 items-center justify-center overflow-hidden rounded-full border-2 border-white/20 bg-dark-bg transition-opacity hover:opacity-90 disabled:cursor-wait"
                  >
                    {avatarUrl !== null ? (
                      <img src={avatarUrl} alt="Аватар" className="h-full w-full object-cover" />
                    ) : (
                      <i className="ti ti-user text-5xl text-text-secondary" aria-hidden="true" />
                    )}
                    {isUploadingAvatar && (
                      <div className="absolute inset-0 flex items-center justify-center bg-black/60">
                        <i className="ti ti-loader-2 animate-spin text-3xl text-text-primary" aria-hidden="true" />
                      </div>
                    )}
                  </button>
                  <button
                    type="button"
                    onClick={() => avatarInputRef.current?.click()}
                    disabled={isUploadingAvatar}
                    aria-label="Изменить фото профиля"
                    className="absolute bottom-0 right-0 flex h-9 w-9 items-center justify-center rounded-full border-2 border-dark-bg bg-accent-ice text-dark-bg transition-opacity hover:opacity-90 disabled:cursor-wait"
                  >
                    <i className="ti ti-camera text-base" aria-hidden="true" />
                  </button>
                  <input
                    ref={avatarInputRef}
                    type="file"
                    accept="image/*"
                    capture="user"
                    className="hidden"
                    onChange={handleAvatarChange}
                  />
                </div>
              </div>

              <div className="rounded bg-dark-bg/60 px-3 py-3 text-center">
                <p className="text-base font-bold uppercase tracking-wide text-text-primary">
                  {displayName}
                </p>
                {ageExperienceParts.length > 0 && (
                  <p className="mt-1 text-sm text-text-secondary">{ageExperienceParts.join(' · ')}</p>
                )}
              </div>

              <div className="grid grid-cols-4 gap-2">
                {TARGET_STATS.map((statType) => {
                  const stat = statsByType.get(statType)
                  if (stat === undefined) {
                    return null
                  }
                  return (
                    <button
                      key={statType}
                      type="button"
                      onClick={() => setSelectedStatType(statType)}
                      className="flex flex-col items-center rounded py-1.5 text-center transition-colors hover:bg-white/5"
                    >
                      <span className="text-xs text-text-secondary">{STAT_ABBREVIATIONS[statType]}</span>
                      <span className="font-mono text-2xl font-bold text-text-primary">
                        {Math.round(stat.effective_value)}
                      </span>
                    </button>
                  )
                })}
              </div>
            </div>
          </div>
          <FormError message={avatarError} />
        </div>
      )}

      {!isLoading && sortedSkills !== null && (
        <div className="overflow-hidden rounded-md border border-white/5 bg-dark-card">
          <button
            type="button"
            onClick={() => setSkillsExpanded((value) => !value)}
            className="flex w-full items-center justify-between p-4 text-left"
          >
            <span className="font-medium text-text-primary">Навыки</span>
            <i
              className={`ti ${skillsExpanded ? 'ti-chevron-down' : 'ti-chevron-right'} text-text-secondary`}
              aria-hidden="true"
            />
          </button>

          {skillsExpanded && (
            <div className="flex flex-col gap-3 border-t border-white/5 p-4">
              {sortedSkills.map((skill) => {
                const barMax = skill.next_milestone?.threshold ?? skill.value
                return (
                  <button
                    key={skill.id}
                    type="button"
                    onClick={() => openSkillModal(skill.id)}
                    className="flex w-full flex-col gap-2 rounded-md border border-white/5 bg-dark-bg p-5 text-left transition-colors hover:border-white/20"
                  >
                    <p className="font-medium text-text-primary">{skill.name}</p>
                    <ProgressBar value={skill.value} max={barMax} />
                    <p className="text-xs text-text-secondary">
                      {skill.next_milestone !== null
                        ? `${Math.round(skill.next_milestone.points_remaining)} до «${skill.next_milestone.title}»`
                        : 'Все пороги пройдены'}
                    </p>
                  </button>
                )
              })}
            </div>
          )}
        </div>
      )}

      {selectedSkillId !== null && (
        <SkillDetailModal
          skillName={selectedSkill?.name ?? ''}
          detail={skillDetails[selectedSkillId]}
          isLoading={loadingDetailId === selectedSkillId}
          error={detailError}
          onClose={() => setSelectedSkillId(null)}
        />
      )}

      {selectedStatType !== null && selectedStat !== undefined && (
        <StatDetailModal
          statType={selectedStatType}
          stat={selectedStat}
          onClose={() => setSelectedStatType(null)}
        />
      )}

      {isAvatarPreviewOpen && avatarUrl !== null && (
        <Modal title="Фото профиля" onClose={() => setIsAvatarPreviewOpen(false)}>
          <img src={avatarUrl} alt="Аватар" className="w-full rounded" />
        </Modal>
      )}
    </div>
  )
}

function StatDetailModal({
  statType,
  stat,
  onClose,
}: {
  statType: TargetStat
  stat: UserStatRead
  onClose: () => void
}) {
  return (
    <Modal title={TARGET_STAT_LABELS[statType]} onClose={onClose}>
      <div className="flex flex-col gap-4">
        <p className="text-sm text-text-secondary">{TARGET_STAT_DESCRIPTIONS[statType]}</p>
        <div>
          <p className="font-mono text-3xl font-bold leading-none text-text-primary">
            {Math.round(stat.effective_value)}
          </p>
          {stat.decay_active && (
            <p className="mt-2 flex items-center gap-1 text-xs text-text-secondary">
              <i className="ti ti-trending-down" aria-hidden="true" />
              затухает, {Math.round(stat.idle_days)} дней без нагрузки
            </p>
          )}
        </div>
      </div>
    </Modal>
  )
}
