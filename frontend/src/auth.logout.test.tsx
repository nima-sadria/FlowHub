// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { AuthProvider, useAuth } from './auth'
import { authFetch as serviceAuthFetch } from './api/authFetch'

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('AuthProvider logout', () => {
  let container: HTMLDivElement
  let root: Root
  let logoutFn: (() => Promise<void>) | null = null
  let authFetchFn: ReturnType<typeof useAuth>['authFetch'] | null = null
  let currentStatus: ReturnType<typeof useAuth>['status'] | null = null

  function Consumer() {
    const { logout, authFetch, status } = useAuth()
    logoutFn = logout
    authFetchFn = authFetch
    currentStatus = status
    return null
  }

  beforeEach(() => {
    container = document.createElement('div')
    document.body.appendChild(container)
    root = createRoot(container)
    localStorage.setItem('wp_token', 'access-token')
    localStorage.setItem('wp_refresh_token', 'refresh-token')
  })

  afterEach(() => {
    act(() => root.unmount())
    container.remove()
    localStorage.clear()
    vi.restoreAllMocks()
    logoutFn = null
    authFetchFn = null
    currentStatus = null
  })

  it('revokes the refresh token server-side and clears local auth', async () => {
    const fetchMock = vi.spyOn(window, 'fetch').mockImplementation(async (input) => {
      const url = String(input)
      if (url === '/api/auth/me') {
        return jsonResponse({
          username: 'admin',
          role: 'owner',
          is_admin: true,
          is_super_admin: true,
          permissions: {},
        })
      }
      if (url === '/api/auth/logout') return new Response(null, { status: 204 })
      throw new Error(`unexpected fetch: ${url}`)
    })

    await act(async () => {
      root.render(
        <AuthProvider>
          <Consumer />
        </AuthProvider>,
      )
    })

    await act(async () => {
      await logoutFn?.()
    })

    const logoutCall = fetchMock.mock.calls.find(([input]) => String(input) === '/api/auth/logout')
    expect(logoutCall).toBeDefined()
    const init = logoutCall?.[1]
    expect(init?.method).toBe('POST')
    expect(JSON.parse(String(init?.body))).toEqual({ refresh_token: 'refresh-token' })
    expect(new Headers(init?.headers).get('Authorization')).toBe('Bearer access-token')
    expect(localStorage.getItem('wp_token')).toBeNull()
    expect(localStorage.getItem('wp_refresh_token')).toBeNull()
  })

  it('still clears local auth when revocation fails', async () => {
    vi.spyOn(window, 'fetch').mockImplementation(async (input) => {
      const url = String(input)
      if (url === '/api/auth/me') {
        return jsonResponse({
          username: 'admin',
          role: 'owner',
          is_admin: true,
          is_super_admin: true,
          permissions: {},
        })
      }
      if (url === '/api/auth/logout') throw new TypeError('network down')
      throw new Error(`unexpected fetch: ${url}`)
    })

    await act(async () => {
      root.render(
        <AuthProvider>
          <Consumer />
        </AuthProvider>,
      )
    })

    await act(async () => {
      await logoutFn?.()
    })

    expect(localStorage.getItem('wp_token')).toBeNull()
    expect(localStorage.getItem('wp_refresh_token')).toBeNull()
  })

  it('keeps the authenticated session when one action is denied', async () => {
    vi.spyOn(window, 'fetch').mockImplementation(async (input) => {
      const url = String(input)
      if (url === '/api/auth/me') {
        return jsonResponse({
          username: 'viewer',
          role: 'viewer',
          is_admin: false,
          is_super_admin: false,
          permissions: { 'workspace.read': true },
        })
      }
      if (url === '/api/v2/denied-action') return jsonResponse({ detail: 'Forbidden' }, 403)
      throw new Error(`unexpected fetch: ${url}`)
    })

    await act(async () => {
      root.render(<AuthProvider><Consumer /></AuthProvider>)
    })
    expect(currentStatus).toBe('authenticated')

    await act(async () => {
      const response = await authFetchFn?.('/api/v2/denied-action')
      expect(response?.status).toBe(403)
    })

    expect(currentStatus).toBe('authenticated')
  })

  it('updates the provider when a standalone API service cannot refresh the session', async () => {
    vi.spyOn(window, 'fetch').mockImplementation(async (input) => {
      const url = String(input)
      if (url === '/api/auth/me') {
        return jsonResponse({
          username: 'admin',
          role: 'owner',
          is_admin: true,
          is_super_admin: true,
          permissions: {},
        })
      }
      if (url === '/api/v2/source-profiles') {
        return jsonResponse({ detail: 'Expired access token' }, 401)
      }
      if (url === '/api/auth/refresh') {
        return jsonResponse({ detail: 'Invalid refresh token' }, 401)
      }
      throw new Error(`unexpected fetch: ${url}`)
    })

    await act(async () => {
      root.render(<AuthProvider><Consumer /></AuthProvider>)
    })
    expect(currentStatus).toBe('authenticated')

    await act(async () => {
      const response = await serviceAuthFetch('/api/v2/source-profiles')
      expect(response.status).toBe(401)
    })

    expect(currentStatus).toBe('login_required')
    expect(localStorage.getItem('wp_token')).toBeNull()
    expect(localStorage.getItem('wp_refresh_token')).toBeNull()
  })
})
