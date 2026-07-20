import type { MetaFunction } from 'react-router'

export const meta: MetaFunction = () => [
  { title: 'Page Not Found | GameMetrix' },
  { name: 'robots', content: 'noindex,follow' },
]

export function loader() {
  throw new Response('Not Found', { status: 404 })
}

export default function NotFound() {
  return null
}
