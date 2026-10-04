import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { PlayerCard } from '../components/PlayerCard'
import { cardStatsFrom, overallRatingOf } from '../components/playerCardStats'
import { BackLink } from '../components/ui/BackLink'
import { Button } from '../components/ui/Button'
import { IceGlowBackground } from '../components/ui/IceGlowBackground'
import { Modal } from '../components/ui/Modal'
import * as progressApi from '../api/progress'
import { API_BASE_URL } from '../api/client'
import { useAuth } from '../hooks/useAuth'
import type { UserStatRead } from '../types/progress'

// The premium sales page (2026-10-04, mockup variant A: the player's own card
// in gold on top). No prices yet and no payment provider wired (YooKassa is
// planned), so "Оформить" opens a "coming soon" stub instead of a checkout.
// Benefits not built yet (the gold card on the
// profile) carry a "СКОРО" badge -- drop it as each one ships.

type Plan = 'year' | 'month'

const BENEFITS: { icon: string; title: string; text: string; isSoon?: boolean }[] = [
  {
    icon: 'ti-message-chatbot',
    title: 'ИИ-тренер без ограничений',
    text: '150 сообщений в месяц вместо 5. Спрашивай про технику, нагрузку, игры.',
  },
  {
    icon: 'ti-calendar-stats',
    title: 'Разбор недели',
    text: 'Каждый понедельник тренер подводит итоги: рекорды, что просело и на чём сфокусироваться.',
  },
  {
    icon: 'ti-brain',
    title: 'Тренер тебя помнит',
    text: 'Травмы, цели, турниры — не нужно повторять каждый раз.',
  },
  {
    icon: 'ti-chart-line',
    title: 'Аналитика прогресса',
    text: 'Рост характеристик и навыков, рекорды, баланс нагрузки на мышцы.',
  },
  {
    icon: 'ti-star',
    title: 'Премиальная карточка',
    text: 'Золотая рамка и блеск — видно друзьям и команде.',
    isSoon: true,
  },
]

const PLANS: { id: Plan; title: string; note: string; badge?: string }[] = [
  { id: 'year', title: 'Год', note: 'оплата раз в год', badge: 'Выгоднее' },
  { id: 'month', title: 'Месяц', note: 'продлевается каждый месяц' },
]

