import { useEffect, useState } from 'react'

// The number in the middle is a real text input, not just a +/- readout
// (2026-08-29: "хотелось бы добавить возможность писать вес и подходы
// вручную") -- tapping it opens the device's numeric keyboard. Local `text`
// state so a mid-edit value like "7." or an empty field while typing isn't
// immediately clobbered by re-deriving from the numeric `value` prop; it
// resyncs from `value` on blur/Enter (commit) and whenever `value` changes
// for a reason other than this input itself (+/- taps, a fresh suggestion
// loading in) via the effect below.
export function Stepper({
  value,
  unit,
  step,
  min = 0,
  disabled,
  ariaLabel,
  onChange,
}: {
  value: number
  unit?: string
  step: number
  min?: number
  disabled?: boolean
  // Overrides the default aria-label (which assumes this is either a
  // weight or a reps stepper) -- needed for other honest-fact fields like
  // TimerPlayer's actual-seconds-performed stepper.
  ariaLabel?: string
  onChange: (value: number) => void
}) {
  const [text, setText] = useState(String(value))

  useEffect(() => {
    setText(String(value))
  }, [value])

  function commit() {
    const parsed = Number(text.replace(',', '.'))
    if (!Number.isFinite(parsed)) {
      setText(String(value))
      return
    }
    const clamped = Math.max(min, parsed)
    setText(String(clamped))
    if (clamped !== value) {
      onChange(clamped)
    }
  }

  return (
    <div className="flex shrink-0 items-center gap-2">
      <button
        type="button"
        onClick={() => onChange(Math.max(min, value - step))}
        disabled={disabled}
        aria-label="Меньше"
        className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-white/10 text-text-primary disabled:opacity-50"
      >
        <i className="ti ti-minus text-sm" aria-hidden="true" />
      </button>
      <span className="flex items-baseline">
        <input
          type="text"
          inputMode="decimal"
          value={text}
          disabled={disabled}
          onChange={(event) => setText(event.target.value)}
          onBlur={commit}
          onKeyDown={(event) => {
            if (event.key === 'Enter') {
              commit()
              event.currentTarget.blur()
            }
          }}
          aria-label={ariaLabel ?? (unit !== undefined ? `Вес, ${unit}` : 'Количество повторений')}
          className="w-9 shrink-0 bg-transparent text-center font-display text-lg font-semibold text-text-primary outline-none disabled:opacity-50"
        />
        {unit !== undefined && <span className="text-xs font-sans text-text-secondary">{unit}</span>}
      </span>
      <button
        type="button"
        onClick={() => onChange(value + step)}
        disabled={disabled}
        aria-label="Больше"
        className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-white/10 text-text-primary disabled:opacity-50"
      >
        <i className="ti ti-plus text-sm" aria-hidden="true" />
      </button>
    </div>
  )
}
