import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { HELP_TOPICS } from '../content/help'
import type { HelpTopicKey } from '../content/help'
import { Button } from './ui/Button'
import { Modal } from './ui/Modal'

// The "?" next to a main screen's title (2026-10-08): the same short "Как
// это работает" sheet everywhere -- three points -- with "Подробнее" into
// the matching "Как пользоваться" chapter.
export function HelpButton({ topic }: { topic: HelpTopicKey }) {
  const [open, setOpen] = useState(false)
  const navigate = useNavigate()
  const help = HELP_TOPICS[topic]

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label="Как это работает"
        className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full border border-accent-ice/35 bg-accent-ice/10 text-accent-ice transition-colors hover:bg-accent-ice/20"
      >
        <i className="ti ti-help text-xl" aria-hidden="true" />
      </button>
      {open && (
        <Modal title={help.title} onClose={() => setOpen(false)}>
          <div className="flex flex-col gap-4">
            <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-accent-persimmon">
              Как это работает
            </p>
            <ol className="flex flex-col gap-4">
              {help.points.map((point, index) => (
                <li key={point.title} className="flex gap-3.5">
                  <span className="w-5 shrink-0 font-display text-xl font-semibold leading-tight text-accent-ice">
                    {index + 1}
                  </span>
                  <span className="flex flex-col gap-0.5">
                    <span className="text-[15px] font-semibold text-text-primary">{point.title}</span>
                    <span className="text-sm leading-relaxed text-text-secondary">{point.text}</span>
                  </span>
                </li>
              ))}
            </ol>
            <div className="mt-1 flex gap-2">
              <Button
                variant="neutral"
                onClick={() => {
                  setOpen(false)
                  navigate(`/guide/${help.guide}`)
                }}
                className="flex-1"
              >
                Подробнее
              </Button>
              <Button onClick={() => setOpen(false)} className="flex-1">
                Понятно
              </Button>
            </div>
          </div>
        </Modal>
      )}
    </>
  )
}
