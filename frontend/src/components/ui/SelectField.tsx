import type { SelectHTMLAttributes } from 'react'
import { useId } from 'react'

interface SelectFieldProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label: string
  options: { value: string; label: string }[]
  placeholder?: string
}

export function SelectField({ label, options, placeholder, id, className = '', ...props }: SelectFieldProps) {
  const generatedId = useId()
  const inputId = id ?? generatedId

  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={inputId} className="text-sm text-text-secondary">
        {label}
      </label>
      <select
        id={inputId}
        className={`rounded border border-white/10 bg-dark-bg px-3 py-2 text-text-primary focus:border-accent-ice focus:outline-none ${className}`}
        {...props}
      >
        {placeholder !== undefined && <option value="">{placeholder}</option>}
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </div>
  )
}
