import { Button } from './ui/Button'
import { CARD_BORDER } from './ui/cardStyle'

interface OnboardingTourProps {
  // Both count as "seen" server-side (see HomePage), but only "Начать"
  // sends the user on to plan their first week -- "Пропустить" just drops
  // them back on Home as before.
  onSkip: () => void
  onComplete: () => void
}

// Down to one short blurb (2026-08-30 coachmark pass) -- the previous
// 4-slide feature-callout sequence front-loaded explanations ("streaks
// grow", "progress shows in skills/stats"...) before the athlete had ever
// seen the screens those referred to. That detail now lives in the
// coachmark tour, triggered by actually reaching each part of the UI (see
// CoachmarkProvider) -- this welcome screen's only job is "start planning
// your first week", not a feature tour.
export function OnboardingTour({ onSkip, onComplete }: OnboardingTourProps) {
  return (
    <div className="fixed inset-0 z-50 flex flex-col overflow-hidden bg-dark-bg">
      {/* Same arena-bg + logo treatment as Login/Register/Onboarding --
          this is still part of that "welcome" sequence (shown once, right
          after finishing onboarding), not a regular in-app screen --
          IceGlowBackground (what HomePage itself uses underneath this
          overlay) is reserved for the moment the tour ends and the real
          app takes over. */}
      <div className="absolute inset-0 bg-[url('/images/arena-bg.webp')] bg-cover bg-center" />
      <div className="absolute inset-0 bg-dark-bg/80" />

      <button
        type="button"
        onClick={onSkip}
        className="absolute right-4 top-4 z-10 px-2 py-1 text-sm text-text-secondary transition-colors hover:text-text-primary"
      >
        Пропустить
      </button>

      <div className="relative z-[1] flex flex-1 flex-col items-center justify-center px-6">
        <img src="/images/logo.webp" alt="IceLevel" className="mb-8 w-full max-w-[180px] opacity-80" />
        <div className="flex w-full max-w-sm flex-col items-center gap-6 text-center">
          <div className={`flex h-20 w-20 items-center justify-center rounded-full ${CARD_BORDER} bg-dark-card`}>
            <i className="ti ti-rocket text-4xl text-accent-ice" aria-hidden="true" />
          </div>
          <div className="flex flex-col gap-3">
            <h2 className="text-balance text-xl font-semibold text-text-primary">Добро пожаловать в IceLevel</h2>
            <p className="text-sm leading-relaxed text-text-secondary">
              Каждую неделю мы подбираем тренировки под ваш уровень — лёд, зал, отдых. Начнём с
              планирования первой недели, а дальше подскажем прямо по ходу дела.
            </p>
          </div>
        </div>
      </div>

      <div className="relative z-[1] flex flex-col items-center px-6 pb-10">
        <Button onClick={onComplete} className="w-full max-w-sm">
          Начать
        </Button>
      </div>
    </div>
  )
}
