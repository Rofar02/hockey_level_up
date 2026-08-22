interface SwitchProps {
  checked: boolean
  disabled?: boolean
  onClick?: () => void
}

export function Switch({ checked, disabled = false, onClick }: SwitchProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={onClick}
      className={`relative h-6 w-11 shrink-0 rounded-full border transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
        checked ? 'border-accent-ice bg-accent-ice/40' : 'border-white/20 bg-white/10'
      }`}
    >
      <span
        // left-0 pins the untransformed base position to the button's own
        // left edge -- without it, the browser falls back to this
        // absolutely-positioned span's "static position", which inherits
        // the native <button> UA default of text-align:center and lands
        // well right of 0. translate-x-1/translate-x-[22px] below were
        // written assuming a left:0 baseline, so without this the thumb
        // renders translated *from* an already-centered position and pokes
        // out past the pill's right edge when checked.
        className={`absolute left-0 top-1/2 h-4 w-4 -translate-y-1/2 rounded-full bg-white transition-transform ${
          checked ? 'translate-x-[22px]' : 'translate-x-1'
        }`}
      />
    </button>
  )
}
