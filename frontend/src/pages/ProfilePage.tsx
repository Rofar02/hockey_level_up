import { useEffect, useRef, useState } from 'react'
import type { ChangeEvent, ReactNode } from 'react'
import { Link, useParams } from 'react-router-dom'
import { BackLink } from '../components/ui/BackLink'
import { Button } from '../components/ui/Button'
import { FormError } from '../components/ui/FormError'
import { IceGlowBackground } from '../components/ui/IceGlowBackground'
import { JerseyBadge } from '../components/ui/JerseyBadge'
import { Modal } from '../components/ui/Modal'
import { ProgressBar } from '../components/ui/ProgressBar'
import { LockedSkillChip } from '../components/ui/SkillChip'
import { MuscleLoadChart } from '../components/MuscleLoadChart'
import { SkillDetailModal } from '../components/SkillDetailModal'
import * as authApi from '../api/auth'
import * as exercisesApi from '../api/exercises'
import * as progressApi from '../api/progress'
import * as skillsApi from '../api/skills'
import * as usersApi from '../api/users'
import { API_BASE_URL, ApiError } from '../api/client'
import { useAuth } from '../hooks/useAuth'
import {
  EQUIPMENT_ITEMS,
  EQUIPMENT_ITEM_LABELS,
  TARGET_STATS,
  TARGET_STAT_DESCRIPTIONS,
  TARGET_STAT_LABELS,
} from '../types/exercise'
import type { EquipmentItem, ExerciseEquipmentRequirement, TargetStat } from '../types/exercise'
import type { MuscleLoadRead, UserStatRead } from '../types/progress'
import type { SkillDetailRead, SkillSummaryRead } from '../types/skill'
import { POSITION_LABELS } from '../types/user'
import type { UserPublicRead } from '../types/user'
import { getAvatarTierStyle } from '../utils/avatarTier'
import { getDisplayName } from '../utils/displayName'
import { countAvailableExercises, countExercisesUsingItem } from '../utils/equipmentAvailability'
import { EQUIPMENT_ICONS, EQUIPMENT_ITEM_DESCRIPTIONS } from '../utils/equipmentIcons'
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

// Thin dispatcher: /profile (no :userId, or :userId === your own id) keeps
// the existing full self-view (stats, skills, avatar upload -- all of it
// still /me/... underneath); any other :userId switches to the read-only,
// friends/teammates-only public view. Two separate components rather than
// one with an early return, so each keeps its own independent, unconditional
// hook sequence -- an early return before some of OwnProfileView's hooks but
// after others would violate the rules of hooks the moment :userId changes.
export function ProfilePage() {
  const { userId } = useParams<{ userId?: string }>()
  const { user } = useAuth()
  if (userId !== undefined && userId !== user?.id) {
    return <OtherUserProfileView userId={userId} />
  }
  return <OwnProfileView />
}

