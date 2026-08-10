import { useEffect, useRef, useState } from 'react'
import type { ChangeEvent } from 'react'
import { Link } from 'react-router-dom'
import { BackLink } from '../components/ui/BackLink'
import { FormError } from '../components/ui/FormError'
import { IceGlowBackground } from '../components/ui/IceGlowBackground'
import { JerseyBadge } from '../components/ui/JerseyBadge'
import { Modal } from '../components/ui/Modal'
import { ProgressBar } from '../components/ui/ProgressBar'
import { LockedSkillChip } from '../components/ui/SkillChip'
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
import { getAvatarTierStyle } from '../utils/avatarTier'
import { getDisplayName } from '../utils/displayName'
import { transliterate } from '../utils/transliterate'

const STAT_ABBREVIATIONS: Record<TargetStat, string> = {
  strength: 'СИЛ',
  agility: 'ЛОВ',
  intellect: 'ИНТ',
  endurance: 'ВЫН',
  on_ice_skating: 'ЛЁД',
  puck_handling: 'ШАЙ',
}

// Same icy top-border card convention as HomePage/TrainingSessionPage.
const CARD_BORDER = 'border-t border-[rgba(215,239,255,0.35)]'

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
  // Skills the user picked as priorities (UserSkillPreference) -- highlighted
  // in the overview modal below, same idea as HomePage's "почти порог"
  // persimmon treatment, just for a different signal.
  const [preferredSkillIds, setPreferredSkillIds] = useState<Set<string>>(new Set())
  const [isLoading, setIsLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)

  const [isSkillsOverviewOpen, setIsSkillsOverviewOpen] = useState(false)

  const [selectedSkillId, setSelectedSkillId] = useState<string | null>(null)
  const [skillDetails, setSkillDetails] = useState<Record<string, SkillDetailRead>>({})
  const [loadingDetailId, setLoadingDetailId] = useState<string | null>(null)
  const [detailError, setDetailError] = useState<string | null>(null)
  // Whether the open SkillDetailModal was reached via the overview list --
  // closing it should feel like "back" (reopen the overview) in that case,
  // not "exit everything". Any future direct-open path that never routes
  // through selectSkillFromOverview leaves this false, so it keeps the
  // plain close-and-done behavior.
  const [detailOpenedFromOverview, setDetailOpenedFromOverview] = useState(false)

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
    Promise.all([
      progressApi.getMyStats(accessToken),
      skillsApi.listSkills(accessToken),
      usersApi.getSkillPreferences(accessToken),
    ])
      .then(([statsResult, skillsResult, preferencesResult]) => {
        if (cancelled) {
          return
        }
        setStats(statsResult)
        setSkills(skillsResult)
        setPreferredSkillIds(new Set(preferencesResult.map((preference) => preference.skill_id)))
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

  // Stacking Modal on top of Modal (two dimmed backdrops, two centered
  // cards) reads as broken rather than "drilling down" -- so the overview
  // closes itself the instant a row is picked, then the detail modal takes
  // its place instead of layering above it.
  function selectSkillFromOverview(skillId: string) {
    setIsSkillsOverviewOpen(false)
    setDetailOpenedFromOverview(true)
    void openSkillModal(skillId)
  }

  function closeSkillDetailModal() {
    setSelectedSkillId(null)
    if (detailOpenedFromOverview) {
      setDetailOpenedFromOverview(false)
      setIsSkillsOverviewOpen(true)
    }
  }

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
  // Split by required_level, same gate SettingsPage's skill picker already
  // applies (see LockedSkillChip there) -- locked skills are still shown
  // (the overview is a preview of the whole catalog, not just what's
  // reachable now), just not clickable and rendered with the same
  // locked-chip treatment instead of a progress row.
  const unlockedSkills =
    skills !== null
      ? sortByClosestMilestone(skills.filter((skill) => skill.required_level <= (user?.level ?? 1)))
      : null
  const lockedSkills =
    skills !== null
      ? [...skills.filter((skill) => skill.required_level > (user?.level ?? 1))].sort(
          (a, b) => a.required_level - b.required_level,
        )
      : null
  const selectedSkill = skills?.find((skill) => skill.id === selectedSkillId)
  const selectedStat = selectedStatType !== null ? statsByType.get(selectedStatType) : undefined

  const displayName = user !== null ? getDisplayName(user).toUpperCase() : ''
  const ageExperienceParts = [
    user?.age != null ? `${user.age} лет` : null,
    user?.years_of_experience != null ? `${user.years_of_experience} лет стажа` : null,
  ].filter((part): part is string => part !== null)
  const avatarUrl = user?.avatar_url != null ? `${API_BASE_URL}${user.avatar_url}` : null
  const avatarTierStyle = getAvatarTierStyle(user?.level ?? 1)

  return (
    <div className="relative min-h-svh overflow-hidden">
      <IceGlowBackground />
      {/* gap-4/py-6, not the page-wide gap-6/py-8 default -- installed as a
          home-screen PWA on iOS loses the address bar's vertical budget, so
          this page's own content (card + stats + Skills button) needs to sit
          tighter to clear the fixed BottomNav without scrolling on a phone
          like iPhone 13 Pro (measured live: was short by ~20px). */}
      <div className="relative z-[1] mx-auto flex max-w-2xl flex-col gap-4 px-4 py-6">
      <div className="flex flex-col gap-2">
        <div className="flex items-center justify-between">
          <BackLink />
          <div className="flex items-center gap-4">
            <Link
              to="/leaderboard"
              aria-label="Рейтинг"
              className="text-[#8A94A6] transition-colors hover:text-[#F5F7FA]"
            >
              <i className="ti ti-trophy text-xl" aria-hidden="true" />
            </Link>
            <Link
              to="/analytics"
              aria-label="Аналитика"
              className="text-[#8A94A6] transition-colors hover:text-[#F5F7FA]"
            >
              <i className="ti ti-chart-line text-xl" aria-hidden="true" />
            </Link>
            <Link
              to="/coach"
              aria-label="ИИ-тренер"
              className="text-[#8A94A6] transition-colors hover:text-[#F5F7FA]"
            >
              <i className="ti ti-message-chatbot text-xl" aria-hidden="true" />
            </Link>
            <Link
              to="/settings"
              aria-label="Настройки"
              className="text-[#8A94A6] transition-colors hover:text-[#F5F7FA]"
            >
              <i className="ti ti-settings text-xl" aria-hidden="true" />
            </Link>
          </div>
        </div>
        <h1 className="text-xl font-semibold">Профиль</h1>
      </div>

      <FormError message={loadError} />
      {isLoading && <p className="text-sm text-[#8A94A6]">Загрузка...</p>}

      {!isLoading && stats !== null && (
        <div className="mx-auto flex w-full max-w-[310px] flex-col">
          {/* Keeps its rink-pattern.webp background image + dark overlay --
              flagged separately as a different card-assembly pattern from
              the rest of the app, not silently flattened to bg-dark-card
              here. Only the border (full -> icy top-only) and text tokens
              changed. */}
          <div className={`relative overflow-hidden rounded-md ${CARD_BORDER}`}>
            <div className="absolute inset-0 bg-[url('/images/rink-pattern.webp')] bg-cover bg-center" />
            <div className="absolute inset-0 bg-dark-bg/[0.85]" />

            <div className="relative flex flex-col gap-4 p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="flex flex-col items-center gap-2">
                  <JerseyBadge number={overallRating ?? '—'} label="Рейтинг" accentColor="ice" />
                  {user?.position != null && (
                    <span className="inline-block rounded border border-white/15 px-2 py-1 text-xs uppercase tracking-wide text-[#8A94A6]">
                      {POSITION_LABELS[user.position]}
                    </span>
                  )}
                </div>
                {user?.jersey_number != null && (
                  <JerseyBadge
                    number={user.jersey_number}
                    label="Номер"
                    accentColor="persimmon"
                    surname={transliterate(user.last_name)}
                  />
                )}
              </div>

              <div className="flex justify-center py-1">
                <div className="relative">
                  {/* Two-layer wrapper, same reason as HomePage's avatar:
                      the tier border/glow (box-shadow) lives on this outer
                      div, and the button below keeps overflow-hidden to
                      clip the photo -- combining both on one element would
                      clip the glow along with the photo. */}
                  <div className="h-32 w-32 rounded-full" style={avatarTierStyle.style}>
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
                      className="relative flex h-full w-full items-center justify-center overflow-hidden rounded-full bg-dark-bg transition-opacity hover:opacity-90 disabled:cursor-wait"
                    >
                      {avatarUrl !== null ? (
                        <img src={avatarUrl} alt="Аватар" className="h-full w-full object-cover" />
                      ) : (
                        <i className="ti ti-user text-5xl text-[#8A94A6]" aria-hidden="true" />
                      )}
                      {isUploadingAvatar && (
                        <div className="absolute inset-0 flex items-center justify-center bg-black/60">
                          <i className="ti ti-loader-2 animate-spin text-3xl text-[#F5F7FA]" aria-hidden="true" />
                        </div>
                      )}
                    </button>
                  </div>
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
                    className="hidden"
                    onChange={handleAvatarChange}
                  />
                </div>
              </div>

              <div className="rounded bg-dark-bg/60 px-3 py-3 text-center">
                <p className="text-base font-bold uppercase tracking-wide text-[#F5F7FA]">
                  {displayName}
                </p>
                {ageExperienceParts.length > 0 && (
                  <p className="mt-1 text-sm text-[#8A94A6]">{ageExperienceParts.join(' · ')}</p>
                )}
              </div>

              <div className="grid grid-cols-3 gap-2">
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
                      <span className="text-xs text-[#8A94A6]">{STAT_ABBREVIATIONS[statType]}</span>
                      {/* Numbers use the ice accent, not primary text --
                          matches the "#D7EFFF for numbers" rule already
                          applied on Home/TrainingSession. */}
                      <span className="font-mono text-2xl font-bold text-accent-ice">
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

      {!isLoading && skills !== null && (
        <button
          type="button"
          onClick={() => setIsSkillsOverviewOpen(true)}
          className={`flex w-full items-center justify-between rounded-md ${CARD_BORDER} bg-dark-card p-4 text-left`}
        >
          <span className="font-medium text-[#F5F7FA]">Навыки</span>
          <i className="ti ti-chevron-right text-[#8A94A6]" aria-hidden="true" />
        </button>
      )}

      {isSkillsOverviewOpen && unlockedSkills !== null && lockedSkills !== null && (
        <SkillsOverviewModal
          unlockedSkills={unlockedSkills}
          lockedSkills={lockedSkills}
          preferredSkillIds={preferredSkillIds}
          onSelectSkill={selectSkillFromOverview}
          onClose={() => setIsSkillsOverviewOpen(false)}
        />
      )}

      {selectedSkillId !== null && (
        <SkillDetailModal
          skillName={selectedSkill?.name ?? ''}
          detail={skillDetails[selectedSkillId]}
          isLoading={loadingDetailId === selectedSkillId}
          error={detailError}
          onClose={closeSkillDetailModal}
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
    </div>
  )
}

// Compact stand-in for the old inline expand list -- tapping the "Навыки"
// block now opens this instead of expanding in place, so every skill (not
// just the top few) needs a glanceable row here. Priority skills
// (UserSkillPreference, picked in Settings) get the same persimmon accent
// HomePage's "почти порог" card uses for its own attention-signal, just
// applied to the row border/star/label instead of a bar-only tint.
function SkillsOverviewModal({
  unlockedSkills,
  lockedSkills,
  preferredSkillIds,
  onSelectSkill,
  onClose,
}: {
  unlockedSkills: SkillSummaryRead[]
  lockedSkills: SkillSummaryRead[]
  preferredSkillIds: Set<string>
  onSelectSkill: (skillId: string) => void
  onClose: () => void
}) {
  return (
    <Modal title="Навыки" onClose={onClose}>
      <div className="flex flex-col gap-4">
        <p className="text-sm text-[#8A94A6]">
          Приоритетные навыки — те, что вы выбрали в настройках, — чаще получают подходящие
          упражнения в тренировках. Остальные тоже растут, от общей физической подготовки,
          просто медленнее.
        </p>
        <div className="flex flex-col gap-2">
          {unlockedSkills.map((skill) => {
            const barMax = skill.next_milestone?.threshold ?? skill.value
            const isPreferred = preferredSkillIds.has(skill.id)
            return (
              <button
                key={skill.id}
                type="button"
                onClick={() => onSelectSkill(skill.id)}
                className={`flex w-full flex-col gap-1.5 rounded-md border p-3 text-left transition-colors ${
                  isPreferred
                    ? 'border-accent-persimmon/40 bg-accent-persimmon/5 hover:border-accent-persimmon/60'
                    : 'border-white/10 hover:border-white/20'
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="flex min-w-0 items-center gap-1.5">
                    {isPreferred && (
                      <i
                        className="ti ti-star-filled shrink-0 text-xs text-accent-persimmon"
                        aria-hidden="true"
                      />
                    )}
                    <span className="truncate text-sm font-medium text-[#F5F7FA]">{skill.name}</span>
                  </span>
                  {isPreferred && (
                    <span className="shrink-0 text-xs font-medium text-accent-persimmon">
                      Приоритет
                    </span>
                  )}
                </div>
                <ProgressBar value={skill.value} max={barMax} accent={isPreferred ? 'persimmon' : 'ice'} />
              </button>
            )
          })}
          {/* Same LockedSkillChip SettingsPage's picker uses for skills
              gated by level -- not clickable (there's no reachable progress
              detail to show yet), just a preview of what's still ahead. */}
          {lockedSkills.map((skill) => (
            <LockedSkillChip key={skill.id} label={skill.name} requiredLevel={skill.required_level} />
          ))}
        </div>
      </div>
    </Modal>
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
        <p className="text-sm text-[#8A94A6]">{TARGET_STAT_DESCRIPTIONS[statType]}</p>
        <div>
          {/* Matches HomePage's own StatDetailModal: a large "hero" number
              in a modal reads as primary text, not the ice accent -- ice is
              reserved for compact numbers in card grids (see the 4-tile
              row above). */}
          <p className="font-mono text-3xl font-bold leading-none text-[#F5F7FA]">
            {Math.round(stat.effective_value)}
          </p>
          {stat.decay_active && (
            <p className="mt-2 flex items-center gap-1 text-xs text-[#8A94A6]">
              <i className="ti ti-trending-down" aria-hidden="true" />
              затухает, {Math.round(stat.idle_days)} дней без нагрузки
            </p>
          )}
        </div>
      </div>
    </Modal>
  )
}
