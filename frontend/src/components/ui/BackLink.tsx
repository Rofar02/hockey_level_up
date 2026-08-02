import { Link } from 'react-router-dom'

export function BackLink({ to = '/' }: { to?: string }) {
  return (
    <Link
      to={to}
      className="inline-flex w-fit items-center gap-1.5 text-sm text-text-secondary transition-colors hover:text-text-primary"
    >
      <i className="ti ti-arrow-left" aria-hidden="true" />
      Назад
    </Link>
  )
}
