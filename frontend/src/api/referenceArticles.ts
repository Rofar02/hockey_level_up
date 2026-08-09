import { apiDeleteAuth, apiGet, apiPatchAuth, apiPostAuth, apiPostMultipartAuth } from './client'
import type {
  ReferenceArticleDetail,
  ReferenceArticleSummary,
  ReferenceArticleWrite,
} from '../types/referenceArticle'

export function listReferenceArticles(accessToken: string): Promise<ReferenceArticleSummary[]> {
  return apiGet<ReferenceArticleSummary[]>('/reference-articles', accessToken)
}

export function getReferenceArticle(
  articleId: string,
  accessToken: string,
): Promise<ReferenceArticleDetail> {
  return apiGet<ReferenceArticleDetail>(`/reference-articles/${articleId}`, accessToken)
}

// -- admin CRUD --

export function createReferenceArticle(
  payload: ReferenceArticleWrite,
  accessToken: string,
): Promise<ReferenceArticleDetail> {
  return apiPostAuth<ReferenceArticleDetail>('/reference-articles', payload, accessToken)
}

export function updateReferenceArticle(
  articleId: string,
  payload: ReferenceArticleWrite,
  accessToken: string,
): Promise<ReferenceArticleDetail> {
  return apiPatchAuth<ReferenceArticleDetail>(`/reference-articles/${articleId}`, payload, accessToken)
}

export function deleteReferenceArticle(articleId: string, accessToken: string): Promise<void> {
  return apiDeleteAuth<void>(`/reference-articles/${articleId}`, accessToken)
}

export function uploadReferenceArticleImage(
  articleId: string,
  file: File,
  accessToken: string,
): Promise<ReferenceArticleDetail> {
  const formData = new FormData()
  formData.append('file', file)
  return apiPostMultipartAuth<ReferenceArticleDetail>(
    `/reference-articles/${articleId}/image`,
    formData,
    accessToken,
  )
}

// Returns the updated article, not void -- DELETE /{id}/image (unlike
// DELETE /{id} above) only clears one field and hands back fresh state.
export function deleteReferenceArticleImage(
  articleId: string,
  accessToken: string,
): Promise<ReferenceArticleDetail> {
  return apiDeleteAuth<ReferenceArticleDetail>(`/reference-articles/${articleId}/image`, accessToken)
}

// Separate from uploadReferenceArticleImage (the one banner) -- this is for
// images referenced inline from `body` markdown via ![](url). Doesn't touch
// the article row; the caller inserts the returned url into the body text
// itself at the cursor position.
export function uploadReferenceArticleContentImage(
  articleId: string,
  file: File,
  accessToken: string,
): Promise<{ url: string }> {
  const formData = new FormData()
  formData.append('file', file)
  return apiPostMultipartAuth<{ url: string }>(
    `/reference-articles/${articleId}/content-image`,
    formData,
    accessToken,
  )
}
