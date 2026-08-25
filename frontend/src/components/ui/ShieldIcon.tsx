// Small heading accent for the auth-flow pages (Login, ForgotPassword,
// ResetPassword) -- same jersey-collar shield silhouette already used for
// the level chip on Home/Profile/TrainingSession, just as a heading icon
// here instead. Shared rather than duplicated since it now appears on
// multiple pages with the exact same markup.
export function ShieldIcon({ size = 19, className }: { size?: number; className?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="#D7EFFF"
      strokeWidth="2"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      <path d="M12 2 L21 6.5 V13 C21 18 17 21.5 12 23 C7 21.5 3 18 3 13 V6.5 Z" />
    </svg>
  )
}
