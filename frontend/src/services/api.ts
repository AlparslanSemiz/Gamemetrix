const defaultApiBaseUrl =
  typeof window !== 'undefined' && ['localhost', '127.0.0.1'].includes(window.location.hostname)
    ? 'http://127.0.0.1:8000'
    : ''
const rawApiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? defaultApiBaseUrl

export const API_BASE_URL = rawApiBaseUrl.replace(/\/$/, '')
