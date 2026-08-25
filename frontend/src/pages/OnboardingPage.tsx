import { useState } from 'react'
import { AuthWizardShell } from '../components/AuthWizardShell'
import { AssessmentStep } from './onboarding/AssessmentStep'
import { EquipmentStep } from './onboarding/EquipmentStep'
import { SkillsStep } from './onboarding/SkillsStep'

const STEP_LABELS = ['Оборудование', 'Оценка формы', 'Навыки']
const TOTAL_STEPS = STEP_LABELS.length

export function OnboardingPage() {
  const [step, setStep] = useState(1)

  return (
    <AuthWizardShell step={step} totalSteps={TOTAL_STEPS} stepLabel={STEP_LABELS[step - 1]}>
      {step === 1 && <EquipmentStep onNext={() => setStep(2)} />}
      {step === 2 && <AssessmentStep onNext={() => setStep(3)} />}
      {step === 3 && <SkillsStep />}
    </AuthWizardShell>
  )
}
