interface ChoiceCardProps {
  title: string
  description: string
  selected?: boolean
  disabled?: boolean
  onClick: () => void
}

export function ChoiceCard({
  title,
  description,
  selected = false,
  disabled = false,
  onClick,
}: ChoiceCardProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`flex-1 rounded-md border p-5 text-left transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
        selected
          ? 'border-accent-ice bg-accent-ice/10'
          : 'border-white/5 bg-dark-card hover:border-white/20'
      }`}
    >
      <p className="font-medium text-text-primary">{title}</p>
      <p className="mt-1 text-sm text-text-secondary">{description}</p>
    </button>
  )
}
