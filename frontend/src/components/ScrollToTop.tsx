import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'

// React Router doesn't reset scroll position on navigation the way a
// classic multi-page site does -- without this, pushing a new route while
// scrolled down (e.g. leaving a long list mid-scroll) lands the new page
// already scrolled, forcing an extra manual scroll-up, most noticeable on
// mobile. Mounted once in App, above <Routes>, so every route change
// (not just Teams) resets to the top.
export function ScrollToTop() {
  const { pathname } = useLocation()

  useEffect(() => {
    window.scrollTo(0, 0)
  }, [pathname])

  return null
}
