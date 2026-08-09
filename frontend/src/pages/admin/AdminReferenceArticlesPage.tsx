import { useEffect, useRef, useState } from 'react'
import type { ChangeEvent, FormEvent } from 'react'
import { MarkdownContent } from '../../components/MarkdownContent'
import { AdminLayout } from '../../components/admin/AdminLayout'
import { AdminModal } from '../../components/admin/AdminModal'
import { Button } from '../../components/ui/Button'
import { FormError } from '../../components/ui/FormError'
import { TextField } from '../../components/ui/TextField'
import * as referenceArticlesApi from '../../api/referenceArticles'
import { API_BASE_URL, ApiError } from '../../api/client'
import { useAuth } from '../../hooks/useAuth'
import type {
  ReferenceArticleDetail,
  ReferenceArticleSummary,
  ReferenceArticleWrite,
} from '../../types/referenceArticle'

function formatDate(iso: string): string {
  const date = new Date(iso)
  const day = String(date.getDate()).padStart(2, '0')
  const month = String(date.getMonth() + 1).padStart(2, '0')
  return `${day}.${month}.${date.getFullYear()}`
}

export function AdminReferenceArticlesPage() {
  const { accessToken } = useAuth()

  const [articles, setArticles] = useState<ReferenceArticleSummary[] | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  const [isFormOpen, setIsFormOpen] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)

  useEffect(() => {
    if (accessToken === null) {
      return
    }
    let cancelled = false
    setIsLoading(true)
    referenceArticlesApi
      .listReferenceArticles(accessToken)
      .then((result) => {
        if (!cancelled) {
          setArticles(result)
          setLoadError(null)
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setLoadError(err instanceof ApiError ? err.message : 'Не удалось загрузить справочник.')
        }
      })
      .finally(() => {
        if (!cancelled) {
          setIsLoading(false)
        }
      })
    return () => {
      cancelled = true
    }
  }, [accessToken])

  function openCreateForm() {
    setEditingId(null)
    setIsFormOpen(true)
  }

  function openEditForm(article: ReferenceArticleSummary) {
    setEditingId(article.id)
    setIsFormOpen(true)
  }

  function handleSaved(saved: ReferenceArticleDetail) {
    setArticles((previous) => {
      if (previous === null) {
        return previous
      }
      const summary: ReferenceArticleSummary = {
        id: saved.id,
        title: saved.title,
        category: saved.category,
      }
      const exists = previous.some((item) => item.id === saved.id)
      return exists
        ? previous.map((item) => (item.id === saved.id ? summary : item))
        : [...previous, summary]
    })
  }

  async function handleDelete(article: ReferenceArticleSummary) {
    if (accessToken === null) {
      return
    }
    if (!window.confirm(`Удалить статью «${article.title}»?`)) {
      return
    }
    try {
      await referenceArticlesApi.deleteReferenceArticle(article.id, accessToken)
      setArticles((previous) => previous?.filter((item) => item.id !== article.id) ?? previous)
    } catch (err) {
      window.alert(err instanceof ApiError ? err.message : 'Не удалось удалить статью.')
    }
  }

  const categories = Array.from(new Set((articles ?? []).map((article) => article.category))).sort()

  return (
    <AdminLayout title="Справочник">
      <div className="mb-4 flex justify-end">
        <Button type="button" onClick={openCreateForm}>
          Добавить статью
        </Button>
      </div>

      <FormError message={loadError} />
      {isLoading && <p className="text-sm text-text-secondary">Загрузка...</p>}

      {!isLoading && articles !== null && (
        <div className="overflow-x-auto rounded-md border border-white/10">
          <table className="w-full min-w-[560px] border-collapse text-sm">
            <thead>
              <tr className="border-b border-white/10 bg-white/5 text-left text-text-secondary">
                <th className="px-3 py-2 font-medium">Название</th>
                <th className="px-3 py-2 font-medium">Категория</th>
                <th className="px-3 py-2 font-medium" />
              </tr>
            </thead>
            <tbody>
              {articles.length === 0 && (
                <tr>
                  <td colSpan={3} className="px-3 py-6 text-center text-text-secondary">
                    Пока нет статей.
                  </td>
                </tr>
              )}
              {articles.map((article) => (
                <tr key={article.id} className="border-b border-white/5 hover:bg-white/5">
                  <td className="px-3 py-2 text-text-primary">{article.title}</td>
                  <td className="px-3 py-2 text-text-secondary">{article.category}</td>
                  <td className="px-3 py-2 text-right">
                    <div className="flex justify-end gap-3">
                      <button
                        type="button"
                        onClick={() => openEditForm(article)}
                        className="text-accent-ice hover:underline"
                      >
                        Изменить
                      </button>
                      <button
                        type="button"
                        onClick={() => handleDelete(article)}
                        className="text-accent-persimmon hover:underline"
                      >
                        Удалить
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {isFormOpen && (
        <ArticleFormModal
          articleId={editingId}
          categories={categories}
          onClose={() => setIsFormOpen(false)}
          onSaved={handleSaved}
        />
      )}
    </AdminLayout>
  )
}

function ArticleFormModal({
  articleId,
  categories,
  onClose,
  onSaved,
}: {
  articleId: string | null
  categories: string[]
  onClose: () => void
  onSaved: (article: ReferenceArticleDetail) => void
}) {
  const { accessToken } = useAuth()

  const [article, setArticle] = useState<ReferenceArticleDetail | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [isLoadingArticle, setIsLoadingArticle] = useState(articleId !== null)

  const [title, setTitle] = useState('')
  const [category, setCategory] = useState('')
  const [body, setBody] = useState('')

  const [formError, setFormError] = useState<string | null>(null)
  const [isSaving, setIsSaving] = useState(false)

  const [bodyViewMode, setBodyViewMode] = useState<'edit' | 'preview'>('edit')
  const bodyTextareaRef = useRef<HTMLTextAreaElement>(null)
  const contentImageInputRef = useRef<HTMLInputElement>(null)
  const [isUploadingContentImage, setIsUploadingContentImage] = useState(false)
  const [contentImageError, setContentImageError] = useState<string | null>(null)

  useEffect(() => {
    if (articleId === null || accessToken === null) {
      return
    }
    let cancelled = false
    referenceArticlesApi
      .getReferenceArticle(articleId, accessToken)
      .then((result) => {
        if (cancelled) {
          return
        }
        setArticle(result)
        setTitle(result.title)
        setCategory(result.category)
        setBody(result.body)
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setLoadError(err instanceof ApiError ? err.message : 'Не удалось загрузить статью.')
        }
      })
      .finally(() => {
        if (!cancelled) {
          setIsLoadingArticle(false)
        }
      })
    return () => {
      cancelled = true
    }
  }, [articleId, accessToken])

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (accessToken === null) {
      return
    }
    setFormError(null)

    if (title.trim() === '') {
      setFormError('Название обязательно.')
      return
    }
    if (category.trim() === '') {
      setFormError('Категория обязательна.')
      return
    }
    if (body.trim() === '') {
      setFormError('Содержимое обязательно.')
      return
    }

    const payload: ReferenceArticleWrite = {
      title: title.trim(),
      category: category.trim(),
      body: body.trim(),
    }

    setIsSaving(true)
    try {
      // Same pattern as AdminExercisesPage's exercise form: a successful
      // create switches this modal into "editing the new record" rather
      // than closing, so the image block below can appear immediately
      // instead of forcing a reopen. An update, editing something that
      // already existed, closes as before.
      if (article === null) {
        const created = await referenceArticlesApi.createReferenceArticle(payload, accessToken)
        setArticle(created)
        onSaved(created)
      } else {
        const updated = await referenceArticlesApi.updateReferenceArticle(article.id, payload, accessToken)
        setArticle(updated)
        onSaved(updated)
        onClose()
      }
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : 'Не удалось сохранить статью.')
    } finally {
      setIsSaving(false)
    }
  }

  function handleImageUpdated(updated: ReferenceArticleDetail) {
    setArticle(updated)
    onSaved(updated)
  }

  function insertAtCursor(snippet: string) {
    const textarea = bodyTextareaRef.current
    if (textarea === null) {
      setBody((previous) => `${previous}${snippet}`)
      return
    }
    const start = textarea.selectionStart
    const end = textarea.selectionEnd
    setBody((previous) => `${previous.slice(0, start)}${snippet}${previous.slice(end)}`)
    // The textarea's DOM value hasn't caught up with the new React state
    // yet on this tick -- wait a frame before moving the cursor, otherwise
    // setSelectionRange clamps against the stale (shorter) value.
    requestAnimationFrame(() => {
      textarea.focus()
      const cursor = start + snippet.length
      textarea.setSelectionRange(cursor, cursor)
    })
  }

  async function handleContentImageChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (file === undefined || article === null || accessToken === null) {
      return
    }
    setContentImageError(null)
    setIsUploadingContentImage(true)
    try {
      const { url } = await referenceArticlesApi.uploadReferenceArticleContentImage(
        article.id,
        file,
        accessToken,
      )
      insertAtCursor(`![](${url})`)
    } catch (err) {
      setContentImageError(err instanceof ApiError ? err.message : 'Не удалось загрузить изображение.')
    } finally {
      setIsUploadingContentImage(false)
    }
  }

  return (
    <AdminModal
      title={
        article !== null
          ? `Редактирование: ${article.title}`
          : articleId === null
            ? 'Новая статья'
            : 'Редактирование...'
      }
      onClose={onClose}
    >
      <FormError message={loadError} />
      {isLoadingArticle && <p className="text-sm text-text-secondary">Загрузка...</p>}

      {!isLoadingArticle && (
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <TextField label="Название" value={title} onChange={(event) => setTitle(event.target.value)} maxLength={255} required />

          <div className="flex flex-col gap-1.5">
            <label className="text-sm text-text-secondary" htmlFor="article-category">
              Категория
            </label>
            <input
              id="article-category"
              list="article-category-options"
              value={category}
              onChange={(event) => setCategory(event.target.value)}
              maxLength={100}
              required
              className="rounded border border-white/10 bg-dark-bg px-3 py-2 text-text-primary placeholder:text-text-secondary/60 focus:border-accent-ice focus:outline-none"
            />
            <datalist id="article-category-options">
              {categories.map((value) => (
                <option key={value} value={value} />
              ))}
            </datalist>
          </div>

          <div className="flex flex-col gap-1.5">
            <div className="flex items-center justify-between">
              <label className="text-sm text-text-secondary" htmlFor="article-body">
                Содержимое (Markdown)
              </label>
              <div className="flex items-center gap-3 text-xs">
                <button
                  type="button"
                  onClick={() => setBodyViewMode('edit')}
                  className={
                    bodyViewMode === 'edit'
                      ? 'text-accent-ice'
                      : 'text-text-secondary transition-colors hover:text-text-primary'
                  }
                >
                  Редактировать
                </button>
                <button
                  type="button"
                  onClick={() => setBodyViewMode('preview')}
                  className={
                    bodyViewMode === 'preview'
                      ? 'text-accent-ice'
                      : 'text-text-secondary transition-colors hover:text-text-primary'
                  }
                >
                  Предпросмотр
                </button>
              </div>
            </div>

            {bodyViewMode === 'edit' ? (
              <>
                <div className="flex items-center gap-3">
                  <Button
                    type="button"
                    variant="neutral"
                    onClick={() => contentImageInputRef.current?.click()}
                    isLoading={isUploadingContentImage}
                    disabled={article === null}
                    title={article === null ? 'Сначала сохраните статью' : undefined}
                  >
                    Вставить картинку
                  </Button>
                  <input
                    ref={contentImageInputRef}
                    type="file"
                    accept="image/jpeg,image/png,image/webp"
                    className="hidden"
                    onChange={handleContentImageChange}
                  />
                </div>
                <FormError message={contentImageError} />
                <textarea
                  ref={bodyTextareaRef}
                  id="article-body"
                  value={body}
                  onChange={(event) => setBody(event.target.value)}
                  rows={10}
                  required
                  className="rounded border border-white/10 bg-dark-bg px-3 py-2 font-mono text-sm text-text-primary focus:border-accent-ice focus:outline-none"
                />
                <p className="text-xs text-text-secondary">
                  Поддерживается Markdown: <code># Заголовок</code>, <code>**жирный**</code>,{' '}
                  <code>*курсив*</code>, <code>- список</code>, <code>![](url)</code> — картинка.
                </p>
              </>
            ) : (
              <div className="min-h-[240px] rounded border border-white/10 bg-dark-bg px-3 py-2">
                {body.trim() === '' ? (
                  <p className="text-sm text-text-secondary">Нечего показывать.</p>
                ) : (
                  <MarkdownContent content={body} />
                )}
              </div>
            )}
          </div>

          {article !== null && (
            <p className="text-xs text-text-secondary">Создано: {formatDate(article.created_at)}</p>
          )}

          <FormError message={formError} />
          <Button type="submit" isLoading={isSaving} className="self-start">
            {article === null ? 'Создать' : 'Сохранить'}
          </Button>
        </form>
      )}

      {article !== null && accessToken !== null && (
        <ArticleImageSection article={article} accessToken={accessToken} onUpdated={handleImageUpdated} />
      )}
    </AdminModal>
  )
}

