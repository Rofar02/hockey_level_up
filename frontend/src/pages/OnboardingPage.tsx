import { useState } from 'react'
import { Card } from '../components/ui/Card'
import { AssessmentStep } from './onboarding/AssessmentStep'
import { EquipmentStep } from './onboarding/EquipmentStep'
import { SkillsStep } from './onboarding/SkillsStep'

const STEP_LABELS = ['Оборудование', 'Оценка формы', 'Навыки']
const TOTAL_STEPS = STEP_LABELS.length

export function OnboardingPage() {
  const [step, setStep] = useState(1)

  return (
    <div className="relative flex min-h-svh items-center justify-center overflow-hidden px-4 py-10">
      <div className="absolute inset-0 bg-[url('/images/arena-bg.webp')] bg-cover bg-center" />
      <div className="absolute inset-0 bg-dark-bg/80" />
      <Card className="relative w-full max-w-2xl">
        <div className="mb-8">
          <p className="mb-2 text-sm text-text-secondary">
            Шаг {step} из {TOTAL_STEPS} — {STEP_LABELS[step - 1]}
          </p>
          <div className="flex gap-1.5">
            {STEP_LABELS.map((label, index) => (
              <div
                key={label}
                className={`h-1.5 flex-1 rounded ${index + 1 <= step ? 'bg-accent-ice' : 'bg-white/10'}`}
              />
            ))}
          </div>
        </div>

        {step === 1 && <EquipmentStep onNext={() => setStep(2)} />}
        {step === 2 && <AssessmentStep onNext={() => setStep(3)} />}
        {step === 3 && <SkillsStep />}
      </Card>
    </div>
  )
}
