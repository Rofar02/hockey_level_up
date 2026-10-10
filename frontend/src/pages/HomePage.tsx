import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { OnboardingTour } from '../components/OnboardingTour'
import { SkillDetailModal } from '../components/SkillDetailModal'
import { WeeklyReviewCard } from '../components/WeeklyReviewCard'
import { CoachPlanReminderCard } from '../components/teamEvents/CoachPlanReminderCard'
import { TeamDayCard } from '../components/teamEvents/TeamDayCard'
import { IceFocusCard } from '../components/IceFocusCard'
import { OnboardingCard } from '../components/OnboardingCard'
import { Button } from '../components/ui/Button'
import { CardGlow } from '../components/ui/CardGlow'
import { CARD_BORDER, CARD_CLASS } from '../components/ui/cardStyle'
import { FaceoffProgressRing } from '../components/ui/FaceoffProgressRing'
import { FormError } from '../components/ui/FormError'
import { IceGlowBackground } from '../components/ui/IceGlowBackground'
import { LevelUnlocksModal } from '../components/ui/LevelUnlocksModal'
import { Modal } from '../components/ui/Modal'
import { ProgressBar } from '../components/ui/ProgressBar'
import { XpBar } from '../components/ui/XpBar'
import { API_BASE_URL, ApiError } from '../api/client'
import * as questsApi from '../api/quests'
import * as progressApi from '../api/progress'
import * as scheduleApi from '../api/schedule'
import * as skillsApi from '../api/skills'
import * as trainingBlockApi from '../api/trainingBlock'
import * as usersApi from '../api/users'
import { useAuth } from '../hooks/useAuth'
import { useCoachmarkStep } from '../hooks/useCoachmarkStep'
import { useSuppressCoachmarks } from '../hooks/useSuppressCoachmarks'
import { TARGET_STAT_DESCRIPTIONS, TARGET_STAT_LABELS } from '../types/exercise'
import type { ExerciseRead, TargetStat } from '../types/exercise'
import type { QuestStatusRead } from '../types/quest'
import type { ActivityCalendarDayRead, TrainingStreakRead, UserStatRead } from '../types/progress'
import { DAY_SESSION_TYPE_LABELS, SESSION_TYPE_COLORS, SESSION_TYPE_ICONS } from '../types/schedule'
import type {
  DayPlanRead,
  DaySessionType,
  SessionBlockRead,
  TrainingPhase,
  TrainingSessionRead,
  WeeklyPlanRead,
} from '../types/schedule'
import type { SkillDetailRead, SkillSummaryRead } from '../types/skill'
import { BLOCK_PHASE_LABELS } from '../types/trainingBlock'
import type { BlockPhase, TrainingBlockRead } from '../types/trainingBlock'
import { POSITION_LABELS } from '../types/user'
import { getAvatarTierStyle } from '../utils/avatarTier'
import { getDisplayName } from '../utils/displayName'
import { WEEKDAY_LABELS, addDays, formatShortDate, getMondayOfCurrentWeek, parseIsoDate, toIsoDate } from '../utils/date'
import { loadOptional } from '../utils/loadOptional'
import { HomeSkeleton } from '../components/ui/Skeleton'

const MONTH_LABELS = [
  'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
  'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь',
]

// Reviewed copy (2026-09-15) -- also mirrored, at greater length, in the
// "Зачем нужны фазы тренировочного блока" reference article (seeded via
// scripts/seed_reference_articles.py), which PeriodizationCard's info panel
// links out to. Grounded in the real mechanics from app/core/training_block.py
// (intensification biases toward difficulty>=4, deload biases toward
// difficulty<=2 and shrinks the main block to 1-2 exercises). Phrased around
// "фаза" rather than "неделя" since Phase 4 made phase length
// session-count-driven, not a fixed calendar week.
const BLOCK_PHASE_DESCRIPTIONS: Record<BlockPhase, string> = {
  accumulation:
    'Базовый этап блока: набираем общий объём тренировок без резких скачков сложности.',
  intensification:
    'Сложность упражнений заметно растёт — это самая требовательная фаза блока. Следите за техникой.',
  deload:
    'Разгрузочная фаза перед новым блоком: упражнения проще, а нагрузки в основной части меньше. Время на восстановление.',
}

// Rest-day hint on TodayCard: during intensification (the highest-load
// phase, see BLOCK_PHASE_DESCRIPTIONS above) light movement speeds recovery
// more than full inactivity, so that phase gets a more specific nudge.
// Accumulation/deload phases, or no active block at all, get the same
// simple text -- no phase-specific tuning needed there.
function getRestDayHint(phase: BlockPhase | null): string {
  if (phase === 'intensification') {
    return 'День отдыха. Лёгкая прогулка 20-30 минут поможет мышцам быстрее восстановиться после высокой нагрузки в этой фазе.'
  }
  return 'День отдыха. Дайте телу восстановиться.'
}

// Read CARD_CLASS as the rink's blue line -- neutral/progress content
// defaults to it. (Tried a bolder border-t-2/0.5 as a 2026-08-28
// experiment -- reverted, the thin line was the right call.)
// Same card, red top line instead -- the rink's other line, reserved for
// content that's a status/urgency call rather than routine progress (hockey
// design pass, 2026-08-28). Only TournamentTaperBanner uses this today.
const CARD_CLASS_URGENT = 'rounded-md border-t border-accent-persimmon/50 bg-dark-card'

function startOfMonth(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), 1)
}

function addMonths(date: Date, months: number): Date {
  return new Date(date.getFullYear(), date.getMonth() + months, 1)
}

// Monday-start grid padded with nulls to a full number of weeks.
function buildMonthGrid(monthStart: Date): (Date | null)[] {
  const daysInMonth = new Date(monthStart.getFullYear(), monthStart.getMonth() + 1, 0).getDate()
  const leadingBlanks = (monthStart.getDay() + 6) % 7
  const cells: (Date | null)[] = []
  for (let i = 0; i < leadingBlanks; i++) {
    cells.push(null)
  }
  for (let day = 1; day <= daysInMonth; day++) {
    cells.push(new Date(monthStart.getFullYear(), monthStart.getMonth(), day))
  }
  while (cells.length % 7 !== 0) {
    cells.push(null)
  }
  return cells
}

function isSessionDayCompleted(day: DayPlanRead): boolean {
  const blocks = day.training_session?.blocks
  return (
    blocks !== undefined &&
    blocks.length > 0 &&
    blocks.every((block) => block.completed_at !== null || block.skipped_at !== null)
  )
}

