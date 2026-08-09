import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { MarkdownContent } from '../components/MarkdownContent'
import { BackLink } from '../components/ui/BackLink'
import { FormError } from '../components/ui/FormError'
import { IceGlowBackground } from '../components/ui/IceGlowBackground'
import * as referenceArticlesApi from '../api/referenceArticles'
import { API_BASE_URL, ApiError } from '../api/client'
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
    <div className="relative min-h-svh overflow-hidden">
      <IceGlowBackground />
      <div className="relative z-[1] mx-auto flex max-w-2xl flex-col gap-6 px-4 py-8">
      <BackLink to="/reference" />

      <FormError message={loadError} />
      {article === null && loadError === null && (
        <p className="text-sm text-[#8A94A6]">Загрузка...</p>
      )}

      {article !== null && (
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <span className="w-fit rounded-full border border-white/15 px-3 py-1 text-xs text-[#8A94A6]">
              {article.category}
            </span>
            <h1 className="text-xl font-semibold">{article.title}</h1>
          </div>
          {article.image_url !== null && (
            <img
              src={`${API_BASE_URL}${article.image_url}`}
              alt=""
              className="w-full rounded-md object-cover"
            />
          )}
          <MarkdownContent content={article.body} />
        </div>
      )}
      </div>
    </div>
  )
}
