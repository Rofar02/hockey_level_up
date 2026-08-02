import type { ButtonHTMLAttributes } from 'react'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'neutral'
  isLoading?: boolean
}

const VARIANT_CLASSES: Record<NonNullable<ButtonProps['variant']>, string> = {
  // The one warm accent, reserved for the main CTA on a screen (start a
  // workout, save, level-up) -- never mixed with the ice accent.
  primary: 'bg-accent-persimmon text-dark-bg hover:bg-accent-persimmon/90',
  neutral: 'border border-white/15 text-text-primary hover:bg-white/5',
}

export function Button({
  variant = 'primary',
  isLoading = false,
  disabled,
  className = '',
  children,
  ...props
}: ButtonProps) {
  return (
    <button
      className={`rounded px-4 py-2.5 font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${VARIANT_CLASSES[variant]} ${className}`}
      disabled={disabled || isLoading}
      {...props}
    >
      {isLoading ? 'Загрузка...' : children}
    </button>
  )
}