export function PremiumPage() {
  const { user, accessToken } = useAuth()
  const hasPremium = user?.has_premium === true
  const [plan, setPlan] = useState<Plan>('year')
  const [isCheckoutOpen, setIsCheckoutOpen] = useState(false)

  // For the gold card preview -- best-effort, the card shows "—" without it.
  const [stats, setStats] = useState<UserStatRead[]>([])
  useEffect(() => {
    if (accessToken === null) {
      return
    }
    let cancelled = false
    progressApi
      .getMyStats(accessToken)
      .then((result) => !cancelled && setStats(result))
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
  }, [accessToken])

  return (
    <div className="relative min-h-svh overflow-hidden">
      <IceGlowBackground />
      <div className="relative z-[1] mx-auto flex max-w-2xl flex-col gap-6 px-4 pb-32 pt-8">
        <div className="flex flex-col gap-2">
          <BackLink />
          <h1 className="text-xl font-semibold">Премиум</h1>
        </div>

        <div className="mx-auto w-full max-w-[260px]">
          <PlayerCard
            cardStyle="gold"
            shine
            jerseyColor={user?.jersey_color ?? null}
            rating={overallRatingOf(stats)}
            position={user?.position ?? null}
            jerseyNumber={user?.jersey_number ?? null}
            surname={user?.last_name || user?.first_name || ''}
            subtitle={user?.first_name ?? ''}
            level={user?.level ?? 1}
            xp={user?.xp ?? 0}
            avatarUrl={user?.avatar_url != null ? `${API_BASE_URL}${user.avatar_url}` : null}
            teamLogoUrl={null}
            stats={cardStatsFrom(stats)}
          />
        </div>

        <div className="flex flex-col gap-2 text-center">
          <h2 className="font-display text-3xl font-bold uppercase leading-tight tracking-wide">
            Играй на уровень выше
          </h2>
          <p className="text-[15px] leading-relaxed text-text-secondary">
            Личный тренер, который помнит тебя, разбор каждой недели и аналитика роста.
          </p>
        </div>

        <ul className="flex flex-col gap-2.5">
          {BENEFITS.map((benefit) => (
            <li key={benefit.title} className="flex items-start gap-3.5 rounded-md bg-dark-card p-3.5">
              <i className={`ti ${benefit.icon} mt-0.5 text-2xl text-accent-ice`} aria-hidden="true" />
              <div className="flex flex-col gap-1">
                <span className="flex items-center gap-2 text-[15px] font-semibold">
                  {benefit.title}
                  {benefit.isSoon === true && (
                    <span className="rounded border border-accent-ice/40 px-1.5 py-0.5 text-[10px] font-bold text-accent-ice">СКОРО</span>
                  )}
                </span>
                <span className="text-[13px] leading-snug text-text-secondary">{benefit.text}</span>
              </div>
            </li>
          ))}
        </ul>

        {hasPremium ? (
          <div className="flex items-center gap-3 rounded-md border border-[#F6D98A]/40 bg-dark-card p-4">
            <i className="ti ti-crown text-2xl text-[#F6D98A]" aria-hidden="true" />
            <span className="text-[15px] font-semibold">Премиум уже активен.</span>
          </div>
        ) : (
          <>
            <div className="flex flex-col gap-2.5" role="radiogroup" aria-label="Тариф">
              {PLANS.map((option) => {
                const isSelected = plan === option.id
                return (
                  <button
                    key={option.id}
                    type="button"
                    role="radio"
                    aria-checked={isSelected}
                    onClick={() => setPlan(option.id)}
                    className={`flex min-h-16 items-center justify-between rounded-md border-2 px-4 py-3 text-left transition-colors ${
                      isSelected ? 'border-accent-ice bg-[#1D2840]' : 'border-white/10 bg-dark-card hover:border-white/20'
                    }`}
                  >
                    <span className="flex flex-col gap-0.5">
                      <span className="flex items-center gap-2 text-[15px] font-semibold">
                        {option.title}
                        {option.badge !== undefined && (
                          <span className="rounded bg-accent-ice px-1.5 py-0.5 text-[10px] font-bold text-dark-bg">
                            {option.badge}
                          </span>
                        )}
                      </span>
                      <span className="text-xs text-text-secondary">{option.note}</span>
                    </span>
                    <span
                      className={`flex h-5 w-5 items-center justify-center rounded-full border-2 ${
                        isSelected ? 'border-accent-ice' : 'border-white/25'
                      }`}
                      aria-hidden="true"
                    >
                      {isSelected && <span className="h-2.5 w-2.5 rounded-full bg-accent-ice" />}
                    </span>
                  </button>
                )
              })}
            </div>

            <div className="flex flex-col gap-3">
              <Button type="button" className="h-14 text-base font-bold" onClick={() => setIsCheckoutOpen(true)}>
                {plan === 'year' ? 'Оформить на год' : 'Оформить на месяц'}
              </Button>
              <p className="text-center text-xs leading-relaxed text-text-secondary">
                Оплата картой или через СБП. Отменить можно в любой момент.
                <br />
                <Link to="/privacy" className="text-accent-ice hover:text-text-primary">
                  Политика конфиденциальности
                </Link>
              </p>
            </div>
          </>
        )}
      </div>

      {isCheckoutOpen && (
        <Modal title="Оплата скоро появится" onClose={() => setIsCheckoutOpen(false)}>
          <div className="flex flex-col items-center gap-4 text-center">
            <i className="ti ti-credit-card text-4xl text-accent-ice" aria-hidden="true" />
            <p className="text-[15px] leading-relaxed text-text-secondary">
              Мы подключаем оплату картой и через СБП. Как только она заработает, премиум можно будет оформить прямо
              здесь.
            </p>
            <Button type="button" variant="neutral" className="w-full" onClick={() => setIsCheckoutOpen(false)}>
              Понятно
            </Button>
          </div>
        </Modal>
      )}
    </div>
  )
}
