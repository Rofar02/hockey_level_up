import { Link } from 'react-router-dom'
import { CARD_BORDER } from './cardStyle'

interface PremiumGateProps {
  title?: string
  description?: string
}

// A preview of what premium unlocks, linking to the /premium sales page
// (2026-10-04; payment itself isn't wired yet, see PremiumPage). Shared by
// every premium-gated screen (analytics, AI coach, ...) so the visual
// treatment and default copy only live in one place. Both real call sites
// (AnalyticsPage/CoachPage) override title/description with copy specific
// to what THAT screen unlocks, so these defaults only render if PremiumGate
// is ever used bare -- keep them accurate to what's actually shipped (both
// analytics and coach chat are real today, not "coming soon") rather than
// stale placeholder text nobody actually sees day to day.
export function PremiumGate({
  title = 'Эта функция — часть премиум-подписки',
  description = 'С премиум-подпиской откроются графики роста характеристик и навыков, текстовые инсайты о вашем прогрессе, и персональный AI-тренер.',
}: PremiumGateProps) {
  return (
    <div
      className={`flex flex-col items-center gap-4 rounded-md ${CARD_BORDER} bg-dark-card p-8 text-center`}
    >
      <i className="ti ti-crown text-4xl text-accent-ice" aria-hidden="true" />
      <div className="flex flex-col gap-2">
        <h2 className="text-lg font-semibold text-[#F5F7FA]">{title}</h2>
        <p className="text-sm text-[#8A94A6]">{description}</p>
      </div>
      <Link
        to="/premium"
        className="rounded bg-accent-persimmon px-4 py-2.5 font-medium text-dark-bg transition-colors hover:bg-accent-persimmon/90"
      >
        Узнать про премиум
      </Link>
    </div>
  )
}
