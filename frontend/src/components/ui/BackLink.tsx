import { useNavigate } from 'react-router-dom'

// `to` omitted -> real browser-history "back" (navigate(-1)), so this
// returns wherever the user actually came from instead of a fixed route.
// Only pass `to` when landing on one specific path is the intent regardless
// of history (e.g. a deep link that may have no "back" to go to).
export function BackLink({ to }: { to?: string }) {
  const navigate = useNavigate()

  return (
    <button
      type="button"
      onClick={() => (to !== undefined ? navigate(to) : navigate(-1))}
      className="inline-flex w-fit items-center gap-1.5 text-sm text-text-secondary transition-colors hover:text-text-primary"
    >
      <i className="ti ti-arrow-left" aria-hidden="true" />
      Назад
    </button>
  )
}
