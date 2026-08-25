import type { ReactNode } from 'react'
import { Card } from './ui/Card'

// Shared visual shell for the two multi-step auth/onboarding flows
// (OnboardingPage, RegisterPage) -- arena background + logo + card +
// progress dots. Extracted so the two pages can't drift apart on this
// (previously OnboardingPage had its own copy and RegisterPage was a
// single long form with no shell at all).
export function AuthWizardShell({
  step,
  totalSteps,
  stepLabel,
  children,
}: {
  step: number
  totalSteps: number
  stepLabel: string
  children: ReactNode
}) {
  return (
    <div className="relative flex min-h-svh flex-col items-center justify-center overflow-hidden px-4 py-10">
      <div className="absolute inset-0 bg-[url('/images/arena-bg.webp')] bg-cover bg-center" />
      <div className="absolute inset-0 bg-dark-bg/80" />
      <img
        src="/images/logo.webp"
        alt="IceLevel"
        className="relative mb-6 w-full max-w-[220px] opacity-80"
      />
      <Card className="relative w-full max-w-2xl">
        <div className="mb-8">
          <p className="mb-2 text-sm text-text-secondary">
            Шаг {step} из {totalSteps} — {stepLabel}
          </p>
          <div className="flex gap-1.5">
            {Array.from({ length: totalSteps }, (_, index) => (
              <div
                key={index}
                className={`h-1.5 flex-1 rounded ${index + 1 <= step ? 'bg-accent-ice' : 'bg-white/10'}`}
              />
            ))}
          </div>
        </div>

        {children}
      </Card>
    </div>
  )
}