// Same fixed workout-flow order, labels and icons as NewSchedulePage/
// TrainingSessionPage's own page-local copies (that pair's own comments
// call out the duplication convention this follows) -- DayDetailModal's
// history view groups by phase the same way both of those already do, so a
// past day reads the same whether you're looking at it live or looking back.
const PHASE_SEQUENCE: TrainingPhase[] = ['warmup', 'main', 'cooldown', 'puck']

const PHASE_LABELS: Record<TrainingPhase, string> = {
  warmup: 'Разминка',
  main: 'Основная часть',
  cooldown: 'Заминка',
  puck: 'Владение шайбой',
}

const PHASE_ICONS: Record<TrainingPhase, string> = {
  warmup: 'ti-flame',
  main: 'ti-barbell',
  cooldown: 'ti-wind',
  puck: 'ti-disc',
}

function formatTargetVolume(exercise: ExerciseRead): string | null {
  if (exercise.target_sets !== null && exercise.rep_range_min !== null && exercise.rep_range_max !== null) {
    return `${exercise.target_sets} × ${exercise.rep_range_min}-${exercise.rep_range_max}`
  }
  if (exercise.target_duration_seconds !== null) {
    return `${exercise.target_duration_seconds} сек`
  }
  return null
}

// At least one exercise ticked but not every one -- "Начать тренировку" reads
// as a lie once the player has already been in the session (found
// 2026-08-27: reopening TodayCard after checking off a few exercises still
// offered to "start" it from scratch instead of picking back up where they
// left off).
function isSessionDayStarted(day: DayPlanRead): boolean {
  const blocks = day.training_session?.blocks
  return blocks !== undefined && blocks.some((block) => block.completed_at !== null || block.skipped_at !== null)
}

// Backed by GET /users/me/activity-calendar (2026-08-19) -- real
// per-day completion history for whatever month is currently loaded,
// not just the current week's WeeklyPlanRead plus a single
// TrainingStreak.last_activity_date guess for every other day.
function hasKnownActivity(iso: string, calendarData: Record<string, ActivityCalendarDayRead>): boolean {
  return calendarData[iso]?.fully_completed === true
}

function topSkillsNearMilestone(skills: SkillSummaryRead[]): SkillSummaryRead[] {
  return skills
    .filter((skill) => skill.next_milestone !== null)
    .sort((a, b) => a.next_milestone!.points_remaining - b.next_milestone!.points_remaining)
    .slice(0, 3)
}

