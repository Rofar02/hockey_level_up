// Small heading accent for the auth-flow pages (Login, ForgotPassword,
// ResetPassword) and CoachPage. Jersey-collar shield silhouette -- a
// recurring hockey mark rather than a one-off, so `stroke="currentColor"`
// + a color className (default: the app's usual ice accent, matching every
// existing caller) lets it drop into a persimmon context too (e.g. the
// level-up reveal) without a separate icon.
export function ShieldIcon({ size = 19, className = 'text-accent-ice' }: { size?: number; className?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      <path d="M12 2 L21 6.5 V13 C21 18 17 21.5 12 23 C7 21.5 3 18 3 13 V6.5 Z" />
    </svg>
  )
}
