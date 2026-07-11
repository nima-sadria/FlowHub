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
const INTERNAL_ERROR_FALLBACK = 'An internal service error occurred.'
const MAX_ERROR_LENGTH = 500

type SafeErrorPayload = {
  code?: unknown
  message?: unknown
  detail?: unknown
  title?: unknown
  errors?: unknown
}

function redactSensitiveText(value: string): string {
  return value
    .replace(/(\bauthorization\s*[:=]\s*)(?:(?:bearer|basic)\s+)?[^\s,;"'}]+/gi, '$1[REDACTED]')
    .replace(/\b(?:bearer|basic)\s+[a-z0-9+/_~.=-]{8,}/gi, '[REDACTED]')
    .replace(/\b(https?:\/\/)(?:[^@\s/?#]+)@([^/\s?#]+)([^\s]*)/gi, '$1$2$3')
    .replace(
      /(\b(?:consumer_secret|consumer_key|access_token|refresh_token|password|api_key|apikey|secret|token|cookie|set-cookie|jwt|session)\b\s*["']?\s*[:=]\s*)(?:"[^"]*"|'[^']*'|[^\s,;}\]]+)/gi,
      '$1[REDACTED]',
    )
}

function safeMessage(value: unknown): string | null {
  if (typeof value !== 'string') return null
  const trimmed = value.trim()
  if (!trimmed || /<\/?(?:html|body)|<!doctype|<\?xml|cloudflare|nginx|proxy error|gateway timeout/i.test(trimmed)) {
    return null
  }
  if (
    /traceback\s*\(most recent call last\)|(?:^|\n)\s*file\s+["'][^"']+["'],\s*line\s+\d+|(?:^|\n)\s*at\s+[\w$.<>()]+\s*\(|\bexception:\s|internal server error[\s\S]*(?:\n\s*at\s|traceback)/i.test(trimmed)
  ) {
    return INTERNAL_ERROR_FALLBACK
  }
  const sanitized = redactSensitiveText(trimmed)
  return sanitized.length <= MAX_ERROR_LENGTH
    ? sanitized
    : `${sanitized.slice(0, MAX_ERROR_LENGTH - 3)}...`
}

function errorStrings(value: unknown): unknown[] {
  if (typeof value === 'string') return [value]
  if (Array.isArray(value)) return value.flatMap(errorStrings)
  if (value && typeof value === 'object') return Object.values(value).flatMap(errorStrings)
  return []
}

function safePayload(value: unknown): { message: string; code?: string } {
  const payload = value && typeof value === 'object' ? value as SafeErrorPayload : {}
  const detail = payload.detail && typeof payload.detail === 'object'
    ? payload.detail as SafeErrorPayload
    : null
  const message = safeMessage(detail?.message)
    ?? safeMessage(payload.message)
    ?? safeMessage(payload.detail)
    ?? safeMessage(payload.title)
    ?? errorStrings(payload.errors).map(safeMessage).find((item): item is string => item !== null)
    ?? UPSTREAM_FALLBACK
  const rawCode = safeMessage(detail?.code ?? payload.code)
  const code = rawCode && /^[A-Z0-9_.-]{1,100}$/i.test(rawCode) ? rawCode : undefined
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
