import { Link, useParams } from 'react-router-dom'
import { BackLink } from '../components/ui/BackLink'
import { EmptyState } from '../components/ui/EmptyState'
import { IceGlowBackground } from '../components/ui/IceGlowBackground'
import { GUIDE_BY_ID, GUIDE_CHAPTERS } from '../content/guide'
import type { GuideChapter } from '../content/guide'

const GROUPS: GuideChapter['group'][] = ['Главное', 'Вместе', 'Тренер']

// "Как пользоваться" (2026-10-08): /guide lists the chapters, /guide/:id
// shows one. Static content (content/guide.ts), reached from Справочник and
// from every "?" sheet's "Подробнее".
export function GuidePage() {
  const { chapterId } = useParams<{ chapterId: string }>()
  if (chapterId !== undefined) {
    return <GuideChapterView chapter={GUIDE_BY_ID[chapterId]} />
  }

  return (
    <Shell>
      <h1 className="font-display text-2xl font-semibold uppercase tracking-wide">Как пользоваться</h1>
      <p className="-mt-3 text-sm leading-relaxed text-text-secondary">
        Короткие главы. Начните с первой — остальное по интересу.
      </p>
      {GROUPS.map((group) => (
        <section key={group} className="flex flex-col gap-1.5">
          <h2 className="mb-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-text-secondary">{group}</h2>
          {GUIDE_CHAPTERS.filter((chapter) => chapter.group === group).map((chapter, index) => (
            <Link
              key={chapter.id}
              to={`/guide/${chapter.id}`}
              className={`flex min-h-16 items-center gap-3.5 rounded-xl bg-dark-card px-3.5 py-2 transition-colors hover:bg-white/[0.04] ${
                group === 'Главное' && index === 0 ? 'border border-accent-ice/25' : ''
              }`}
            >
              <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-accent-ice/10">
                <i className={`ti ${chapter.icon} text-xl text-accent-ice`} aria-hidden="true" />
              </span>
              <span className="flex min-w-0 flex-1 flex-col">
                <span className="text-sm font-semibold text-text-primary">{chapter.title}</span>
                <span className="text-xs text-text-secondary">{chapter.subtitle}</span>
              </span>
              <span className="whitespace-nowrap text-[11px] text-text-secondary">{chapter.minutes} мин</span>
            </Link>
          ))}
        </section>
      ))}
    </Shell>
  )
}

function GuideChapterView({ chapter }: { chapter: GuideChapter | undefined }) {
  if (chapter === undefined) {
    return (
      <Shell>
        <EmptyState icon="ti-book" title="Глава не найдена" hint="Откройте список глав «Как пользоваться»" />
      </Shell>
    )
  }
  const index = GUIDE_CHAPTERS.indexOf(chapter)
  const next = GUIDE_CHAPTERS[index + 1]
  return (
    <Shell>
      <div className="flex flex-col gap-1">
        <span className="text-[11px] font-semibold uppercase tracking-[0.14em] text-accent-persimmon">
          Как пользоваться · {chapter.minutes} мин
        </span>
        <h1 className="text-2xl font-semibold leading-tight">{chapter.title}</h1>
      </div>
      {chapter.sections.map((section) => (
        <section key={section.heading} className="flex flex-col gap-2">
          <h2 className="text-base font-semibold text-text-primary">{section.heading}</h2>
          {section.paragraphs.map((paragraph) => (
            <p key={paragraph} className="text-[15px] leading-relaxed text-[#C9D2E0]">
              {paragraph}
            </p>
          ))}
        </section>
      ))}
      {next !== undefined && (
        <Link
          to={`/guide/${next.id}`}
          className="mt-2 flex min-h-14 items-center gap-3 rounded-xl border border-white/10 bg-dark-card px-4 transition-colors hover:bg-white/[0.04]"
        >
          <span className="flex flex-1 flex-col">
            <span className="text-[11px] uppercase tracking-wider text-text-secondary">Дальше</span>
            <span className="text-sm font-semibold">{next.title}</span>
          </span>
          <i className="ti ti-arrow-right text-accent-ice" aria-hidden="true" />
        </Link>
      )}
    </Shell>
  )
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="relative min-h-svh overflow-hidden">
      <IceGlowBackground />
      <div className="relative z-[1] mx-auto flex max-w-2xl flex-col gap-5 px-4 pb-[var(--bottom-nav-space)] pt-10">
        <BackLink />
        {children}
      </div>
    </div>
  )
}
