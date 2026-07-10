export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    public readonly code?: string,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>

const UPSTREAM_FALLBACK = 'An upstream service returned an invalid response. Check the connection and try again.'

type SafeErrorPayload = {
  code?: unknown
  message?: unknown
  detail?: unknown
}

function redactSensitiveText(value: string): string {
  return value.replace(
    /((?:consumer_secret|consumer_key|access_token|refresh_token|authorization|password|api_key|apikey|secret|token|key)\s*["']?\s*[:=]\s*["']?)([^"',\s}]+)/gi,
    '$1[REDACTED]',
  )
}

function safeMessage(value: unknown): string | null {
  if (typeof value !== 'string') return null
  const trimmed = value.trim()
  if (!trimmed || trimmed.length > 512 || /<\/?(?:html|body)|<!doctype|<\?xml|cloudflare|nginx|proxy error|gateway timeout/i.test(trimmed)) {
    return null
  }
  return redactSensitiveText(trimmed)
}

function safePayload(value: unknown): { message: string; code?: string } {
  const payload = value && typeof value === 'object' ? value as SafeErrorPayload : {}
  const detail = payload.detail && typeof payload.detail === 'object'
    ? payload.detail as SafeErrorPayload
    : null
  const message = safeMessage(detail?.message)
    ?? safeMessage(payload.message)
    ?? safeMessage(payload.detail)
    ?? UPSTREAM_FALLBACK
  const code = typeof (detail?.code ?? payload.code) === 'string'
    ? String(detail?.code ?? payload.code)
    : undefined
  return { message, code }
}

export function apiErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    try {
      return safePayload(JSON.parse(error.message)).message
    } catch {
      return safeMessage(error.message) ?? fallback
    }
  }
  if (error instanceof Error) return safeMessage(error.message) ?? fallback
  return fallback
}

export async function apiFetch<T>(
  url: string,
  fetchFn: FetchFn,
  init?: RequestInit,
  timeoutMs?: number,
): Promise<T> {
  const controller = timeoutMs ? new AbortController() : null
  const timeoutId = controller
    ? window.setTimeout(() => controller.abort(), timeoutMs)
    : null

  try {
    const requestInit = controller && !init?.signal
      ? { ...init, signal: controller.signal }
      : init
    const r = await fetchFn(url, requestInit)
    if (!r.ok) {
      let payload: unknown = null
      const contentType = r.headers.get('content-type') ?? ''
      if (contentType.toLowerCase().includes('application/json')) {
        payload = await r.json().catch(() => null)
      }
      const safe = safePayload(payload)
      throw new ApiError(r.status, safe.message, safe.code)
    }
    return r.json() as Promise<T>
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') {
      throw new Error('request_timeout')
    }
    throw error
  } finally {
    if (timeoutId !== null) window.clearTimeout(timeoutId)
  }
}