function OwnProfileView() {
  const { user, accessToken, updateUser } = useAuth()

  const [stats, setStats] = useState<UserStatRead[] | null>(null)
  const [skills, setSkills] = useState<SkillSummaryRead[] | null>(null)
  // Skills the user picked as priorities (UserSkillPreference) -- highlighted
  // in the overview modal below, same idea as HomePage's "почти порог"
  // persimmon treatment, just for a different signal.
  const [preferredSkillIds, setPreferredSkillIds] = useState<Set<string>>(new Set())
  const [isLoading, setIsLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)

  // One modal, three tabs (Навыки/Нагрузка/Инвентарь) -- each of the three
  // summary cards further down opens this same modal, landing on its own
  // tab. null means closed; a tab value both opens it and picks which tab
  // is active on open.
  const [openDetailsTab, setOpenDetailsTab] = useState<ProfileDetailsTab | null>(null)

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

  const [isResendingVerification, setIsResendingVerification] = useState(false)
  const [verificationResendResult, setVerificationResendResult] = useState<string | null>(null)
  const [verificationResendError, setVerificationResendError] = useState<string | null>(null)

  // Stage 2.3: inventory showcase card below -- purely a summary of data
  // already editable in Settings, so best-effort like the rest of this
  // page's optional widgets rather than blocking isLoading on its own.
  const [ownedItems, setOwnedItems] = useState<Set<EquipmentItem> | null>(null)
  const [equipmentRequirements, setEquipmentRequirements] = useState<ExerciseEquipmentRequirement[] | null>(null)

  // Body-muscles map (2026-08-20 planning session) -- same best-effort,
  // own-effect treatment as the equipment showcase above: independent
  // data, doesn't block isLoading/the rest of the page on its own.
  const [muscleLoads, setMuscleLoads] = useState<MuscleLoadRead[] | null>(null)

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

  useEffect(() => {
    if (accessToken === null) {
      return
    }
    let cancelled = false
    Promise.all([
      usersApi.getMyEquipmentItems(accessToken),
      exercisesApi.listExerciseEquipmentRequirements(accessToken),
    ])
      .then(([items, requirements]) => {
        if (!cancelled) {
          setOwnedItems(new Set(items))
          setEquipmentRequirements(requirements)
        }
      })
      .catch(() => {
        // Best-effort -- the showcase card just doesn't render.
      })
    return () => {
      cancelled = true
    }
  }, [accessToken])

  const [inventoryToggleError, setInventoryToggleError] = useState<string | null>(null)

  // Game-inventory tab: toggling one item's owned state from inside the
  // detail panel, full-replace under the hood (same PUT endpoint Settings
  // uses) since that's the only shape the backend offers -- optimistic
  // local update first, roll back on failure rather than waiting on the
  // round trip before the icon visually responds.
  async function handleToggleEquipmentItem(item: EquipmentItem) {
    if (accessToken === null || ownedItems === null) {
      return
    }
    const wasOwned = ownedItems.has(item)
    const next = new Set(ownedItems)
    if (wasOwned) {
      next.delete(item)
    } else {
      next.add(item)
    }
    setOwnedItems(next)
    setInventoryToggleError(null)
    try {
      await usersApi.replaceMyEquipmentItems(Array.from(next), accessToken)
    } catch (err) {
      setOwnedItems(ownedItems)
      setInventoryToggleError(
        err instanceof ApiError ? err.message : 'Не удалось обновить инвентарь.',
      )
    }
  }

  useEffect(() => {
    if (accessToken === null) {
      return
    }
    let cancelled = false
    progressApi
      .getMyMuscleLoads(accessToken)
      .then((result) => {
        if (!cancelled) {
          setMuscleLoads(result)
        }
      })
      .catch(() => {
        // Best-effort -- the chart just doesn't render.
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
    setOpenDetailsTab(null)
    setDetailOpenedFromOverview(true)
    void openSkillModal(skillId)
  }

  function closeSkillDetailModal() {
    setSelectedSkillId(null)
    if (detailOpenedFromOverview) {
      setDetailOpenedFromOverview(false)
      setOpenDetailsTab('skills')
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

  async function handleResendVerification() {
    if (accessToken === null) {
      return
    }
    setVerificationResendError(null)
    setIsResendingVerification(true)
    try {
      const result = await authApi.resendVerificationEmail(accessToken)
      setVerificationResendResult(result.detail)
    } catch (err) {
      setVerificationResendError(
        err instanceof ApiError ? err.message : 'Не удалось отправить письмо. Попробуйте ещё раз.',
      )
    } finally {
      setIsResendingVerification(false)
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

      {!isLoading && user !== null && !user.email_verified && (
        <div className={`flex flex-col gap-2 rounded-md ${CARD_BORDER} bg-dark-card p-4`}>
          <div className="flex items-center gap-2">
            <i className="ti ti-mail-exclamation text-lg text-accent-persimmon" aria-hidden="true" />
            <span className="text-sm font-medium text-[#F5F7FA]">Email не подтверждён</span>
          </div>
          {verificationResendResult === null ? (
            <>
              <p className="text-sm text-[#8A94A6]">
                Проверьте почту {user.email} и перейдите по ссылке из письма.
              </p>
              <Button
                type="button"
                variant="neutral"
                isLoading={isResendingVerification}
                onClick={handleResendVerification}
                className="self-start !px-3 !py-1.5 !text-xs"
              >
                Отправить письмо ещё раз
              </Button>
              <FormError message={verificationResendError} />
            </>
          ) : (
            <p className="text-sm text-accent-ice">{verificationResendResult}</p>
          )}
        </div>
      )}

      {/* 3 equal-width quick-action buttons in one row, directly under the
          profile card and spanning the same width -- a compact "character
          sheet" action bar instead of three separate stacked cards. Each
          just opens ProfileDetailsModal on its own tab. */}
      <div className="grid grid-cols-3 gap-2">
        {!isLoading && skills !== null && (
          <button
            type="button"
            onClick={() => setOpenDetailsTab('skills')}
            className={`flex flex-col items-center gap-1 rounded-md ${CARD_BORDER} bg-dark-card px-2 py-3 transition-colors hover:bg-white/5`}
          >
            <i className="ti ti-target text-xl text-accent-ice" aria-hidden="true" />
            <span className="text-xs font-medium text-[#F5F7FA]">Навыки</span>
          </button>
        )}

        {muscleLoads !== null && (
          <button
            type="button"
            onClick={() => setOpenDetailsTab('muscleLoad')}
            className={`flex flex-col items-center gap-1 rounded-md ${CARD_BORDER} bg-dark-card px-2 py-3 transition-colors hover:bg-white/5`}
          >
            <i className="ti ti-flame text-xl text-accent-ice" aria-hidden="true" />
            <span className="text-xs font-medium text-[#F5F7FA]">Нагрузка</span>
          </button>
        )}

        {ownedItems !== null && equipmentRequirements !== null && (
          <button
            type="button"
            onClick={() => setOpenDetailsTab('inventory')}
            className={`flex flex-col items-center gap-1 rounded-md ${CARD_BORDER} bg-dark-card px-2 py-3 transition-colors hover:bg-white/5`}
          >
            <i className="ti ti-backpack text-xl text-accent-ice" aria-hidden="true" />
            <span className="text-xs font-medium text-[#F5F7FA]">Инвентарь</span>
          </button>
        )}
      </div>

      {openDetailsTab !== null && unlockedSkills !== null && lockedSkills !== null && (
        <ProfileDetailsModal
          initialTab={openDetailsTab}
          unlockedSkills={unlockedSkills}
          lockedSkills={lockedSkills}
          preferredSkillIds={preferredSkillIds}
          onSelectSkill={selectSkillFromOverview}
          muscleLoads={muscleLoads ?? []}
          hasGymAccess={user?.has_gym_access ?? false}
          ownedItems={ownedItems ?? new Set()}
          equipmentRequirements={equipmentRequirements ?? []}
          onToggleEquipmentItem={handleToggleEquipmentItem}
          inventoryToggleError={inventoryToggleError}
          onClose={() => setOpenDetailsTab(null)}
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

// Read-only view of someone else's profile -- backed by GET /users/{id}/profile
// (UserPublicRead), which the server 403s unless requester and target are
// friends or teammates (UserService.get_public_profile). Deliberately much
// smaller than OwnProfileView above: UserPublicRead has no stats/skills/xp-bar
// data and no weight/height under any circumstance, so there's nothing to
// build a stats grid or skills section out of here -- see the diagnosis.
function OtherUserProfileView({ userId }: { userId: string }) {
  const { accessToken } = useAuth()
  const [profile, setProfile] = useState<UserPublicRead | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [isForbidden, setIsForbidden] = useState(false)

  useEffect(() => {
    if (accessToken === null) {
      return
    }
    let cancelled = false
    setProfile(null)
    setLoadError(null)
    setIsForbidden(false)
    usersApi
      .getUserPublicProfile(userId, accessToken)
      .then((result) => {
        if (!cancelled) {
          setProfile(result)
        }
      })
      .catch((err: unknown) => {
        if (cancelled) {
          return
        }
        if (err instanceof ApiError && err.status === 403) {
          setIsForbidden(true)
        } else {
          setLoadError(err instanceof ApiError ? err.message : 'Не удалось загрузить профиль.')
        }
      })
    return () => {
      cancelled = true
    }
  }, [accessToken, userId])

  const avatarTierStyle = getAvatarTierStyle(profile?.level ?? 1)
  const avatarUrl = profile?.avatar_url != null ? `${API_BASE_URL}${profile.avatar_url}` : null

  return (
    <div className="relative min-h-svh overflow-hidden">
      <IceGlowBackground />
      <div className="relative z-[1] mx-auto flex max-w-2xl flex-col gap-4 px-4 py-6">
        <BackLink />

        {isForbidden && (
          <p className="text-sm text-[#8A94A6]">
            Этот профиль виден только друзьям и сокомандникам.
          </p>
        )}
        <FormError message={loadError} />
        {profile === null && !isForbidden && loadError === null && (
          <p className="text-sm text-[#8A94A6]">Загрузка...</p>
        )}

        {profile !== null && (
          <div className="mx-auto flex w-full max-w-[310px] flex-col">
            <div className={`relative overflow-hidden rounded-md ${CARD_BORDER}`}>
              <div className="absolute inset-0 bg-[url('/images/rink-pattern.webp')] bg-cover bg-center" />
              <div className="absolute inset-0 bg-dark-bg/[0.85]" />

              <div className="relative flex flex-col gap-4 p-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex flex-col items-center gap-2">
                    <JerseyBadge number={profile.level} label="Уровень" accentColor="ice" />
                    {profile.position != null && (
                      <span className="inline-block rounded border border-white/15 px-2 py-1 text-xs uppercase tracking-wide text-[#8A94A6]">
                        {POSITION_LABELS[profile.position]}
                      </span>
                    )}
                  </div>
                  {profile.jersey_number != null && (
                    <JerseyBadge
                      number={profile.jersey_number}
                      label="Номер"
                      accentColor="persimmon"
                      surname={transliterate(profile.last_name)}
                    />
                  )}
                </div>

                <div className="flex justify-center py-1">
                  <div className="h-32 w-32 rounded-full" style={avatarTierStyle.style}>
                    <div className="relative flex h-full w-full items-center justify-center overflow-hidden rounded-full bg-dark-bg">
                      {avatarUrl !== null ? (
                        <img src={avatarUrl} alt="Аватар" className="h-full w-full object-cover" />
                      ) : (
                        <i className="ti ti-user text-5xl text-[#8A94A6]" aria-hidden="true" />
                      )}
                    </div>
                  </div>
                </div>

                <div className="rounded bg-dark-bg/60 px-3 py-3 text-center">
                  <p className="text-base font-bold uppercase tracking-wide text-[#F5F7FA]">
                    {getDisplayName(profile).toUpperCase()}
                  </p>
                  {profile.years_of_experience != null && (
                    <p className="mt-1 text-sm text-[#8A94A6]">
                      {profile.years_of_experience} лет стажа
                    </p>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

type ProfileDetailsTab = 'skills' | 'muscleLoad' | 'inventory'

function ProfileDetailsTabButton({
  active,
  onClick,
  children,
}: {
  active: boolean
  onClick: () => void
  children: ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex-1 border-b-2 px-4 py-2.5 text-sm font-medium transition-colors ${
        active ? 'border-accent-persimmon text-text-primary' : 'border-transparent text-[#8A94A6] hover:text-text-primary'
      }`}
    >
      {children}
    </button>
  )
}

// One modal replacing the old separate "Навыки" modal + inline "Нагрузка
// мышц" card + "Инвентарь" link-out -- three tabs instead, opened from
// three still-separate summary buttons under the profile card (each just
// picks which tab is active on open, same "quick links into one shared
// modal" shape as ExerciseDetailModal's own tab bar).
function ProfileDetailsModal({
  initialTab,
  unlockedSkills,
  lockedSkills,
  preferredSkillIds,
  onSelectSkill,
  muscleLoads,
  hasGymAccess,
  ownedItems,
  equipmentRequirements,
  onToggleEquipmentItem,
  inventoryToggleError,
  onClose,
}: {
  initialTab: ProfileDetailsTab
  unlockedSkills: SkillSummaryRead[]
  lockedSkills: SkillSummaryRead[]
  preferredSkillIds: Set<string>
  onSelectSkill: (skillId: string) => void
  muscleLoads: MuscleLoadRead[]
  hasGymAccess: boolean
  ownedItems: Set<EquipmentItem>
  equipmentRequirements: ExerciseEquipmentRequirement[]
  onToggleEquipmentItem: (item: EquipmentItem) => void
  inventoryToggleError: string | null
  onClose: () => void
}) {
  const [activeTab, setActiveTab] = useState<ProfileDetailsTab>(initialTab)
  const [selectedItem, setSelectedItem] = useState<EquipmentItem | null>(null)

  return (
    <Modal title="Профиль" onClose={onClose}>
      <div className="flex flex-col gap-4">
        <div className="-mx-6 -mt-6 flex border-b border-white/5 bg-dark-card">
          <ProfileDetailsTabButton active={activeTab === 'skills'} onClick={() => setActiveTab('skills')}>
            Навыки
          </ProfileDetailsTabButton>
          <ProfileDetailsTabButton
            active={activeTab === 'muscleLoad'}
            onClick={() => setActiveTab('muscleLoad')}
          >
            Нагрузка
          </ProfileDetailsTabButton>
          <ProfileDetailsTabButton
            active={activeTab === 'inventory'}
            onClick={() => setActiveTab('inventory')}
          >
            Инвентарь
          </ProfileDetailsTabButton>
        </div>

        {activeTab === 'skills' && (
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
                  gated by level -- not clickable (there's no reachable
                  progress detail to show yet), just a preview of what's
                  still ahead. */}
              {lockedSkills.map((skill) => (
                <LockedSkillChip key={skill.id} label={skill.name} requiredLevel={skill.required_level} />
              ))}
            </div>
          </div>
        )}

        {activeTab === 'muscleLoad' && <MuscleLoadChart loads={muscleLoads} />}

        {activeTab === 'inventory' && (
          <div className="flex flex-col gap-4">
            {hasGymAccess ? (
              <p className="text-sm text-[#8A94A6]">
                Есть доступ в тренажёрный зал — открыты все упражнения, весь инвентарь ниже
                неважен.
              </p>
            ) : (
              <>
                <p className="text-sm text-[#8A94A6]">Нажмите на предмет, чтобы посмотреть подробности.</p>
                <div className="grid grid-cols-5 gap-2">
                  {EQUIPMENT_ITEMS.map((item) => {
                    const owned = ownedItems.has(item)
                    const isSelected = selectedItem === item
                    return (
                      <button
                        key={item}
                        type="button"
                        onClick={() => setSelectedItem(item)}
                        title={EQUIPMENT_ITEM_LABELS[item]}
                        className={`flex flex-col items-center justify-center rounded-md border p-2.5 transition-colors ${
                          isSelected
                            ? 'border-accent-ice bg-accent-ice/10'
                            : owned
                              ? 'border-accent-ice/40 hover:border-accent-ice/60'
                              : 'border-white/10 opacity-50 hover:opacity-80'
                        }`}
                      >
                        <i
                          className={`ti ${EQUIPMENT_ICONS[item]} text-2xl ${owned ? 'text-accent-ice' : 'text-[#8A94A6]'}`}
                          aria-hidden="true"
                        />
                      </button>
                    )
                  })}
                </div>

                {selectedItem !== null && (
                  <div className="flex flex-col gap-2 rounded-md border border-white/10 bg-white/5 p-3">
                    <div className="flex items-center justify-between gap-2">
                      <p className="font-medium text-[#F5F7FA]">
                        {EQUIPMENT_ITEM_LABELS[selectedItem]}
                      </p>
                      <span
                        className={`shrink-0 text-xs font-medium ${
                          ownedItems.has(selectedItem) ? 'text-accent-ice' : 'text-[#8A94A6]'
                        }`}
                      >
                        {ownedItems.has(selectedItem) ? 'Есть' : 'Нет'}
                      </span>
                    </div>
                    <p className="text-sm text-[#8A94A6]">
                      {EQUIPMENT_ITEM_DESCRIPTIONS[selectedItem]}
                    </p>
                    <p className="text-xs text-[#8A94A6]">
                      Упражнений с этим предметом: {countExercisesUsingItem(equipmentRequirements, selectedItem)}
                    </p>
                    <Button
                      type="button"
                      variant="neutral"
                      onClick={() => onToggleEquipmentItem(selectedItem)}
                      className="self-start !px-3 !py-1.5 !text-xs"
                    >
                      {ownedItems.has(selectedItem) ? 'Убрать из инвентаря' : 'Добавить в инвентарь'}
                    </Button>
                  </div>
                )}

                <FormError message={inventoryToggleError} />

                <p className="text-sm text-[#8A94A6]">
                  Доступно {countAvailableExercises(equipmentRequirements, hasGymAccess, ownedItems)} из{' '}
                  {equipmentRequirements.length} упражнений.
                </p>
              </>
            )}
            <Link
              to="/settings"
              onClick={onClose}
              className="self-start text-sm text-accent-ice hover:underline"
            >
              Настроить зал в настройках
            </Link>
          </div>
        )}
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
