interface SkillChipProps {
  label: string
  selected: boolean
  onClick: () => void
}

// Pill shape is a deliberate exception to the system's sharp-corner rule --
// requested explicitly for this spotify-style chip picker.
export function SkillChip({ label, selected, onClick }: SkillChipProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-full border px-4 py-2 text-sm font-medium transition-colors ${
        selected
          ? 'border-accent-ice bg-accent-ice/10 text-accent-ice'
          : 'border-white/15 text-text-secondary hover:border-white/30 hover:text-text-primary'
      }`}
    >
      {label}
    </button>
  )
}
