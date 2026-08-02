interface CheckboxProps {
  checked: boolean
  disabled?: boolean
  onClick?: () => void
}

export function Checkbox({ checked, disabled = false, onClick }: CheckboxProps) {
  return (
    <button
      type="button"
      role="checkbox"
      aria-checked={checked}
      disabled={disabled}
      onClick={onClick}
      className={`flex h-5 w-5 shrink-0 items-center justify-center rounded border transition-colors disabled:cursor-not-allowed ${
        checked
          ? 'border-accent-ice bg-accent-ice/20 text-accent-ice'
          : 'border-white/20 text-transparent hover:border-white/40'
      }`}
    >
      <svg viewBox="0 0 16 16" className="h-3 w-3 fill-none stroke-current stroke-[2.5]">
        <path d="M3 8l3 3 7-7" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </button>
  )
}
