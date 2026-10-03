export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

export class UnauthorizedError extends ApiError {
  constructor() {
    super(401, 'ログインが必要です')
  }
}

type Params = Record<string, string | number | undefined | null>

// Listeners learn about a lost session (401) so the header can offer a login link.
const unauthorizedListeners = new Set<() => void>()
export function onUnauthorized(listener: () => void): () => void {
  unauthorizedListeners.add(listener)
  return () => unauthorizedListeners.delete(listener)
}

function withParams(path: string, params?: Params): string {
  const query = new URLSearchParams()
  Object.entries(params ?? {}).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') query.set(key, String(value))
  })
  const qs = query.toString()
  return qs ? `${path}?${qs}` : path
}

async function parse<T>(response: Response): Promise<T> {
  if (response.status === 401) {
    unauthorizedListeners.forEach((listener) => listener())
    throw new UnauthorizedError()
  }
  const body = await response.json().catch(() => ({}))
  if (!response.ok) throw new ApiError(response.status, body.detail || `HTTP ${response.status}`)
  return body as T
}

export function getJson<T>(path: string, params?: Params): Promise<T> {
  return fetch(withParams(path, params)).then((response) => parse<T>(response))
}

export function postJson<T>(path: string, body: unknown): Promise<T> {
  return fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }).then(
    (response) => parse<T>(response),
  )
}

export function postForm<T>(path: string, form: FormData, params?: Params): Promise<T> {
  Object.entries(params ?? {}).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') form.set(key, String(value))
  })
  return fetch(path, { method: 'POST', body: form }).then((response) => parse<T>(response))
}
