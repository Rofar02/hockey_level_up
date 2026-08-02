import type { ReactNode } from 'react'

export function Card({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <div className={`rounded-md border border-white/5 bg-dark-card p-8 ${className}`}>
      {children}
    </div>
  )
}
