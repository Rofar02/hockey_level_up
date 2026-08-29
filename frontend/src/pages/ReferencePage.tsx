import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { BackLink } from '../components/ui/BackLink'
import { CARD_CLASS } from '../components/ui/cardStyle'
import { FormError } from '../components/ui/FormError'
import { IceGlowBackground } from '../components/ui/IceGlowBackground'
import * as referenceArticlesApi from '../api/referenceArticles'
import { ApiError } from '../api/client'
import { useAuth } from '../hooks/useAuth'
import type { ReferenceArticleSummary } from '../types/referenceArticle'

// Known categories get a fitting icon; anything added later (a category is a
// free-form string on the backend, not a fixed enum) falls back to a plain
// book icon rather than needing a frontend change to show up.
const CATEGORY_ICONS: Record<string, string> = {
  экипировка: 'ti-shirt-sport',
  основы: 'ti-flag',
}
const DEFAULT_CATEGORY_ICON = 'ti-book-2'

function groupByCategory(
  articles: ReferenceArticleSummary[],
): { category: string; articles: ReferenceArticleSummary[] }[] {
  const groups: { category: string; articles: ReferenceArticleSummary[] }[] = []
  for (const article of articles) {
    const lastGroup = groups[groups.length - 1]
    if (lastGroup !== undefined && lastGroup.category === article.category) {
      lastGroup.articles.push(article)
    } else {
      groups.push({ category: article.category, articles: [article] })
    }
  }
  return groups
}

export function ReferencePage() {
  const { accessToken } = useAuth()
  const navigate = useNavigate()

  const [articles, setArticles] = useState<ReferenceArticleSummary[] | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)

  useEffect(() => {
    if (accessToken === null) {
      return
    }
    let cancelled = false
    referenceArticlesApi
      .listReferenceArticles(accessToken)
      .then((result) => {
        if (!cancelled) {
          setArticles(result)
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setLoadError(err instanceof ApiError ? err.message : 'Не удалось загрузить справочник.')
        }
      })
    return () => {
      cancelled = true
    }
  }, [accessToken])

  const groups = articles !== null ? groupByCategory(articles) : null

  return (
    <div className="relative min-h-svh overflow-hidden">
      <IceGlowBackground />
      <div className="relative z-[1] mx-auto flex max-w-2xl flex-col gap-6 px-4 py-8">
      <div className="flex flex-col gap-2">
        <BackLink />
        <h1 className="text-xl font-semibold">Справочник</h1>
      </div>

      <FormError message={loadError} />
      {articles === null && loadError === null && (
        <p className="text-sm text-[#8A94A6]">Загрузка...</p>
      )}

      {groups !== null && (
        <div className="flex flex-col gap-6">
          {groups.map((group) => (
            <div key={group.category} className="flex flex-col gap-2">
              {/* Same ice-line divider as MorePage's section headers --
                  one convention for "labelled group of rows" everywhere it
                  shows up (hockey design pass, 2026-08-30). */}
              <div className="flex items-center gap-2 px-1">
                <span className="h-px w-4 shrink-0 bg-accent-ice/60" aria-hidden="true" />
                <span className="shrink-0 text-xs font-semibold uppercase tracking-wide text-[#8A94A6]">
                  {group.category}
                </span>
                <span className="h-px flex-1 bg-white/10" aria-hidden="true" />
              </div>
              <div className="flex flex-col gap-2">
                {group.articles.map((article) => (
                  <button
                    key={article.id}
                    type="button"
                    onClick={() => navigate(`/reference/${article.id}`)}
                    className={`group flex w-full items-center gap-3 p-4 text-left transition-colors hover:border-white/20 ${CARD_CLASS}`}
                  >
                    <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-accent-ice/10">
                      <i
                        className={`ti ${CATEGORY_ICONS[article.category] ?? DEFAULT_CATEGORY_ICON} text-lg text-accent-ice`}
                        aria-hidden="true"
                      />
                    </span>
                    <span className="min-w-0 flex-1 truncate font-medium text-[#F5F7FA]">{article.title}</span>
                    <i
                      className="ti ti-chevron-right shrink-0 text-lg text-[#8A94A6] transition-all group-hover:translate-x-0.5 group-hover:text-accent-ice"
                      aria-hidden="true"
                    />
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
      </div>
    </div>
  )
}
