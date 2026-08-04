/**
 * Shared authenticated transport for every frontend API client.
 *
 * Access tokens are short-lived and refresh tokens rotate on every use. Keep
 * refresh coordination here so concurrent page requests cannot consume the
 * same refresh token independently.
 */

export const AUTH_SESSION_EXPIRED_EVENT = 'flowhub:auth-session-expired'

const ACCESS_TOKEN_KEY = 'wp_token'
const REFRESH_TOKEN_KEY = 'wp_refresh_token'
const USER_KEY = 'wp_user'
const REFRESH_LOCK_NAME = 'flowhub-auth-refresh'

type TokenResponse = {
  token: string
  refresh_token: string
}

let refreshInFlight: Promise<boolean> | null = null

function accessToken() {
  return localStorage.getItem(ACCESS_TOKEN_KEY) ?? ''
}

function refreshToken() {
  return localStorage.getItem(REFRESH_TOKEN_KEY) ?? ''
}

function dispatchSessionExpired() {
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new Event(AUTH_SESSION_EXPIRED_EVENT))
  }
}

export function clearStoredAuth({ notify = true }: { notify?: boolean } = {}) {
  const hadStoredSession = Boolean(
    localStorage.getItem(ACCESS_TOKEN_KEY)
      || localStorage.getItem(REFRESH_TOKEN_KEY)
      || localStorage.getItem(USER_KEY),
  )
  localStorage.removeItem(ACCESS_TOKEN_KEY)
  localStorage.removeItem(REFRESH_TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
  if (notify && hadStoredSession) dispatchSessionExpired()
}

export function authHeaders(init?: RequestInit) {
  const headers = new Headers(init?.headers)
  const token = accessToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  return headers
}

function tokensChangedSince(expectedRefreshToken: string) {
  return Boolean(
    accessToken()
      && refreshToken()
      && refreshToken() !== expectedRefreshToken,
  )
}

async function performTokenRefresh(expectedRefreshToken: string): Promise<boolean> {
  const currentRefreshToken = refreshToken()
  if (!currentRefreshToken) return false

  // Another browser tab may have completed rotation while this tab waited for
  // the cross-tab lock. Its new token pair is already the correct result.
  if (currentRefreshToken !== expectedRefreshToken && accessToken()) return true

  try {
    const response = await fetch('/api/auth/refresh', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: currentRefreshToken }),
    })
    if (!response.ok) return tokensChangedSince(currentRefreshToken)

    const data = await response.json() as Partial<TokenResponse>
    if (typeof data.token !== 'string' || !data.token || typeof data.refresh_token !== 'string' || !data.refresh_token) {
      return false
    }

    // Write access first. A storage listener in another tab can immediately
    // validate with it without trying to rotate the refresh token again.
    localStorage.setItem(ACCESS_TOKEN_KEY, data.token)
    localStorage.setItem(REFRESH_TOKEN_KEY, data.refresh_token)
    return true
  } catch {
    return tokensChangedSince(currentRefreshToken)
  }
}

async function withCrossTabRefreshLock(
  expectedRefreshToken: string,
  callback: () => Promise<boolean>,
): Promise<boolean> {
  if (typeof navigator === 'undefined' || !navigator.locks) return callback()
  return navigator.locks.request(REFRESH_LOCK_NAME, async () => {
    if (tokensChangedSince(expectedRefreshToken)) return true
    return callback()
  })
}

export function refreshAuthSession(): Promise<boolean> {
  if (refreshInFlight) return refreshInFlight

  const expectedRefreshToken = refreshToken()
  if (!expectedRefreshToken) return Promise.resolve(false)

  refreshInFlight = withCrossTabRefreshLock(
    expectedRefreshToken,
    () => performTokenRefresh(expectedRefreshToken),
  ).finally(() => {
    refreshInFlight = null
  })
  return refreshInFlight
}

function requestHeaders(input: RequestInfo | URL, init?: RequestInit) {
  const headers = new Headers(input instanceof Request ? input.headers : undefined)
  new Headers(init?.headers).forEach((value, key) => headers.set(key, value))
  const token = accessToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  return headers
}

function sendAuthenticatedRequest(
  input: RequestInfo | URL,
  init?: RequestInit,
) {
  return fetch(input, { ...init, headers: requestHeaders(input, init) })
}

export async function authFetch(
  input: RequestInfo | URL,
  init?: RequestInit,
): Promise<Response> {
  // Clone before fetch consumes a Request body so a single authenticated retry
  // remains possible. FlowHub's RequestInit bodies are replayable JSON strings.
  const retryInput = input instanceof Request ? input.clone() : input
  const attemptedAccessToken = accessToken()
  const response = await sendAuthenticatedRequest(input, init)
  if (response.status !== 401) return response

  // A different request or browser tab may already have refreshed while this
  // response was in flight. Retry with that token instead of rotating again.
  const newerAccessToken = accessToken()
  const recovered = Boolean(newerAccessToken && newerAccessToken !== attemptedAccessToken)
    || await refreshAuthSession()

  if (!recovered) {
    clearStoredAuth()
    return response
  }

  const retriedWithAccessToken = accessToken()
  const retried = await sendAuthenticatedRequest(retryInput, init)
  if (retried.status === 401 && accessToken() === retriedWithAccessToken) {
    clearStoredAuth()
  }
  return retried
}
