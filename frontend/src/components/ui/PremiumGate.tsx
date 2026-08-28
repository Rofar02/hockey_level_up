import { CARD_BORDER } from './cardStyle'

interface PremiumGateProps {
  title?: string
  description?: string
}

// Purely informational -- no payment flow exists yet, so this is a preview
// of what premium unlocks, not an upsell with a call to action. Shared by
// every premium-gated screen (analytics, AI coach, ...) so the visual
// treatment and default copy only live in one place.
export function PremiumGate({
  title = 'Эта функция — часть премиум-подписки',
  description = 'С премиум-подпиской откроются графики роста характеристик и навыков, текстовые инсайты о вашем прогрессе, а скоро — персональный AI-тренер.',
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
    </div>
  )
}
