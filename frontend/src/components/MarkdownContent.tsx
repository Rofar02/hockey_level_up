import ReactMarkdown from 'react-markdown'
import type { Components } from 'react-markdown'
import { API_BASE_URL } from '../api/client'

// Content images are inserted as relative paths returned by our own upload
// endpoint (/static/reference-articles/content/...) -- those need the API
// origin prefixed, same as every other uploaded-image src in this app.
// Absolute URLs (an admin pasting an external image link) pass through
// unchanged.
function resolveImageSrc(src: string): string {
  return src.startsWith('/') ? `${API_BASE_URL}${src}` : src
}

// Tailwind's preflight strips default heading/list/link styling, so
// react-markdown's default output reads as plain, hierarchy-less text
// without these overrides. Shared between the admin form's preview toggle
// and the public article page so both render body markdown identically.
const MARKDOWN_COMPONENTS: Components = {
  h1: ({ children }) => <h2 className="text-lg font-semibold text-text-primary">{children}</h2>,
  h2: ({ children }) => <h3 className="text-base font-semibold text-text-primary">{children}</h3>,
  h3: ({ children }) => <h4 className="text-sm font-semibold text-text-primary">{children}</h4>,
  p: ({ children }) => <p className="text-sm leading-relaxed text-text-primary">{children}</p>,
  strong: ({ children }) => <strong className="font-semibold text-text-primary">{children}</strong>,
  em: ({ children }) => <em className="italic">{children}</em>,
  ul: ({ children }) => (
    <ul className="list-disc space-y-1 pl-5 text-sm text-text-primary">{children}</ul>
  ),
  ol: ({ children }) => (
    <ol className="list-decimal space-y-1 pl-5 text-sm text-text-primary">{children}</ol>
  ),
  li: ({ children }) => <li>{children}</li>,
  a: ({ children, href }) => (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="text-accent-ice underline hover:no-underline"
    >
      {children}
    </a>
  ),
  img: ({ src, alt }) => (
    <img
      src={typeof src === 'string' ? resolveImageSrc(src) : undefined}
      alt={alt ?? ''}
      className="w-full rounded-md"
    />
  ),
}

export function MarkdownContent({ content }: { content: string }) {
  return (
    <div className="flex flex-col gap-4">
      <ReactMarkdown components={MARKDOWN_COMPONENTS}>{content}</ReactMarkdown>
    </div>
  )
}
