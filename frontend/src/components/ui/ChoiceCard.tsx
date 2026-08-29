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
      className={`relative flex-1 rounded-md border p-5 text-left transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
        selected
          ? 'border-accent-ice bg-accent-ice/10'
          : 'border-white/5 bg-dark-card hover:border-white/20'
      }`}
    >
      {/* The border/tint alone read as "which one is lit up" without
          answering "is this actually my choice" at a glance -- a check
          mark makes the selected state legible the same way TodayCard's
          "Выполнено" pill does elsewhere (hockey design pass, 2026-08-30). */}
      {selected && (
        <i
          className="ti ti-circle-check absolute right-3 top-3 text-lg text-accent-ice"
          aria-hidden="true"
        />
      )}
      <p className="pr-6 font-medium text-text-primary">{title}</p>
      <p className="mt-1 text-sm text-text-secondary">{description}</p>
    </button>
  )
}
