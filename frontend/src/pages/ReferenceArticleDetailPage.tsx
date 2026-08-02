import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { BackLink } from '../components/ui/BackLink'
import { FormError } from '../components/ui/FormError'
import * as referenceArticlesApi from '../api/referenceArticles'
import { ApiError } from '../api/client'
import { useAuth } from '../hooks/useAuth'
import type { ReferenceArticleDetail } from '../types/referenceArticle'

export function ReferenceArticleDetailPage() {
  const { articleId } = useParams<{ articleId: string }>()
  const { accessToken } = useAuth()

  const [article, setArticle] = useState<ReferenceArticleDetail | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)

  useEffect(() => {
    if (accessToken === null || articleId === undefined) {
      return
    }
    let cancelled = false
    referenceArticlesApi
      .getReferenceArticle(articleId, accessToken)
      .then((result) => {
        if (!cancelled) {
          setArticle(result)
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setLoadError(err instanceof ApiError ? err.message : 'Не удалось загрузить статью.')
        }
      })
    return () => {
      cancelled = true
    }
  }, [accessToken, articleId])

  return (
    <div className="mx-auto flex min-h-svh max-w-2xl flex-col gap-6 px-4 py-8">
      <BackLink to="/reference" />

      <FormError message={loadError} />
      {article === null && loadError === null && (
        <p className="text-sm text-text-secondary">Загрузка...</p>
      )}

      {article !== null && (
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <span className="w-fit rounded-full border border-white/15 px-3 py-1 text-xs text-text-secondary">
              {article.category}
            </span>
            <h1 className="text-xl font-semibold">{article.title}</h1>
          </div>
          <div className="flex flex-col gap-4">
            {article.body.split('\n\n').map((paragraph, index) => (
              <p key={index} className="text-sm leading-relaxed text-text-secondary">
                {paragraph}
              </p>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
