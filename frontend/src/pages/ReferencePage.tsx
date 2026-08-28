import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { BackLink } from '../components/ui/BackLink'
import { CARD_BORDER } from '../components/ui/cardStyle'
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
            <div key={group.category} className="flex flex-col gap-3">
              <h2 className="text-sm font-medium text-[#8A94A6]">{group.category}</h2>
              <div className="flex flex-col gap-2">
                {group.articles.map((article) => (
                  <button
                    key={article.id}
                    type="button"
                    onClick={() => navigate(`/reference/${article.id}`)}
                    className={`flex items-center gap-3 rounded-md ${CARD_BORDER} bg-dark-card p-4 text-left transition-colors hover:border-white/20`}
                  >
                    <i
                      className={`ti ${CATEGORY_ICONS[article.category] ?? DEFAULT_CATEGORY_ICON} text-xl text-accent-ice`}
                      aria-hidden="true"
                    />
                    <span className="font-medium text-[#F5F7FA]">{article.title}</span>
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
