import { useRef, useState } from 'react'
import type { TouchEvent } from 'react'
import { Button } from './ui/Button'

interface Slide {
  icon: string
  title: string
  body: string
}

const SLIDES: Slide[] = [
  {
    icon: 'ti-calendar-stats',
    title: 'План на каждую неделю',
    body: 'Каждую неделю мы подбираем вам тренировки — лёд, зал, отдых — под ваш уровень и цели.',
  },
  {
    icon: 'ti-flame',
    title: 'Тренируйтесь регулярно',
    body: 'Стрик растёт, уровень растёт, открываются новые возможности.',
  },
  {
    icon: 'ti-chart-radar',
    title: 'Прогресс — в навыках и статах',
    body: 'Ваш прогресс виден в навыках и статах. Качайте то, что важно именно вам.',
  },
  {
    icon: 'ti-rocket',
    title: 'Спланируйте свою неделю',
    body: 'Выберите дни для льда, зала и отдыха — и начнём тренироваться.',
  },
]

// Minimum horizontal drag before a touch counts as a swipe, not a tap --
// short taps/scrolls shouldn't accidentally flip a slide.
const SWIPE_THRESHOLD_PX = 50

interface OnboardingTourProps {
  // Both count as "seen" server-side (see HomePage), but only the final
  // "Начать" sends the user on to plan their first week -- "Пропустить" at
  // any earlier slide just drops them back on Home as before.
  onSkip: () => void
  onComplete: () => void
}

export function OnboardingTour({ onSkip, onComplete }: OnboardingTourProps) {
  const [index, setIndex] = useState(0)
  const touchStartX = useRef<number | null>(null)

  const isLast = index === SLIDES.length - 1
  const slide = SLIDES[index]

  function goNext() {
    if (isLast) {
      onComplete()
      return
    }
    setIndex((current) => current + 1)
  }

  function goPrev() {
    setIndex((current) => Math.max(0, current - 1))
  }

  function handleTouchStart(event: TouchEvent) {
    touchStartX.current = event.touches[0].clientX
  }

  function handleTouchEnd(event: TouchEvent) {
    if (touchStartX.current === null) {
      return
    }
    const deltaX = event.changedTouches[0].clientX - touchStartX.current
    touchStartX.current = null
    if (deltaX <= -SWIPE_THRESHOLD_PX) {
      goNext()
    } else if (deltaX >= SWIPE_THRESHOLD_PX) {
      goPrev()
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex flex-col overflow-hidden bg-dark-bg"
      onTouchStart={handleTouchStart}
      onTouchEnd={handleTouchEnd}
    >
      {/* Same arena-bg + logo treatment as Login/Register/Onboarding --
          this tour is still part of that "welcome" sequence (shown once,
          right after finishing onboarding), not a regular in-app screen --
          IceGlowBackground (what HomePage itself uses underneath this
          overlay) is reserved for the moment the tour ends and the real
          app takes over. */}
      <div className="absolute inset-0 bg-[url('/images/arena-bg.webp')] bg-cover bg-center" />
      <div className="absolute inset-0 bg-dark-bg/80" />

      {!isLast && (
        <button
          type="button"
          onClick={onSkip}
          className="absolute right-4 top-4 z-[1] px-2 py-1 text-sm text-text-secondary transition-colors hover:text-text-primary"
        >
          Пропустить
        </button>
      )}

      <div className="relative z-[1] flex flex-1 flex-col items-center justify-center px-6">
        <img src="/images/logo.webp" alt="IceLevel" className="mb-8 w-full max-w-[180px] opacity-80" />
        <div className="flex w-full max-w-sm flex-col items-center gap-6 text-center">
          <div className="flex h-20 w-20 items-center justify-center rounded-full border-t border-[rgba(215,239,255,0.35)] bg-dark-card">
            <i className={`ti ${slide.icon} text-4xl text-accent-ice`} aria-hidden="true" />
          </div>
          <div className="flex flex-col gap-3">
            <h2 className="text-balance text-xl font-semibold text-text-primary">{slide.title}</h2>
            <p className="text-sm leading-relaxed text-text-secondary">{slide.body}</p>
          </div>
        </div>
      </div>

      <div className="relative z-[1] flex flex-col items-center gap-6 px-6 pb-10">
        <div className="flex items-center gap-2">
          {SLIDES.map((item, dotIndex) => (
            <span
              key={item.title}
              className={`h-1.5 rounded-full transition-all ${
                dotIndex === index ? 'w-6 bg-accent-persimmon' : 'w-1.5 bg-white/15'
              }`}
              aria-hidden="true"
            />
          ))}
        </div>

        <div className="flex w-full max-w-sm items-center gap-3">
          {index > 0 && (
            <Button variant="neutral" onClick={goPrev} className="flex-1">
              Назад
            </Button>
          )}
          <Button onClick={goNext} className="flex-1">
            {isLast ? 'Начать' : 'Далее'}
          </Button>
        </div>
      </div>
    </div>
  )
}
