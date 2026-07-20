const INTERNAL_API_BASE_URL = (
  process.env.INTERNAL_API_BASE_URL
  ?? process.env.VITE_API_BASE_URL
  ?? 'http://127.0.0.1:8000'
).replace(/\/$/, '')

export class BackendResponseError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'BackendResponseError'
    this.status = status
  }
}

export async function fetchBackend<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${INTERNAL_API_BASE_URL}${path}`, {
    ...init,
    signal: init?.signal ?? AbortSignal.timeout(10_000),
    headers: {
      Accept: 'application/json',
      ...init?.headers,
    },
  })
  if (!response.ok) {
    throw new BackendResponseError(response.status, `Backend returned ${response.status}`)
  }
  return response.json() as Promise<T>
}