export function HomePage() {
  const { user, accessToken, updateUser } = useAuth()
  const navigate = useNavigate()

  // Local, session-only guard on top of user.has_seen_onboarding_tour --
  // set the instant the tour closes, regardless of whether the
  // persist-to-server call below succeeds, so a dropped request never
  // strands the user behind the tour; worst case it just shows again next
  // launch.
  const [tourDismissed, setTourDismissed] = useState(false)

  const [trainingBlock, setTrainingBlock] = useState<TrainingBlockRead | null>(null)
  const [weeklyPlan, setWeeklyPlan] = useState<WeeklyPlanRead | null>(null)
  const [streak, setStreak] = useState<TrainingStreakRead | null>(null)
  const [stats, setStats] = useState<UserStatRead[] | null>(null)
  const [skills, setSkills] = useState<SkillSummaryRead[] | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [calendarExpanded, setCalendarExpanded] = useState(false)
  const [calendarMonth, setCalendarMonth] = useState(() => startOfMonth(new Date()))
  const [levelModalOpen, setLevelModalOpen] = useState(false)
  const [calendarData, setCalendarData] = useState<Record<string, ActivityCalendarDayRead>>({})
  const [selectedDay, setSelectedDay] = useState<Date | null>(null)
  // Lazily fetched fallback for a day the calendar shows activity for but
  // that isn't inside the currently-loaded WeeklyPlan (any day outside the
  // current week -- last week, further back, or next week before it's
  // loaded) -- see the effect below and GET /schedule/day-plan. Keyed by
  // isoDate (not just the plan) so a stale result from a previously-
  // selected day is never shown for a new one while its own fetch is still
  // in flight.
  const [fetchedDayPlan, setFetchedDayPlan] = useState<{ isoDate: string; plan: DayPlanRead | null } | null>(
    null,
  )

  const [selectedStatType, setSelectedStatType] = useState<TargetStat | null>(null)

  const [selectedSkillId, setSelectedSkillId] = useState<string | null>(null)
  const [skillDetails, setSkillDetails] = useState<Record<string, SkillDetailRead>>({})
  const [loadingSkillDetailId, setLoadingSkillDetailId] = useState<string | null>(null)
  const [skillDetailError, setSkillDetailError] = useState<string | null>(null)

  useEffect(() => {
    if (accessToken === null) {
      return
    }
    let cancelled = false
    Promise.all([
      loadOptional(trainingBlockApi.getCurrentTrainingBlock(accessToken)),
      loadOptional(scheduleApi.getCurrentWeeklyPlan(accessToken)),
      progressApi.getMyStreak(accessToken),
      progressApi.getMyStats(accessToken),
      skillsApi.listSkills(accessToken),
    ])
      .then(([block, plan, streakResult, statsResult, skillsResult]) => {
        if (cancelled) {
          return
        }
        setTrainingBlock(block)
        setWeeklyPlan(plan)
        setStreak(streakResult)
        setStats(statsResult)
        setSkills(skillsResult)
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : 'Не удалось загрузить дашборд.')
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

  // Only fetched once the panel is actually open (not on every dashboard
  // load) and refetched whenever the visible month changes -- one request
  // per month, not one per day like a naive per-cell fetch would be.
  useEffect(() => {
    if (accessToken === null || !calendarExpanded) {
      return
    }
    let cancelled = false
    progressApi
      .getMyActivityCalendar(toIsoDate(calendarMonth), accessToken)
      .then((days) => {
        if (cancelled) {
          return
        }
        const byDate: Record<string, ActivityCalendarDayRead> = {}
        for (const day of days) {
          byDate[day.date] = day
        }
        setCalendarData(byDate)
      })
      .catch(() => {
        // Best-effort -- a failed fetch just leaves this month's cells
        // unhighlighted rather than taking down the rest of the dashboard.
      })
    return () => {
      cancelled = true
    }
  }, [accessToken, calendarExpanded, calendarMonth])

  // A day tapped in the calendar is usually inside weeklyPlan already (this
  // week) and needs no fetch at all -- this only runs for a day outside it
  // (see DayDetailModal, which used to just say "детали недоступны" for
  // exactly this case). loadOptional/404 covers a date with no DayPlan at
  // all (a future day nothing's been generated for).
  useEffect(() => {
    if (accessToken === null || selectedDay === null) {
      return
    }
    const isoDate = toIsoDate(selectedDay)
    if (weeklyPlan?.day_plans.some((day) => day.date === isoDate) === true) {
      return
    }
    let cancelled = false
    loadOptional(scheduleApi.getDayPlan(isoDate, accessToken)).then((plan) => {
      if (!cancelled) {
        setFetchedDayPlan({ isoDate, plan })
      }
    })
    return () => {
      cancelled = true
    }
  }, [accessToken, selectedDay, weeklyPlan])

  async function openSkillModal(skillId: string) {
    setSelectedSkillId(skillId)
    if (skillDetails[skillId] !== undefined || accessToken === null) {
      return
    }
    setSkillDetailError(null)
    setLoadingSkillDetailId(skillId)
    try {
      const detail = await skillsApi.getSkillDetail(skillId, accessToken)
      setSkillDetails((previous) => ({ ...previous, [skillId]: detail }))
    } catch (err) {
      setSkillDetailError(err instanceof ApiError ? err.message : 'Не удалось загрузить детали навыка.')
    } finally {
      setLoadingSkillDetailId(null)
    }
  }

  async function persistTourSeen() {
    if (accessToken === null) {
      return
    }
    try {
      const updated = await usersApi.markOnboardingTourSeen(accessToken)
      updateUser(updated)
    } catch {
      // Best-effort -- tourDismissed below already lets this session
      // through; a failed persist just means the tour shows again next
      // launch instead of being gone for good.
    }
  }

  function handleTourSkip() {
    setTourDismissed(true)
    void persistTourSeen()
  }

  function handleTourComplete() {
    setTourDismissed(true)
    void persistTourSeen()
    // Straight into planning the first week -- an empty Home dashboard
    // ("Нет плана на сегодня") right after the tour is a dead end, not a
    // next step.
    navigate('/schedule/new')
  }

  const showTour = user !== null && !user.has_seen_onboarding_tour && !tourDismissed
  // The welcome tour covers the page but doesn't unmount it -- without this,
  // a coachmark registered by whatever's underneath (e.g. "Ближайшие
  // пороги") renders right on top of the tour instead of waiting for it to
  // close (found live, 2026-08-30, on a brand-new account's first visit).
  useSuppressCoachmarks(showTour)

  const todayIso = toIsoDate(new Date())
  const today = weeklyPlan?.day_plans.find((day) => day.date === todayIso && day.is_extra !== true) ?? null
  // Double day (step 6): today's separate gym training next to the ice/game.
  const todayExtra = weeklyPlan?.day_plans.find((day) => day.date === todayIso && day.is_extra === true) ?? null
  const avatarUrl = user?.avatar_url != null ? `${API_BASE_URL}${user.avatar_url}` : null
  const avatarTierStyle = getAvatarTierStyle(user?.level ?? 1, user?.avatar_ring_accent)
  const selectedIsoDate = selectedDay !== null ? toIsoDate(selectedDay) : null
  const selectedDayWeeklyPlanDay =
    selectedIsoDate !== null
      ? weeklyPlan?.day_plans.find((day) => day.date === selectedIsoDate && day.is_extra !== true)
      : undefined
  // fetchedDayPlan.plan is `null` for "fetched, no plan for that date" (a
  // real answer -- don't fall through to "still loading"), so only
  // `undefined` (nothing fetched yet, or for a different date) is coerced
  // away below; DayDetailModal tells the two apart via isLoadingPlan.
  const fetchedForSelectedDate =
    fetchedDayPlan?.isoDate === selectedIsoDate ? fetchedDayPlan.plan : undefined
  const selectedDayPlan = selectedDayWeeklyPlanDay ?? fetchedForSelectedDate ?? undefined
  const isLoadingSelectedDayPlan =
    selectedIsoDate !== null && selectedDayWeeklyPlanDay === undefined && fetchedForSelectedDate === undefined
  const selectedDayHasActivity =
    selectedDay !== null && hasKnownActivity(toIsoDate(selectedDay), calendarData)
  const selectedSkillName = skills?.find((skill) => skill.id === selectedSkillId)?.name ?? ''
  const selectedStat =
    selectedStatType !== null ? (stats?.find((stat) => stat.stat_type === selectedStatType) ?? null) : null

  // Every training of the day done (2026-10-10): the day closes into one
  // card with "как прошёл день" -- never "начать" again after the report.
  // A team day keeps its own TeamDayCard.
  const dayClosed =
    today !== null &&
    today.team_event_id === null &&
    today.training_session !== null &&
    isMainDayDone(today) &&
    (todayExtra === null || isSessionDayCompleted(todayExtra))

  return (
    <div className="relative min-h-svh overflow-hidden">
      <IceGlowBackground />
      {showTour && <OnboardingTour onSkip={handleTourSkip} onComplete={handleTourComplete} />}
      <div className="relative z-[1] mx-auto flex min-h-svh max-w-3xl flex-col gap-4 px-4 py-8">
        <div className={`flex flex-col gap-4 p-4 ${CARD_CLASS}`}>
          {/* Level sits under the name (identity info, left-aligned with
              it) instead of paired with the streak button on the right --
              the two read as unrelated facts (character level vs. a
              daily-activity counter), so pairing them as matched pills
              read as arbitrary rather than intentional.

              No flex-wrap here (tried it, wrong call -- the streak button
              would drop to a second row on a long name, which looks like
              something broke, not like a deliberate layout). Instead
              min-w-0 on both the left column and its name/position wrapper
              lets THAT column shrink and wrap its own text across two
              lines -- the streak button stays shrink-0 and pinned to this
              same row no matter how long the name is. */}
          <div className="flex items-center justify-between gap-4">
            <div className="flex min-w-0 items-center gap-4">
              {/* Two-layer wrapper: the outer div carries the level-tier
                  border/glow (box-shadow), the inner one clips the photo to a
                  circle. Both on the same element would clip the glow itself
                  -- overflow-hidden clips a box's own box-shadow, not just
                  its content. */}
              <div className="h-20 w-20 shrink-0 rounded-full" style={avatarTierStyle.style}>
                <div className="flex h-full w-full items-center justify-center overflow-hidden rounded-full bg-dark-bg">
                  {avatarUrl !== null ? (
                    <img src={avatarUrl} alt="" className="h-full w-full object-cover" />
                  ) : (
                    <i className="ti ti-user text-3xl text-[#8A94A6]" aria-hidden="true" />
                  )}
                </div>
              </div>
              <div className="flex min-w-0 flex-col gap-1">
                <span className="text-xl font-bold leading-tight text-[#F5F7FA]">
                  {user !== null ? getDisplayName(user) : ''}
                </span>
                <span className="text-sm text-[#8A94A6]">
                  {user?.position != null ? POSITION_LABELS[user.position] : ''}
                </span>
                {/* Same compact pill ProfilePage's own card uses for level
                    (px-2.5 py-0.5, text-[11px]) -- one style for "level
                    badge sitting under a name" wherever that pattern shows
                    up, not a one-off sized to match a neighboring button.
                    Tappable -- opens LevelUnlocksModal so a level number
                    isn't just an inert stat, matching the chevron
                    discoverability convention used elsewhere (2026-08-30). */}
                <button
                  type="button"
                  onClick={() => setLevelModalOpen(true)}
                  className="group mt-0.5 flex w-fit items-center gap-1 rounded-md border border-accent-ice/25 bg-accent-ice/[0.08] px-2.5 py-0.5 transition-colors hover:border-accent-ice/40"
                >
                  <span className="font-sans text-[9px] font-semibold uppercase tracking-wider text-accent-ice/70">
                    Ур.
                  </span>
                  <span className="font-display text-sm font-semibold leading-none text-accent-ice">
                    {user?.level ?? 1}
                  </span>
                  <i
                    className="ti ti-chevron-right text-xs text-accent-ice/50 transition-all group-hover:translate-x-0.5 group-hover:text-accent-ice"
                    aria-hidden="true"
                  />
                </button>
              </div>
            </div>

            {streak !== null && (
              <button
                type="button"
                onClick={() => setCalendarExpanded((value) => !value)}
                className="flex shrink-0 items-center justify-center gap-1.5 rounded-md border border-white/10 bg-dark-bg px-3 py-2 transition-colors hover:border-white/20"
              >
                <i className="ti ti-flame text-xs text-accent-persimmon" aria-hidden="true" />
                <span className="font-mono text-xs font-bold text-accent-persimmon">
                  {streak.current_streak}
                </span>
                <i
                  className={`ti ${calendarExpanded ? 'ti-chevron-up' : 'ti-chevron-down'} text-xs text-[#8A94A6]`}
                  aria-hidden="true"
                />
              </button>
            )}
          </div>

          <XpBar level={user?.level ?? 1} xp={user?.xp ?? 0} />
        </div>

        {calendarExpanded && (
          <CalendarPanel
            month={calendarMonth}
            onMonthChange={setCalendarMonth}
            calendarData={calendarData}
            onSelectDay={setSelectedDay}
          />
        )}

        <FormError message={error} />
        {isLoading && <HomeSkeleton />}

        {!isLoading && (
          <div className="flex flex-col gap-4">
            {/* New players: the main loop as a paid checklist, until done or
                hidden. */}
            <OnboardingCard />

            {/* Captains only, and only while a training this week has no
                published plan -- renders nothing otherwise. */}
            <CoachPlanReminderCard />

            {/* Premium: the coach's Monday review of last week, until closed. */}
            <WeeklyReviewCard />

            {dayClosed && today !== null ? (
              <DayClosedCard
                day={today}
                extra={todayExtra}
                onReport={() => navigate(`/day-report/${today.date}`)}
              />
            ) : (
            <>
            {todayExtra !== null && todayExtra.time_of_day === 'morning' && (
              <ExtraGymTodayCard day={todayExtra} onStart={() => navigate(`/training/${todayExtra.id}`)} />
            )}

            {(() => {
              const personalCard = (
                <TodayCard
                  day={today}
                  phaseLabel={trainingBlock !== null ? BLOCK_PHASE_LABELS[trainingBlock.phase] : null}
                  phase={trainingBlock !== null ? trainingBlock.phase : null}
                  onStart={() => today !== null && navigate(`/training/${today.id}`)}
                  onFillDiary={() => today !== null && navigate(`/training/${today.id}/diary`)}
                  onPlanWeek={() => navigate('/schedule/new')}
                />
              )
              if (today === null || today.team_event_id === null) {
                return personalCard
              }
              const weekday = WEEKDAY_LABELS[(parseIsoDate(today.date).getDay() + 6) % 7]
              return (
                <TeamDayCard
                  day={{ ...today, team_event_id: today.team_event_id }}
                  eyebrow={`${weekday} · Команда`}
                  onStartWarmup={() => navigate(`/training/${today.id}`)}
                  personalCard={personalCard}
                />
              )
            })()}

            {todayExtra !== null && todayExtra.time_of_day !== 'morning' && (
              <ExtraGymTodayCard day={todayExtra} onStart={() => navigate(`/training/${todayExtra.id}`)} />
            )}
            </>
            )}

            <NextWeekPlanCard onPlan={() => navigate('/schedule/new?week=next')} />

            <WeeklyQuestsCard onOpen={() => navigate('/quests')} />

            {skills !== null && (
              <SkillsNearMilestoneCard skills={skills} onSelectSkill={openSkillModal} />
            )}

            {trainingBlock !== null && <PeriodizationCard block={trainingBlock} />}

            {user !== null && <TournamentTaperBanner tournamentDate={user.tournament_date} />}

          </div>
        )}
      </div>

      {selectedDay !== null && (
        <DayDetailModal
          date={selectedDay}
          dayPlan={selectedDayPlan}
          isLoadingPlan={isLoadingSelectedDayPlan}
          hasKnownActivity={selectedDayHasActivity}
          onClose={() => setSelectedDay(null)}
        />
      )}

      {selectedStatType !== null && selectedStat !== null && (
        <StatDetailModal statType={selectedStatType} stat={selectedStat} onClose={() => setSelectedStatType(null)} />
      )}

      {selectedSkillId !== null && (
        <SkillDetailModal
          skillName={selectedSkillName}
          detail={skillDetails[selectedSkillId]}
          isLoading={loadingSkillDetailId === selectedSkillId}
          error={skillDetailError}
          onClose={() => setSelectedSkillId(null)}
        />
      )}

      {levelModalOpen && (
        <LevelUnlocksModal level={user?.level ?? 1} onClose={() => setLevelModalOpen(false)} />
      )}
    </div>
  )
}

// 2026-09-17 (audit item #3): game/on_ice go through a 4-state button
// (not-started -> in-progress -> awaiting diary -> done) since both get a
// full-screen diary (see TrainingDiaryPage.tsx); off_ice has no diary
// step at all (has_diary_entry stays null there), so it keeps the
// original 2-state start/continue behavior unchanged. Team on-ice days
// use a different, time-based "awaiting" transition instead of this
// blocks checklist -- see the team-ice system's own doc, out of scope
// here.
function todayCardStartLabels(sessionType: DaySessionType): { start: string; resume: string } {
  if (sessionType === 'game') {
    return { start: 'Подготовка к игре', resume: 'Продолжить подготовку' }
  }
  if (sessionType === 'on_ice') {
    return { start: 'Подготовка ко льду', resume: 'Продолжить подготовку' }
  }
  return { start: 'Начать тренировку', resume: 'Продолжить тренировку' }
}

// The day's main part is done: an ice day or a game once its report is in
// (the report is what the day is -- the preparation is optional, owner's
// call 2026-10-10), a gym day once every exercise is.
function isMainDayDone(day: DayPlanRead): boolean {
  if (day.training_session === null) {
    return false
  }
  if (day.session_type === 'on_ice' || day.session_type === 'game') {
    return day.training_session.has_diary_entry === true
  }
  return isSessionDayCompleted(day)
}

function TodayCard({
  day,
  phaseLabel,
  phase,
  onStart,
  onFillDiary,
  onPlanWeek,
}: {
  day: DayPlanRead | null
  phaseLabel: string | null
  phase: BlockPhase | null
  onStart: () => void
  onFillDiary: () => void
  onPlanWeek: () => void
}) {
  const weekday = day !== null ? WEEKDAY_LABELS[(parseIsoDate(day.date).getDay() + 6) % 7] : null
  const eyebrow = [weekday, phaseLabel].filter(Boolean).join(' · ')

  if (day === null || day.training_session === null) {
    // Rest days never get a TrainingSession (see schedule_service.py), so
    // day.training_session === null already covers session_type === 'rest'
    // -- checking session_type here too would just be redundant with it.
    const isRestDay = day !== null && day.session_type === 'rest'
    return (
      <div className={`relative overflow-hidden p-5 ${CARD_CLASS}`}>
        <CardGlow />
        {/* relative: an absolute sibling (CardGlow) with z-index:auto
            actually paints ABOVE static in-flow content per CSS stacking
            order -- relative (still z-index:auto) is what puts this back
            on top, same fix TeamDetailPage's card-glow already needed. */}
        <div className="relative flex items-center gap-4">
          <i
            className={`ti ${isRestDay ? SESSION_TYPE_ICONS.rest : 'ti-calendar-off'} text-2xl text-[#8A94A6]`}
            aria-hidden="true"
          />
          <div>
            {eyebrow !== '' && <p className="mb-1 text-xs uppercase tracking-wide text-[#8A94A6]">{eyebrow}</p>}
            <p className="text-lg font-semibold text-[#F5F7FA]">
              {isRestDay ? getRestDayHint(phase) : day === null ? 'Неделя ещё не спланирована' : 'Нет плана на сегодня'}
            </p>
          </div>
        </div>
        {/* No day at all means this week has no plan -- the only fix is the
            week planner, so the card leads straight there instead of being
            a dead end. */}
        {day === null && (
          <div className="relative mt-4 flex flex-col gap-3">
            <p className="text-sm leading-relaxed text-[#C9D2DE]">
              Отметьте, в какие дни лёд, игра, сухая или отдых — тренировки подберутся под ваш уровень.
            </p>
            <Button onClick={onPlanWeek} className="w-full">
              Спланировать неделю
            </Button>
          </div>
        )}
      </div>
    )
  }

  const isIceLike = day.session_type === 'on_ice' || day.session_type === 'game'
  const reported = day.training_session.has_diary_entry === true
  // An ice/game day is done once its report is in, preparation or not.
  const blocksDone = isSessionDayCompleted(day) || (isIceLike && reported)
  const started = !blocksDone && isSessionDayStarted(day)
  // has_diary_entry is null for off_ice/rest (no diary step at all) --
  // only game/on_ice ever reach "blocksDone but still awaiting the
  // diary" (see TodayCard's own docstring above).
  const diaryPending = blocksDone && day.training_session.has_diary_entry === false
  const fullyDone = blocksDone && !diaryPending
  const { start: startLabel, resume: resumeLabel } = todayCardStartLabels(day.session_type)
  const reportLabel = day.session_type === 'game' ? 'Как сыграли?' : 'Отчёт после льда'

  return (
    <div className={`relative overflow-hidden p-5 ${CARD_CLASS}`}>
      <CardGlow />
      <div className="relative flex flex-col gap-4">
        <div className="flex items-center justify-between gap-3">
          {eyebrow !== '' && <p className="text-xs uppercase tracking-wide text-[#8A94A6]">{eyebrow}</p>}
          {fullyDone && (
            <span className="flex items-center gap-1 rounded-full bg-accent-ice/15 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-accent-ice">
              <i className="ti ti-check" aria-hidden="true" />
              Выполнено
            </span>
          )}
        </div>
        <p className="flex items-center gap-2 text-2xl font-bold text-[#F5F7FA]">
          <i className={`ti ${SESSION_TYPE_ICONS[day.session_type]} ${SESSION_TYPE_COLORS[day.session_type]}`} aria-hidden="true" />
          {DAY_SESSION_TYPE_LABELS[day.session_type]}
        </p>
        {day.session_type === 'on_ice' && !blocksDone && day.training_session.has_diary_entry === false && (
          <IceFocusCard trainingSessionId={day.training_session.id} />
        )}
        {diaryPending && (
          <Button onClick={onFillDiary} className="w-full">
            {reportLabel}
          </Button>
        )}
        {!blocksDone && (
          <Button onClick={onStart} className="w-full">
            {started ? resumeLabel : startLabel}
          </Button>
        )}
        {/* 2026-10-08: the report is what earns an ice/game day, so it must
            be reachable without doing the warm-up first. */}
        {!blocksDone && day.training_session.has_diary_entry === false && (
          <Button variant="neutral" onClick={onFillDiary} className="w-full">
            {reportLabel}
          </Button>
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
        <p className="font-display text-3xl font-bold leading-none text-[#F5F7FA]">
          {Math.round(stat.current_value)}
        </p>
      </div>
    </Modal>
  )
}

function SkillsNearMilestoneCard({
  skills,
  onSelectSkill,
}: {
  skills: SkillSummaryRead[]
  onSelectSkill: (skillId: string) => void
}) {
  // First real usage of the coachmark tour overlay (2026-08-30
  // discoverability pass) -- these rows just picked up a chevron+accent
  // affordance, but a first-time visitor still benefits from one explicit
  // "these are tappable" nudge the first time this card appears.
  const coachmarkRef = useCoachmarkStep(
    'home-skill-milestones',
    'Нажмите на навык, чтобы увидеть его пороги и вклад в характеристики.',
    'ti-hand-click',
  )
  const top = topSkillsNearMilestone(skills)
  if (top.length === 0) {
    return null
  }

  return (
    <div ref={coachmarkRef} className={`flex flex-col gap-3 p-4 ${CARD_CLASS}`}>
      <h2 className="text-sm font-medium text-[#8A94A6]">Ближайшие пороги</h2>
      <div className="flex flex-col gap-4">
        {top.map((skill) => {
          const milestone = skill.next_milestone!
          const nearThreshold = milestone.points_remaining < 5
          const percent =
            milestone.threshold > 0
              ? Math.max(0, Math.min(100, (skill.value / milestone.threshold) * 100))
              : 100
          return (
            <button
              key={skill.id}
              type="button"
              onClick={() => onSelectSkill(skill.id)}
              className="group flex items-center gap-3 text-left"
            >
              {/* Faceoff-circle ring, not a linear bar -- a milestone
                  threshold is a target you're closing in on, which the
                  ring reads as directly (hockey design pass, 2026-08-28).
                  Center shows percent; the text beside it still carries
                  the concrete "how many points" detail the ring can't. */}
              <FaceoffProgressRing
                value={skill.value}
                max={milestone.threshold}
                accent={nearThreshold ? 'persimmon' : 'ice'}
                size={48}
                centerValue={`${Math.round(percent)}%`}
              />
              <div className="flex min-w-0 flex-1 flex-col gap-1">
                {/* Accent color, not plain white -- this row was tappable
                    but read as inert label text (discoverability pass,
                    2026-08-30: "Ближайшие пороги" names gave no visual
                    affordance). Same treatment as the chevron pattern
                    already used for row-style navigation elsewhere. */}
                <span className="truncate text-sm font-medium text-accent-ice">{skill.name}</span>
                {nearThreshold ? (
                  <span className="text-xs font-medium text-accent-persimmon">почти порог</span>
                ) : (
                  <span className="text-xs text-[#8A94A6]">
                    {Math.round(milestone.points_remaining)} до «{milestone.title}»
                  </span>
                )}
              </div>
              <i
                className="ti ti-chevron-right shrink-0 text-lg text-[#8A94A6] transition-all group-hover:translate-x-0.5 group-hover:text-accent-ice"
                aria-hidden="true"
              />
            </button>
          )
        })}
      </div>
    </div>
  )
}

// Mirrors app.core.training_block.TAPER_WINDOW_WEEKS / _TAPER_FINAL_WEEK_DAYS
// -- display-only, the server is the source of truth for actual volume.
const TAPER_WINDOW_DAYS = 21
const TAPER_FINAL_WEEK_DAYS = 7

function TournamentTaperBanner({ tournamentDate }: { tournamentDate: string | null }) {
  if (tournamentDate === null) {
    return null
  }
  const daysUntil = Math.floor(
    (new Date(tournamentDate).getTime() - new Date().setHours(0, 0, 0, 0)) / 86_400_000,
  )
  if (daysUntil < 0 || daysUntil >= TAPER_WINDOW_DAYS) {
    return null
  }
  const isFinalWeek = daysUntil < TAPER_FINAL_WEEK_DAYS

  return (
    <div className={`flex flex-col gap-2 p-4 ${CARD_CLASS_URGENT}`}>
      <p className="text-xs text-accent-persimmon">
        {isFinalWeek
          ? `Финальная неделя перед турниром (через ${daysUntil} дн.) — объём тренировок снижен по максимуму.`
          : `Подводка к турниру (через ${daysUntil} дн.) — объём тренировок постепенно снижается.`}
      </p>
    </div>
  )
}

function PeriodizationCard({ block }: { block: TrainingBlockRead }) {
  const navigate = useNavigate()
  const [infoOpen, setInfoOpen] = useState(false)
  const description = BLOCK_PHASE_DESCRIPTIONS[block.phase]

  return (
    <div className={`flex flex-col gap-2 p-4 ${CARD_CLASS}`}>
      <div className="flex items-center justify-between text-sm">
        <span className="flex items-center gap-1.5 text-[#8A94A6]">
          Блок {block.block_number} · {BLOCK_PHASE_LABELS[block.phase]}
          <button
            type="button"
            onClick={() => setInfoOpen((value) => !value)}
            aria-label="Что означает эта фаза"
            aria-expanded={infoOpen}
            title={description}
            className="text-[#8A94A6] transition-colors hover:text-accent-ice"
          >
            <i className="ti ti-info-circle text-sm" aria-hidden="true" />
          </button>
        </span>
        <span className="font-mono text-accent-ice">
          {block.sessions_completed_in_phase}/{block.sessions_to_advance}
        </span>
      </div>
      {infoOpen && (
        <div className="flex flex-col gap-1.5">
          <p className="text-xs text-[#8A94A6]">{description}</p>
          <button
            type="button"
            onClick={() => navigate('/reference')}
            className="w-fit text-xs text-accent-ice hover:underline"
          >
            Подробнее о фазах блока — в Справочнике ›
          </button>
        </div>
      )}
      {block.is_macrocycle_deload && (
        <p className="text-xs text-accent-persimmon">
          Восстановительный макроцикл — вес и повторы временно ниже обычного, чтобы вы отдохнули
          перед следующим циклом роста.
        </p>
      )}
      <ProgressBar value={block.sessions_completed_in_phase} max={block.sessions_to_advance} />
    </div>
  )
}

// From Friday on, if next week has no plan yet: the week planner is a manual
// step every week, and forgetting it means Monday opens on an empty day.
const NEXT_WEEK_REMINDER_FROM_WEEKDAY = 4 // Monday = 0, so Friday

function NextWeekPlanCard({ onPlan }: { onPlan: () => void }) {
  const { accessToken } = useAuth()
  const [needsPlan, setNeedsPlan] = useState(false)
  const weekdayIndex = (new Date().getDay() + 6) % 7

  useEffect(() => {
    if (accessToken === null || weekdayIndex < NEXT_WEEK_REMINDER_FROM_WEEKDAY) {
      return
    }
    let cancelled = false
    const nextMondayIso = toIsoDate(addDays(getMondayOfCurrentWeek(), 7))
    loadOptional(scheduleApi.getWeeklyPlan(nextMondayIso, accessToken))
      .then((plan) => !cancelled && setNeedsPlan(plan === null))
      .catch(() => {
        // Best-effort -- no reminder on an error.
      })
    return () => {
      cancelled = true
    }
  }, [accessToken, weekdayIndex])

  if (!needsPlan) {
    return null
  }
  return (
    <button
      type="button"
      onClick={onPlan}
      className="flex items-center gap-3 rounded-md border border-dashed border-accent-ice/35 bg-accent-ice/[0.05] p-4 text-left"
    >
      <i className="ti ti-calendar-plus text-2xl text-accent-ice" aria-hidden="true" />
      <span className="flex flex-1 flex-col gap-0.5">
        <span className="text-sm font-medium text-[#F5F7FA]">Следующая неделя не спланирована</span>
        <span className="text-xs text-[#8A94A6]">Отметьте лёд, игры и отдых — займёт минуту</span>
      </span>
      <span className="text-sm font-semibold text-accent-ice">Спланировать</span>
    </button>
  )
}

// This week's quests at a glance -- the whole list used to sit under
// "Ещё", out of sight; a reward waiting to be claimed is called out.
function WeeklyQuestsCard({ onOpen }: { onOpen: () => void }) {
  const { accessToken } = useAuth()
  const [quests, setQuests] = useState<QuestStatusRead[] | null>(null)

  useEffect(() => {
    if (accessToken === null) {
      return
    }
    let cancelled = false
    questsApi
      .getQuestStatus(accessToken)
      .then((result) => !cancelled && setQuests(result))
      .catch(() => {
        // Best-effort -- the card just doesn't render.
      })
    return () => {
      cancelled = true
    }
  }, [accessToken])

  if (quests === null) {
    return null
  }
  const weekly = quests.filter((quest) => quest.type === 'weekly')
  const claimable = quests.filter((quest) => quest.claimable).length
  if (weekly.length === 0 && claimable === 0) {
    return null
  }

  return (
    <button type="button" onClick={onOpen} className={`flex flex-col gap-3 p-4 text-left ${CARD_CLASS}`}>
      <span className="flex items-center gap-2">
        <span className="flex-1 text-xs font-semibold uppercase tracking-wide text-[#8A94A6]">Задания недели</span>
        {claimable > 0 && (
          <span className="rounded-full bg-accent-persimmon/15 px-2 py-0.5 text-xs font-semibold text-[#FF8A6B]">
            {claimable === 1 ? '1 награда ждёт' : `Наград ждёт: ${claimable}`}
          </span>
        )}
      </span>
      {weekly.map((quest) => (
        <span key={quest.id} className="flex items-center gap-2.5">
          <span
            className={`flex h-[18px] w-[18px] shrink-0 items-center justify-center rounded ${
              quest.completed || quest.claimable ? 'bg-accent-ice text-dark-bg' : 'border-[1.5px] border-white/25'
            }`}
          >
            {(quest.completed || quest.claimable) && <i className="ti ti-check text-xs" aria-hidden="true" />}
          </span>
          <span className={`flex-1 text-sm ${quest.completed ? 'text-[#8A94A6] line-through' : 'text-[#F5F7FA]'}`}>
            {quest.title}
          </span>
          <span className="font-display text-sm text-accent-persimmon">+{quest.xp_reward}</span>
        </span>
      ))}
    </button>
  )
}

function CalendarPanel({
  month,
  onMonthChange,
  calendarData,
  onSelectDay,
}: {
  month: Date
  onMonthChange: (month: Date) => void
  calendarData: Record<string, ActivityCalendarDayRead>
  onSelectDay: (date: Date) => void
}) {
  const cells = buildMonthGrid(month)
  const todayIso = toIsoDate(new Date())

  return (
    <div className={`flex flex-col gap-3 p-4 ${CARD_CLASS}`}>
      <div className="flex items-center justify-between">
        <button
          type="button"
          onClick={() => onMonthChange(addMonths(month, -1))}
          aria-label="Предыдущий месяц"
          className="text-[#8A94A6] transition-colors hover:text-[#F5F7FA]"
        >
          <i className="ti ti-chevron-left" aria-hidden="true" />
        </button>
        <span className="text-sm font-medium text-[#F5F7FA]">
          {MONTH_LABELS[month.getMonth()]} {month.getFullYear()}
        </span>
        <button
          type="button"
          onClick={() => onMonthChange(addMonths(month, 1))}
          aria-label="Следующий месяц"
          className="text-[#8A94A6] transition-colors hover:text-[#F5F7FA]"
        >
          <i className="ti ti-chevron-right" aria-hidden="true" />
        </button>
      </div>

      <div className="grid grid-cols-7 gap-1 text-center text-xs text-[#8A94A6]">
        {WEEKDAY_LABELS.map((label) => (
          <span key={label}>{label}</span>
        ))}
      </div>

      <div className="grid grid-cols-7 gap-1">
        {cells.map((date, index) => {
          if (date === null) {
            return <div key={index} />
          }
          const iso = toIsoDate(date)
          const active = hasKnownActivity(iso, calendarData)
          const isToday = iso === todayIso
          return (
            <button
              key={iso}
              type="button"
              onClick={() => onSelectDay(date)}
              className={`aspect-square rounded font-mono text-xs transition-colors ${
                active
                  ? 'bg-accent-persimmon text-dark-bg'
                  : `text-[#8A94A6] hover:bg-white/5 ${isToday ? 'border border-accent-ice' : ''}`
              }`}
            >
              {date.getDate()}
            </button>
          )
        })}
      </div>
    </div>
  )
}

function DayDetailModal({
  date,
  dayPlan,
  isLoadingPlan,
  hasKnownActivity: dayHasActivity,
  onClose,
}: {
  date: Date
  dayPlan: DayPlanRead | undefined
  isLoadingPlan: boolean
  hasKnownActivity: boolean
  onClose: () => void
}) {
  return (
    <Modal title={formatShortDate(date)} onClose={onClose}>
      {isLoadingPlan && <p className="text-sm text-[#8A94A6]">Загрузка...</p>}

      {!isLoadingPlan && dayPlan === undefined && (
        <p className="text-sm text-[#8A94A6]">
          {dayHasActivity
            ? // GET /schedule/day-plan (by exact date) came back 404 despite
              // GET /users/me/activity-calendar marking this date
              // fully_completed -- shouldn't happen (fully_completed implies
              // a DayPlan+TrainingSession exist), kept as a defensive
              // fallback rather than assumed impossible.
              'В этот день была тренировка, но детали пока недоступны.'
            : 'Тренировки не было.'}
        </p>
      )}

      {dayPlan !== undefined && dayPlan.session_type === 'rest' && (
        <p className="text-sm text-[#8A94A6]">День отдыха.</p>
      )}

      {dayPlan !== undefined && dayPlan.session_type !== 'rest' && dayPlan.training_session === null && (
        <p className="text-sm text-[#8A94A6]">Тренировки не было.</p>
      )}

      {dayPlan !== undefined && dayPlan.training_session !== null && (
        <DayDetailSession session={dayPlan.training_session} sessionType={dayPlan.session_type} />
      )}
    </Modal>
  )
}

// Same phase-card shape as NewSchedulePage's DayPreviewPhaseSection/
// StartedDayPhaseSection and TrainingSessionPage's PhasePreviewSheet -- icon
// + label + count header, hairline-divided rows below -- rather than the
// flat "name, checkmark" list this replaced (found 2026-08-27: "текста
// дохрена" -- a fully off-ice day is 15+ exercises with nothing visually
// separating one from the next, or one phase from another).
function DayDetailSession({
  session,
  sessionType,
}: {
  session: TrainingSessionRead
  sessionType: DaySessionType
}) {
  const doneCount = session.blocks.filter(
    (block) => block.completed_at !== null || block.skipped_at !== null,
  ).length
  const totalCount = session.blocks.length

  const blocksByPhase: Record<TrainingPhase, SessionBlockRead[]> = {
    warmup: [],
    main: [],
    cooldown: [],
    puck: [],
  }
  for (const block of session.blocks) {
    blocksByPhase[block.phase].push(block)
  }
  const activePhases = PHASE_SEQUENCE.filter((phase) => blocksByPhase[phase].length > 0)

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-3">
        <span className="flex items-center gap-2 text-sm font-medium text-[#F5F7FA]">
          <i
            className={`ti ${SESSION_TYPE_ICONS[sessionType]} ${SESSION_TYPE_COLORS[sessionType]}`}
            aria-hidden="true"
          />
          {DAY_SESSION_TYPE_LABELS[sessionType]}
        </span>
        <span className="font-mono text-xs text-[#8A94A6]">
          {doneCount} из {totalCount}
        </span>
      </div>

      {activePhases.map((phase) => (
        <div key={phase} className={`overflow-hidden rounded-md ${CARD_BORDER} bg-dark-bg/40`}>
          <div className="flex items-center gap-2 px-3 pb-2 pt-2.5">
            <i className={`ti ${PHASE_ICONS[phase]} text-sm text-accent-ice`} aria-hidden="true" />
            <p className="text-xs font-medium uppercase tracking-wide text-[#8A94A6]">{PHASE_LABELS[phase]}</p>
            <span className="ml-auto font-mono text-[11px] text-[#8A94A6]">{blocksByPhase[phase].length}</span>
          </div>
          <div className="flex flex-col divide-y divide-white/5">
            {blocksByPhase[phase].map((block) => {
              const volume = formatTargetVolume(block.exercise)
              const skipped = block.skipped_at !== null
              const done = block.completed_at !== null || skipped
              return (
                <div key={block.id} className="flex items-center gap-3 px-3 py-2.5">
                  <i
                    className={`ti ${
                      skipped ? 'ti-player-skip-forward text-[#8A94A6]' : done ? 'ti-check text-accent-ice' : 'ti-minus text-[#8A94A6]'
                    } shrink-0 text-xs`}
                    aria-hidden="true"
                  />
                  <span className={`line-clamp-2 min-w-0 flex-1 text-sm ${done ? 'text-[#F5F7FA]' : 'text-[#8A94A6]'}`}>
                    {block.exercise.name}
                  </span>
                  {volume !== null && (
                    <span className="shrink-0 whitespace-nowrap rounded bg-white/5 px-1.5 py-0.5 font-mono text-[11px] text-[#8A94A6]">
                      {volume}
                    </span>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      ))}
    </div>
  )
}

// All of today's trainings are done (2026-10-10): what was done and a way
// to the day's report.
function DayClosedCard({ day, extra, onReport }: { day: DayPlanRead; extra: DayPlanRead | null; onReport: () => void }) {
  const items = [day, ...(extra !== null ? [extra] : [])].sort((a, b) =>
    a.time_of_day === 'morning' ? -1 : b.time_of_day === 'morning' ? 1 : 0,
  )
  return (
    <div className={`relative overflow-hidden p-5 ${CARD_CLASS}`}>
      <CardGlow />
      <div className="relative flex flex-col gap-4">
        <div className="flex items-center justify-between gap-3">
          <p className="text-xs uppercase tracking-wide text-[#8A94A6]">
            {WEEKDAY_LABELS[(parseIsoDate(day.date).getDay() + 6) % 7]} · день закрыт
          </p>
          <span className="flex items-center gap-1 rounded-full bg-accent-ice/15 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-accent-ice">
            <i className="ti ti-check" aria-hidden="true" />
            Выполнено
          </span>
        </div>
        <p className="text-xl font-bold text-[#F5F7FA]">Все тренировки дня сделаны</p>
        <div className="flex flex-col divide-y divide-white/5">
          {items.map((item) => (
            <div key={item.id} className="flex items-center justify-between gap-3 py-2 text-sm">
              <span className="flex items-center gap-2 text-[#F5F7FA]">
                <i className={`ti ${SESSION_TYPE_ICONS[item.session_type]} ${SESSION_TYPE_COLORS[item.session_type]}`} aria-hidden="true" />
                {DAY_SESSION_TYPE_LABELS[item.session_type]}
                {item.time_of_day !== null && item.time_of_day !== undefined && (
                  <span className="text-xs text-[#8A94A6]">· {item.time_of_day === 'morning' ? 'утро' : 'вечер'}</span>
                )}
              </span>
              <span className="text-xs text-[#8A94A6]">
                {item.session_type === 'on_ice' || item.session_type === 'game' ? 'отчёт отправлен' : 'пройдено'}
              </span>
            </div>
          ))}
        </div>
        <Button variant="neutral" onClick={onReport} className="w-full">
          Как прошёл день

        </Button>
      </div>
    </div>
  )
}

// Double day (step 6): the day's separate gym training, above the ice when
// it's in the morning, below when in the evening.
function ExtraGymTodayCard({ day, onStart }: { day: DayPlanRead; onStart: () => void }) {
  const blocks = day.training_session?.blocks ?? []
  const done = blocks.length > 0 && blocks.every((b) => b.completed_at !== null || b.skipped_at !== null)
  const started = blocks.some((b) => b.completed_at !== null || b.skipped_at !== null)
  return (
    <div className="flex items-center gap-3 rounded-2xl border border-white/10 bg-dark-card p-4">
      <i className="ti ti-barbell text-2xl text-accent-persimmon" aria-hidden="true" />
      <div className="flex min-w-0 flex-1 flex-col">
        <span className="text-xs uppercase tracking-wide text-[#8A94A6]">
          {day.time_of_day === 'morning' ? 'Утро' : 'Вечер'} · зал
        </span>
        <span className="text-sm font-semibold text-[#F5F7FA]">
          {done ? 'Зал пройден' : `${blocks.length} упражнений`}
        </span>
      </div>
      {!done && (
        <button
          type="button"
          onClick={onStart}
          className="shrink-0 rounded-xl bg-accent-persimmon px-4 py-2 text-sm font-semibold text-dark-bg"
        >
          {started ? 'Продолжить' : 'Начать'}
        </button>
      )}
    </div>
  )
}