function ArticleImageSection({
  article,
  accessToken,
  onUpdated,
}: {
  article: ReferenceArticleDetail
  accessToken: string
  onUpdated: (article: ReferenceArticleDetail) => void
}) {
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [isUploading, setIsUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    // Reset so selecting the same file again still fires onChange.
    event.target.value = ''
    if (file === undefined) {
      return
    }
    setError(null)
    setIsUploading(true)
    try {
      const updated = await referenceArticlesApi.uploadReferenceArticleImage(
        article.id,
        file,
        accessToken,
      )
      onUpdated(updated)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Не удалось загрузить изображение.')
    } finally {
      setIsUploading(false)
    }
  }

  async function handleRemove() {
    if (!window.confirm('Удалить изображение статьи?')) {
      return
    }
    setError(null)
    try {
      const updated = await referenceArticlesApi.deleteReferenceArticleImage(article.id, accessToken)
      onUpdated(updated)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Не удалось удалить изображение.')
    }
  }

  const imageSrc = article.image_url !== null ? `${API_BASE_URL}${article.image_url}` : null

  return (
    <div className="flex flex-col gap-3 border-t border-white/10 pt-6">
      <h3 className="text-sm font-medium text-text-secondary">Изображение</h3>

      {imageSrc !== null ? (
        <img src={imageSrc} alt="" className="max-h-56 w-full rounded object-cover" />
      ) : (
        <p className="text-sm text-text-secondary">Изображение не загружено.</p>
      )}

      <div className="flex gap-3">
        <Button
          type="button"
          variant="neutral"
          onClick={() => fileInputRef.current?.click()}
          isLoading={isUploading}
        >
          {imageSrc !== null ? 'Заменить' : 'Загрузить'}
        </Button>
        {imageSrc !== null && (
          <Button type="button" variant="neutral" onClick={handleRemove}>
            Удалить
          </Button>
        )}
      </div>
      <input
        ref={fileInputRef}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        className="hidden"
        onChange={handleFileChange}
      />
      <FormError message={error} />
    </div>
  )
}
