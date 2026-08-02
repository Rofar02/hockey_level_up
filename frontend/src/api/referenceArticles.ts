import { apiGet } from './client'
import type { ReferenceArticleDetail, ReferenceArticleSummary } from '../types/referenceArticle'

export function listReferenceArticles(accessToken: string): Promise<ReferenceArticleSummary[]> {
  return apiGet<ReferenceArticleSummary[]>('/reference-articles', accessToken)
}

export function getReferenceArticle(
  articleId: string,
  accessToken: string,
): Promise<ReferenceArticleDetail> {
  return apiGet<ReferenceArticleDetail>(`/reference-articles/${articleId}`, accessToken)
}
