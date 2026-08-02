import type { InputHTMLAttributes } from 'react'
import { useId } from 'react'

interface TextFieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string
  numeric?: boolean
}

export function TextField({ label, numeric = false, id, className = '', ...props }: TextFieldProps) {
  const generatedId = useId()
  const inputId = id ?? generatedId

  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={inputId} className="text-sm text-text-secondary">
        {label}
      </label>
      <input
        id={inputId}
        className={`rounded border border-white/10 bg-dark-bg px-3 py-2 text-text-primary placeholder:text-text-secondary/60 focus:border-accent-ice focus:outline-none ${
          numeric ? 'font-mono' : ''
        } ${className}`}
        {...props}
      />
    </div>
  )
}
