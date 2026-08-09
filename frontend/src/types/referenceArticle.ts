export interface ReferenceArticleSummary {
  id: string
  title: string
  category: string
}

export interface ReferenceArticleDetail {
  id: string
  title: string
  category: string
  body: string
  image_url: string | null
  created_at: string
}

// Create/update payload (admin CRUD) -- category is a free-form string on
// the backend (no enum), not a fixed set of options.
export interface ReferenceArticleWrite {
  title: string
  category: string
  body: string
}
