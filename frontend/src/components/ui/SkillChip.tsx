interface SkillChipProps {
  label: string
  selected: boolean
  disabled?: boolean
  onClick: () => void
}

// Pill shape is a deliberate exception to the system's sharp-corner rule --
// requested explicitly for this spotify-style chip picker.
export function SkillChip({ label, selected, disabled = false, onClick }: SkillChipProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`rounded-full border px-4 py-2 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${
        selected
          ? 'border-accent-ice bg-accent-ice/10 text-accent-ice'
          : 'border-white/15 text-text-secondary hover:border-white/30 hover:text-text-primary'
      }`}
    >
      {label}
    </button>
  )
}

// A skill locked by User.level: shown in the same picker grid as SkillChip
// (not hidden -- the whole point is to preview what unlocks later), but
// not a toggle at all, so it's a plain non-interactive element rather than
// a disabled button.
export function LockedSkillChip({ label, requiredLevel }: { label: string; requiredLevel: number }) {
  return (
    <div className="flex flex-col items-start gap-0.5 rounded-md border border-white/10 px-3 py-1.5 text-text-secondary/50">
      <span className="flex items-center gap-1.5 text-sm font-medium">
        <i className="ti ti-lock text-xs" aria-hidden="true" />
        {label}
      </span>
      <span className="text-xs">Доступно с уровня {requiredLevel}</span>
    </div>
  )
}
