// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  AUTH_SESSION_EXPIRED_EVENT,
  authFetch,
} from './authFetch'

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function authorization(init?: RequestInit) {
  return new Headers(init?.headers).get('Authorization')
}

describe('authFetch', () => {
  beforeEach(() => {
    localStorage.clear()
    localStorage.setItem('wp_token', 'expired-access')
    localStorage.setItem('wp_refresh_token', 'valid-refresh')
  })

  afterEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
  })

  it('refreshes an expired access token and retries the original request once', async () => {
    const fetchMock = vi.spyOn(window, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input)
      if (url === '/api/auth/refresh') {
        expect(JSON.parse(String(init?.body))).toEqual({ refresh_token: 'valid-refresh' })
        return jsonResponse({ token: 'fresh-access', refresh_token: 'fresh-refresh' })
      }
      if (url === '/api/v2/source-profiles') {
        return authorization(init) === 'Bearer fresh-access'
          ? jsonResponse({ items: [] })
          : jsonResponse({ detail: 'Expired access token' }, 401)
      }
      throw new Error(`unexpected fetch: ${url}`)
    })

    const response = await authFetch('/api/v2/source-profiles')

    expect(response.status).toBe(200)
    expect(await response.json()).toEqual({ items: [] })
    expect(localStorage.getItem('wp_token')).toBe('fresh-access')
    expect(localStorage.getItem('wp_refresh_token')).toBe('fresh-refresh')
    expect(fetchMock.mock.calls.map(([input]) => String(input))).toEqual([
      '/api/v2/source-profiles',
      '/api/auth/refresh',
      '/api/v2/source-profiles',
    ])
  })

  it('uses one rotating refresh request for concurrent 401 responses', async () => {
    let releaseRefresh!: () => void
    const refreshGate = new Promise<void>(resolve => {
      releaseRefresh = resolve
    })
    let refreshCalls = 0
    const fetchMock = vi.spyOn(window, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input)
      if (url === '/api/auth/refresh') {
        refreshCalls += 1
        await refreshGate
        return jsonResponse({ token: 'fresh-access', refresh_token: 'rotated-refresh' })
      }
      if (url.startsWith('/api/v2/')) {
        return authorization(init) === 'Bearer fresh-access'
          ? jsonResponse({ ok: true })
          : jsonResponse({ detail: 'Expired access token' }, 401)
      }
      throw new Error(`unexpected fetch: ${url}`)
    })

    const requests = Promise.all([
      authFetch('/api/v2/commerce/sources'),
      authFetch('/api/v2/source-profiles'),
      authFetch('/api/v2/exchange-rates/me'),
    ])

    await vi.waitFor(() => expect(refreshCalls).toBe(1))
    releaseRefresh()
    const responses = await requests

    expect(responses.map(response => response.status)).toEqual([200, 200, 200])
    expect(refreshCalls).toBe(1)
    expect(fetchMock.mock.calls.filter(([input]) => String(input) === '/api/auth/refresh')).toHaveLength(1)
  })

  it('clears the session and emits one same-tab event when refresh fails', async () => {
    const expiredListener = vi.fn()
    window.addEventListener(AUTH_SESSION_EXPIRED_EVENT, expiredListener)
    let refreshCalls = 0
    vi.spyOn(window, 'fetch').mockImplementation(async (input) => {
      const url = String(input)
      if (url === '/api/auth/refresh') {
        refreshCalls += 1
        return jsonResponse({ detail: 'Invalid refresh token' }, 401)
      }
      return jsonResponse({ detail: 'Expired access token' }, 401)
    })

    try {
      const responses = await Promise.all([
        authFetch('/api/v2/commerce/sources'),
        authFetch('/api/v2/source-profiles'),
        authFetch('/api/v2/exchange-rates/me'),
      ])

      expect(responses.map(response => response.status)).toEqual([401, 401, 401])
      expect(refreshCalls).toBe(1)
      expect(localStorage.getItem('wp_token')).toBeNull()
      expect(localStorage.getItem('wp_refresh_token')).toBeNull()
      expect(expiredListener).toHaveBeenCalledTimes(1)
    } finally {
      window.removeEventListener(AUTH_SESSION_EXPIRED_EVENT, expiredListener)
    }
  })

  it('retries with a token written by another tab instead of refreshing again', async () => {
    let releaseExpiredResponse!: () => void
    const expiredResponseGate = new Promise<void>(resolve => {
      releaseExpiredResponse = resolve
    })
    const fetchMock = vi.spyOn(window, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input)
      if (url === '/api/auth/refresh') {
        throw new Error('refresh should not be called')
      }
      if (authorization(init) === 'Bearer expired-access') {
        await expiredResponseGate
        return jsonResponse({ detail: 'Expired access token' }, 401)
      }
      return jsonResponse({ items: [] })
    })

    const request = authFetch('/api/v2/source-profiles')
    localStorage.setItem('wp_token', 'other-tab-access')
    localStorage.setItem('wp_refresh_token', 'other-tab-refresh')
    releaseExpiredResponse()

    const response = await request

    expect(response.status).toBe(200)
    expect(fetchMock.mock.calls).toHaveLength(2)
    expect(authorization(fetchMock.mock.calls[1]?.[1])).toBe('Bearer other-tab-access')
  })

  it('does not refresh or clear the session for a permission-denied response', async () => {
    const fetchMock = vi.spyOn(window, 'fetch').mockResolvedValue(
      jsonResponse({ detail: 'Forbidden' }, 403),
    )

    const response = await authFetch('/api/v2/admin-only')

    expect(response.status).toBe(403)
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(localStorage.getItem('wp_token')).toBe('expired-access')
    expect(localStorage.getItem('wp_refresh_token')).toBe('valid-refresh')
  })
})
