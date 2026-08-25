import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { AuthWizardShell } from '../components/AuthWizardShell'
import * as authApi from '../api/auth'
import { ApiError } from '../api/client'
import { useAuth } from '../hooks/useAuth'
import { AccountStep } from './register/AccountStep'
import { PhysicalStep } from './register/PhysicalStep'
import { PlayerStep } from './register/PlayerStep'
import type { Position } from '../types/user'

const STEP_LABELS = ['Аккаунт', 'Игрок', 'Физические данные']
const TOTAL_STEPS = STEP_LABELS.length

function toOptionalNumber(value: string): number | undefined {
  if (value.trim() === '') {
    return undefined
  }
  const parsed = Number(value)
  return Number.isNaN(parsed) ? undefined : parsed
}

// Real 3-step wizard (2026-08-25 RPG-redesign implementation), replacing
// the old single long form -- same fields, same final handleSubmit logic,
// just regrouped into steps and given the same AuthWizardShell as
// OnboardingPage so the two flows read as one system instead of the old
// mismatch (a dense one-screen form immediately followed by a clean
// step-by-step onboarding).
export function RegisterPage() {
  const navigate = useNavigate()
  const { login } = useAuth()

  const [step, setStep] = useState(1)

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [lastName, setLastName] = useState('')
  const [firstName, setFirstName] = useState('')
  const [jerseyNumber, setJerseyNumber] = useState('')
  const [height, setHeight] = useState('')
  const [weight, setWeight] = useState('')
  const [age, setAge] = useState('')
  const [position, setPosition] = useState('')
  const [yearsOfExperience, setYearsOfExperience] = useState('')
  // Never pre-checked -- the user must actively opt in on every visit to
  // this form, not just once ever (a fresh page load always starts false).
  const [privacyConsent, setPrivacyConsent] = useState(false)

  const [error, setError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setError(null)

    const parsedJerseyNumber = Number(jerseyNumber.trim())
    if (
      jerseyNumber.trim() === '' ||
      !Number.isInteger(parsedJerseyNumber) ||
      parsedJerseyNumber < 0 ||
      parsedJerseyNumber > 99
    ) {
      setError('Укажите игровой номер — целое число от 0 до 99.')
      return
    }

    setIsSubmitting(true)
    try {
      await authApi.register({
        email,
        password,
        last_name: lastName,
        first_name: firstName,
        jersey_number: parsedJerseyNumber,
        height: toOptionalNumber(height),
        weight: toOptionalNumber(weight),
        age: toOptionalNumber(age),
        position: position === '' ? undefined : (position as Position),
        years_of_experience: toOptionalNumber(yearsOfExperience),
        privacy_consent: privacyConsent,
      })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Не удалось зарегистрироваться. Попробуйте ещё раз.')
      setIsSubmitting(false)
      return
    }

    // /auth/register only creates the account, it doesn't return a token
    // (unlike /auth/login) -- reuse the same email/password right away so
    // the user isn't sent to the login screen to type what they just typed.
    try {
      await login(email, password)
      navigate('/', { replace: true })
    } catch {
      // Account exists at this point; only the auto-login itself failed
      // (e.g. a transient network hiccup) -- let them log in manually
      // instead of stranding them on this form.
      navigate('/login', { replace: true })
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <AuthWizardShell step={step} totalSteps={TOTAL_STEPS} stepLabel={STEP_LABELS[step - 1]}>
      {step === 1 && (
        <AccountStep
          email={email}
          setEmail={setEmail}
          password={password}
          setPassword={setPassword}
          onNext={() => setStep(2)}
        />
      )}
      {step === 2 && (
        <PlayerStep
          lastName={lastName}
          setLastName={setLastName}
          firstName={firstName}
          setFirstName={setFirstName}
          jerseyNumber={jerseyNumber}
          setJerseyNumber={setJerseyNumber}
          position={position}
          setPosition={setPosition}
          onNext={() => setStep(3)}
          onBack={() => setStep(1)}
        />
      )}
      {step === 3 && (
        <PhysicalStep
          height={height}
          setHeight={setHeight}
          weight={weight}
          setWeight={setWeight}
          age={age}
          setAge={setAge}
          yearsOfExperience={yearsOfExperience}
          setYearsOfExperience={setYearsOfExperience}
          privacyConsent={privacyConsent}
          setPrivacyConsent={setPrivacyConsent}
          error={error}
          isSubmitting={isSubmitting}
          onSubmit={handleSubmit}
          onBack={() => setStep(2)}
        />
      )}

      <p className="mt-6 text-sm text-text-secondary">
        Уже есть аккаунт?{' '}
        <Link to="/login" className="text-accent-ice hover:underline">
          Войти
        </Link>
      </p>
    </AuthWizardShell>
  )
}
