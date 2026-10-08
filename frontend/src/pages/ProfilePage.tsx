import { useEffect, useRef, useState } from 'react'
import { HelpButton } from '../components/HelpButton'
import type { ChangeEvent } from 'react'
import { Link, useParams } from 'react-router-dom'
import { BackLink } from '../components/ui/BackLink'
import { Button } from '../components/ui/Button'
import { CARD_BORDER } from '../components/ui/cardStyle'
import { FormError } from '../components/ui/FormError'
import { IceGlowBackground } from '../components/ui/IceGlowBackground'
import { LevelUnlocksModal } from '../components/ui/LevelUnlocksModal'
import { Modal } from '../components/ui/Modal'
import { AvatarCropModal } from '../components/AvatarCropModal'
import { PlayerCard } from '../components/PlayerCard'
import { cardStatsFrom, overallRatingOf } from '../components/playerCardStats'
import { cardStyleFor, getPlayerCardLook } from '../components/playerCardLook'
import { ShareCardModal } from '../components/ShareCardModal'
import * as authApi from '../api/auth'
import * as exercisesApi from '../api/exercises'
import * as progressApi from '../api/progress'
import * as restrictionsApi from '../api/userTemporaryRestrictions'
import * as skillsApi from '../api/skills'
import * as teamsApi from '../api/teams'
import * as usersApi from '../api/users'
import { API_BASE_URL, ApiError } from '../api/client'
import { useAuth } from '../hooks/useAuth'
import { useCoachmarkStep } from '../hooks/useCoachmarkStep'
import { TARGET_STAT_DESCRIPTIONS, TARGET_STAT_LABELS } from '../types/exercise'
import type { EquipmentItem, ExerciseEquipmentRequirement, TargetStat } from '../types/exercise'
import type { UserStatRead } from '../types/progress'
import type { SkillSummaryRead } from '../types/skill'
import type { UserTemporaryRestrictionRead } from '../types/userTemporaryRestriction'
import type { UserPublicRead } from '../types/user'
import { renderCardImage } from '../utils/cardImage'
import { countAvailableExercises } from '../utils/equipmentAvailability'
import { ProfileSkeleton } from '../components/ui/Skeleton'

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
  const [isLoading, setIsLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)

  const [selectedStatType, setSelectedStatType] = useState<TargetStat | null>(null)

  const statGridCoachmarkRef = useCoachmarkStep(
    'profile-stat-unlocks',
    'Новые упражнения открываются по мере роста характеристик выше — прокачивайте их тренировками, чтобы получить доступ к более сложным вариантам.',
    'ti-lock-open',
  )

  const avatarInputRef = useRef<HTMLInputElement>(null)
  const cardRef = useRef<HTMLDivElement>(null)
  const [isSharing, setIsSharing] = useState(false)
  const [shareError, setShareError] = useState<string | null>(null)
  const [sharedCardImage, setSharedCardImage] = useState<Blob | null>(null)
  const [isUploadingAvatar, setIsUploadingAvatar] = useState(false)
  const [avatarError, setAvatarError] = useState<string | null>(null)
  const [isAvatarPreviewOpen, setIsAvatarPreviewOpen] = useState(false)
  const [pendingAvatarFile, setPendingAvatarFile] = useState<File | null>(null)

  const [isResendingVerification, setIsResendingVerification] = useState(false)
  const [levelModalOpen, setLevelModalOpen] = useState(false)
  const [verificationResendResult, setVerificationResendResult] = useState<string | null>(null)
  const [verificationResendError, setVerificationResendError] = useState<string | null>(null)

  // Stage 2.3: inventory showcase card below -- purely a summary of data
  // already editable in Settings, so best-effort like the rest of this
  // page's optional widgets rather than blocking isLoading on its own.
  const [ownedItems, setOwnedItems] = useState<Set<EquipmentItem> | null>(null)
  const [equipmentRequirements, setEquipmentRequirements] = useState<ExerciseEquipmentRequirement[] | null>(null)

  // Active restrictions -- the count shows on the "Ограничения" row.
  const [restrictions, setRestrictions] = useState<UserTemporaryRestrictionRead[] | null>(null)

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

  // The player card's team emblem -- the first team's logo, best-effort.
  const [teamLogoUrl, setTeamLogoUrl] = useState<string | null>(null)

  useEffect(() => {
    if (accessToken === null) {
      return
    }
    let cancelled = false
    teamsApi
      .listMyTeams(accessToken)
      .then((teams) => {
        const logo = teams[0]?.logo_url ?? null
        if (!cancelled && logo !== null) {
          setTeamLogoUrl(`${API_BASE_URL}${logo}`)
        }
      })
      .catch(() => {
        // Best-effort -- the card falls back to a plain shield.
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
    restrictionsApi
      .listActiveRestrictions(accessToken)
      .then((result) => {
        if (!cancelled) {
          setRestrictions(result)
        }
      })
      .catch(() => {
        // Best-effort -- the chart just renders with nothing marked restricted.
      })
    return () => {
      cancelled = true
    }
  }, [accessToken])

  // Renders the card as a picture and opens ShareCardModal with it -- the
  // share sheet itself is opened from there, on a fresh tap (see the modal).
  async function handleShareCard() {
    if (cardRef.current === null) {
      return
    }
    setShareError(null)
    setIsSharing(true)
    try {
      const frame = cardRef.current.querySelector<HTMLElement>('[data-card="frame"]')
      if (frame === null) {
        throw new Error('card not found')
      }
      setSharedCardImage(
        await renderCardImage(frame, getPlayerCardLook(cardStyleFor(user?.level ?? 1, user?.avatar_ring_accent))),
      )
    } catch (err) {
      // The error's name goes on screen: there's no console to look at on a phone.
      setShareError(
        `Не удалось подготовить карточку (${err instanceof Error ? `${err.name}: ${err.message}` : String(err)}). Попробуйте ещё раз.`,
      )
    } finally {
      setIsSharing(false)
    }
  }

  // A picked photo goes through the framing step first (AvatarCropModal).
  function handleAvatarChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    // Reset so selecting the same file again still fires onChange.
    event.target.value = ''
    if (file !== undefined) {
      setAvatarError(null)
      setPendingAvatarFile(file)
    }
  }

  async function uploadAvatarFile(file: File) {
    setPendingAvatarFile(null)
    if (accessToken === null) {
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
  const overallRating = overallRatingOf(stats ?? [])
  const selectedStat = selectedStatType !== null ? statsByType.get(selectedStatType) : undefined

  const ageExperienceParts = [
    user?.age != null ? `${user.age} лет` : null,
    user?.years_of_experience != null ? `${user.years_of_experience} лет стажа` : null,
  ].filter((part): part is string => part !== null)
  const avatarUrl = user?.avatar_url != null ? `${API_BASE_URL}${user.avatar_url}` : null

  const cardStats = cardStatsFrom(stats ?? [])
  const cardSubtitle = [user?.first_name ?? null, ...ageExperienceParts].filter(Boolean).join(' · ')
  const nearMilestoneCount =
    skills?.filter(
      (skill) =>
        skill.required_level <= (user?.level ?? 1) && (skill.next_milestone?.points_remaining ?? Infinity) <= 5,
    ).length ?? 0

  return (
    <div className="relative min-h-svh overflow-hidden">
      <IceGlowBackground />
      <div className="relative z-[1] mx-auto flex max-w-2xl flex-col gap-3 px-4 py-5">
      <div className="flex items-center justify-between">
        <h1 className="flex-1 text-xl font-semibold">Профиль</h1>
        <HelpButton topic="profile" />
        <button
          type="button"
          onClick={handleShareCard}
          disabled={isSharing || stats === null}
          aria-label="Поделиться карточкой"
          className="flex h-11 w-11 items-center justify-center text-[#8A94A6] transition-colors hover:text-[#F5F7FA] disabled:opacity-50"
        >
          <i className={`ti ${isSharing ? 'ti-loader-2 animate-spin' : 'ti-share'} text-xl`} aria-hidden="true" />
        </button>
        <Link
          to="/settings"
          aria-label="Настройки"
          className="flex h-11 w-11 items-center justify-center text-[#8A94A6] transition-colors hover:text-[#F5F7FA]"
        >
          <i className="ti ti-settings text-xl" aria-hidden="true" />
        </Link>
      </div>

      <FormError message={loadError} />
      {isLoading && <ProfileSkeleton />}

      {!isLoading && stats !== null && (
        <div className="mx-auto flex w-full max-w-[360px] flex-col gap-3">
          <div ref={cardRef}>
          <PlayerCard
            cardStyle={cardStyleFor(user?.level ?? 1, user?.avatar_ring_accent)}
            premium={user?.has_premium === true}
            jerseyColor={user?.jersey_color ?? null}
            rating={overallRating}
            position={user?.position ?? null}
            jerseyNumber={user?.jersey_number ?? null}
            surname={user?.last_name || user?.first_name || ''}
            subtitle={cardSubtitle}
            level={user?.level ?? 1}
            xp={user?.xp ?? 0}
            avatarUrl={avatarUrl}
            teamLogoUrl={teamLogoUrl}
            stats={cardStats}
            isUploadingAvatar={isUploadingAvatar}
            statGridRef={statGridCoachmarkRef}
            onAvatarClick={() => {
              if (avatarUrl !== null) {
                setIsAvatarPreviewOpen(true)
              } else {
                avatarInputRef.current?.click()
              }
            }}
            onChangePhoto={() => avatarInputRef.current?.click()}
            onLevelClick={() => setLevelModalOpen(true)}
            onStatClick={setSelectedStatType}
          />
          </div>
          <FormError message={shareError} />
          <input ref={avatarInputRef} type="file" accept="image/*" className="hidden" onChange={handleAvatarChange} />
          <FormError message={avatarError} />
        </div>
      )}

      <div className="grid grid-cols-2 gap-2">
        <ProfileTile
          icon="ti-target"
          label="Навыки"
          hint={nearMilestoneCount > 0 ? `${nearMilestoneCount} почти у порога` : 'Пороги и вклад в статы'}
          to="/skills"
        />
        <ProfileTile
          icon="ti-chart-line"
          label="Аналитика"
          hint="Рекорды, регулярность"
          to="/analytics"
          pro={user?.has_premium !== true}
        />
        <ProfileTile
          icon="ti-flame"
          label="Нагрузка"
          hint="Мышцы за последние дни"
          to="/muscle-load"
        />
        <ProfileTile
          icon="ti-backpack"
          label="Инвентарь"
          hint={
            ownedItems !== null && equipmentRequirements !== null
              ? `Доступно ${countAvailableExercises(equipmentRequirements, user?.has_gym_access ?? false, ownedItems)} упражн.`
              : 'Что есть для тренировок'
          }
          to="/inventory"
        />
      </div>

      <div className={`flex flex-col rounded-md ${CARD_BORDER} bg-dark-card`}>
        <ProfileRow
          icon="ti-crown"
          label="Премиум"
          hint={user?.has_premium === true ? 'Активен' : 'Тренер, разбор недели, аналитика'}
          to="/premium"
        />
        <ProfileRow icon="ti-notebook" label="Дневник" hint="Записи после льда и игр" to="/diary" />
        <ProfileRow icon="ti-trophy" label="Сезон" hint="Игры, голы, передачи" to="/season" />
        <ProfileRow
          icon="ti-bandage"
          label="Ограничения"
          hint={
            restrictions !== null && restrictions.length > 0
              ? `Сейчас ограничено: ${restrictions.length}`
              : 'Что болит, чтобы не предлагать эти упражнения'
          }
          to="/restrictions"
        />
        <ProfileRow icon="ti-book" label="Справочник" hint="Статьи об экипировке и основах" to="/reference" />
        <ProfileRow icon="ti-clipboard-list" label="Каталог упражнений" hint="Все упражнения с техникой" to="/exercise-catalog" />
        <ProfileRow icon="ti-message-report" label="Обратная связь" hint="Нашёл ошибку или есть идея — напиши" to="/feedback" />
      </div>
      {!isLoading && user !== null && !user.email_verified && (
        <div className={`flex flex-col gap-1.5 rounded-md ${CARD_BORDER} bg-dark-card p-3`}>
          <div className="flex items-center gap-2">
            <i className="ti ti-mail-exclamation text-base text-accent-persimmon" aria-hidden="true" />
            <span className="text-xs font-medium text-[#F5F7FA]">Email не подтверждён</span>
          </div>
          {verificationResendResult === null ? (
            <>
              <p className="text-xs text-[#8A94A6]">
                Проверьте почту {user.email} и перейдите по ссылке из письма.
              </p>
              <Button
                type="button"
                variant="neutral"
                isLoading={isResendingVerification}
                onClick={handleResendVerification}
                className="self-start !px-3 !py-1 !text-xs"
              >
                Отправить письмо ещё раз
              </Button>
              <FormError message={verificationResendError} />
            </>
          ) : (
            <p className="text-xs text-accent-ice">{verificationResendResult}</p>
          )}
        </div>
      )}

      {selectedStatType !== null && selectedStat !== undefined && (
        <StatDetailModal
          statType={selectedStatType}
          stat={selectedStat}
          onClose={() => setSelectedStatType(null)}
        />
      )}

      {sharedCardImage !== null && (
        <ShareCardModal image={sharedCardImage} onClose={() => setSharedCardImage(null)} />
      )}

      {pendingAvatarFile !== null && (
        <AvatarCropModal
          file={pendingAvatarFile}
          onCancel={() => setPendingAvatarFile(null)}
          onConfirm={(cropped) => void uploadAvatarFile(cropped)}
          onUnreadable={(original) => void uploadAvatarFile(original)}
        />
      )}

      {isAvatarPreviewOpen && avatarUrl !== null && (
        <Modal title="Фото профиля" onClose={() => setIsAvatarPreviewOpen(false)}>
          <img src={avatarUrl} alt="Аватар" className="w-full rounded" />
        </Modal>
      )}

      {levelModalOpen && (
        <LevelUnlocksModal level={user?.level ?? 1} onClose={() => setLevelModalOpen(false)} />
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

  const avatarUrl = profile?.avatar_url != null ? `${API_BASE_URL}${profile.avatar_url}` : null
  const cardStats = cardStatsFrom(profile?.stats ?? [])
  const overallRating = overallRatingOf(profile?.stats ?? [])
  const subtitle = [
    profile?.first_name ?? null,
    profile?.years_of_experience != null ? `${profile.years_of_experience} лет стажа` : null,
  ]
    .filter(Boolean)
    .join(' · ')

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

        {/* The same player card the owner sees, read-only -- friends and
            teammates compare cards, which is half the point of having one. */}
        {profile !== null && (
          <div className="mx-auto w-full max-w-[360px]">
            <PlayerCard
              cardStyle={cardStyleFor(profile.level, profile.avatar_ring_accent)}
              premium={profile.has_premium}
              jerseyColor={profile.jersey_color}
              rating={overallRating}
              position={profile.position}
              jerseyNumber={profile.jersey_number}
              surname={profile.last_name || profile.first_name}
              subtitle={subtitle}
              level={profile.level}
              xp={profile.xp}
              avatarUrl={avatarUrl}
              teamLogoUrl={null}
              stats={cardStats}
            />
          </div>
        )}
      </div>
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
        <p className="text-sm text-[#8A94A6]">{TARGET_STAT_DESCRIPTIONS[statType]}</p>
        <div>
          {/* Matches HomePage's own StatDetailModal: a large "hero" number
              in a modal reads as primary text, not the ice accent -- ice is
              reserved for compact numbers in card grids (see the 4-tile
              row above). */}
          <p className="font-display text-3xl font-bold leading-none text-[#F5F7FA]">
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

function ProfileTile({
  icon,
  label,
  hint,
  to,
  onClick,
  pro = false,
}: {
  icon: string
  label: string
  hint: string
  to?: string
  onClick?: () => void
  pro?: boolean
}) {
  const body = (
    <>
      <span className="flex items-center justify-between">
        <i className={`ti ${icon} text-xl text-accent-ice`} aria-hidden="true" />
        {pro && (
          <span className="rounded bg-gradient-to-r from-accent-ice to-accent-persimmon px-1.5 font-display text-[10px] tracking-wider text-dark-bg">
            PRO
          </span>
        )}
      </span>
      <span className="flex flex-col gap-0.5">
        <span className="text-sm font-medium text-[#F5F7FA]">{label}</span>
        <span className="truncate text-xs text-[#8A94A6]">{hint}</span>
      </span>
    </>
  )
  const className = `flex flex-col gap-2 rounded-md ${CARD_BORDER} bg-dark-card p-3 text-left transition-colors hover:bg-white/5`
  if (to !== undefined) {
    return (
      <Link to={to} className={className}>
        {body}
      </Link>
    )
  }
  return (
    <button type="button" onClick={onClick} className={className}>
      {body}
    </button>
  )
}

function ProfileRow({ icon, label, hint, to }: { icon: string; label: string; hint: string; to: string }) {
  return (
    <Link
      to={to}
      className="group flex min-h-14 items-center gap-3 border-b border-white/5 px-3.5 py-3 last:border-b-0 transition-colors hover:bg-white/5"
    >
      <i className={`ti ${icon} text-lg text-accent-ice`} aria-hidden="true" />
      <span className="flex min-w-0 flex-1 flex-col gap-0.5">
        <span className="text-sm text-[#F5F7FA]">{label}</span>
        <span className="truncate text-xs text-[#8A94A6]">{hint}</span>
      </span>
      <i className="ti ti-chevron-right text-lg text-[#8A94A6] transition-all group-hover:translate-x-0.5" aria-hidden="true" />
    </Link>
  )
}
