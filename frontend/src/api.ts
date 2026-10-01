// Where the backend is. Override with VITE_API_URL when it isn't on the
// default port, e.g. VITE_API_URL=http://localhost:8010 npm run dev
const BASE: string = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

export const API_URL = `${BASE}/api`
export const WS_URL = `${BASE.replace(/^http/, 'ws')}/ws/telemetry`

export type Outcome<T> = { ok: true; data: T } | { ok: false; error: string }

// FastAPI reports a refused request as { detail }, where detail is a sentence
// for our own checks and a list of field errors for out-of-range values.
async function errorText(response: Response) {
  const body = await response.json().catch(() => null)
  const detail = body?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail.map(d => `${d.loc?.[d.loc.length - 1]}: ${d.msg}`).join('; ')
  }
  return `Request failed (${response.status})`
}

export async function post<T>(path: string, body?: FormData | object): Promise<Outcome<T>> {
  const init: RequestInit = { method: 'POST' }
  if (body instanceof FormData) {
    init.body = body
  } else {
    init.headers = { 'Content-Type': 'application/json' }
    init.body = JSON.stringify(body ?? {})
  }
  try {
    const response = await fetch(`${API_URL}/${path}`, init)
    if (!response.ok) return { ok: false, error: await errorText(response) }
    return { ok: true, data: await response.json() }
  } catch {
    return { ok: false, error: 'Could not reach the backend. Is it running?' }
  }
}
