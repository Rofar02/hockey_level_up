import { CARD_CLASS } from './cardStyle'

// Loading placeholders (2026-10-04): silhouettes shaped like the content
// they stand in for, so a page shows its full layout at once and nothing
// jumps when the data lands -- instead of a lone "Загрузка..." line.
// The pulse is skipped for players who ask for reduced motion.

export function SkeletonBlock({ className = '' }: { className?: string }) {
  return <div className={`rounded bg-white/[0.06] motion-safe:animate-pulse ${className}`} aria-hidden="true" />
}

function SkeletonCard({ className = '', children }: { className?: string; children?: React.ReactNode }) {
  return <div className={`flex flex-col gap-3 p-4 ${CARD_CLASS} ${className}`}>{children}</div>
}

// One screen-reader announcement per page, the shapes themselves are hidden.
function Busy({ children }: { children: React.ReactNode }) {
  return (
    <div role="status" aria-label="Загрузка" className="flex flex-col gap-4">
      {children}
    </div>
  )
}

export function HomeSkeleton() {
  return (
    <Busy>
      <SkeletonCard>
        <SkeletonBlock className="h-3 w-24" />
        <SkeletonBlock className="h-7 w-2/3" />
        <SkeletonBlock className="h-4 w-1/2" />
        <SkeletonBlock className="mt-2 h-12 w-full rounded-md" />
      </SkeletonCard>
      <SkeletonCard>
        <SkeletonBlock className="h-3 w-28" />
        <SkeletonBlock className="h-4 w-full" />
        <SkeletonBlock className="h-4 w-4/5" />
      </SkeletonCard>
      <SkeletonCard>
        <SkeletonBlock className="h-3 w-32" />
        <SkeletonBlock className="h-16 w-full rounded-md" />
      </SkeletonCard>
    </Busy>
  )
}

export function ProfileSkeleton() {
  return (
    <Busy>
      <div className="mx-auto w-full max-w-[360px]">
        <SkeletonBlock className="h-[484px] w-full rounded-2xl" />
      </div>
      <div className="grid grid-cols-2 gap-3">
        {[0, 1, 2, 3].map((index) => (
          <SkeletonCard key={index}>
            <SkeletonBlock className="h-5 w-5" />
            <SkeletonBlock className="h-4 w-2/3" />
            <SkeletonBlock className="h-3 w-4/5" />
          </SkeletonCard>
        ))}
      </div>
    </Busy>
  )
}

export function WeekSkeleton() {
  return (
    <Busy>
      {/* Same shape as a day row: the date dot on the left, the day card. */}
      {[0, 1, 2, 3, 4, 5, 6].map((index) => (
        <div key={index} className="flex items-center gap-3">
          <SkeletonBlock className="h-9 w-9 shrink-0 rounded-full" />
          <div className={`flex flex-1 flex-col gap-2 p-4 ${CARD_CLASS}`}>
            <div className="flex items-center justify-between">
              <SkeletonBlock className="h-4 w-24" />
              <SkeletonBlock className="h-4 w-16" />
            </div>
            <SkeletonBlock className="h-3 w-3/5" />
          </div>
        </div>
      ))}
    </Busy>
  )
}

export function ListSkeleton({ rows = 3 }: { rows?: number }) {
  return (
    <Busy>
      {Array.from({ length: rows }, (_, index) => (
        <SkeletonCard key={index}>
          <SkeletonBlock className="h-4 w-1/2" />
          <SkeletonBlock className="h-3 w-3/4" />
          <SkeletonBlock className="h-3 w-2/5" />
        </SkeletonCard>
      ))}
    </Busy>
  )
}

export function ChatSkeleton() {
  return (
    <div role="status" aria-label="Загрузка" className="flex flex-col gap-4">
      <div className="flex items-end gap-2">
        <SkeletonBlock className="h-9 w-9 rounded-full" />
        <SkeletonBlock className="h-16 w-3/5 rounded-md" />
      </div>
      <div className="flex justify-end">
        <SkeletonBlock className="h-10 w-2/5 rounded-md" />
      </div>
      <div className="flex items-end gap-2">
        <SkeletonBlock className="h-9 w-9 rounded-full" />
        <SkeletonBlock className="h-24 w-4/6 rounded-md" />
      </div>
    </div>
  )
}
