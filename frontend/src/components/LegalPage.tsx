import type { ReactNode } from 'react'
import './LegalPage.css'

export const IMPRESSUM_FULL_URL = 'https://alparslansemiz.com/de/impressum/'
export const CONTROLLER_EMAIL = 'impressum@alparslansemiz.com'

export function LegalPage({
  children,
  lang = 'en',
  title,
}: {
  children: ReactNode
  lang?: 'en' | 'de'
  title: string
}) {
  return (
    <main id="main-content" className="legal-shell" lang={lang}>
      <article className="legal-page">
        <a className="legal-back" href="/">GameMetrix</a>
        <h1>{title}</h1>
        {children}
      </article>
    </main>
  )
}
