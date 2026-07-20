// @vitest-environment jsdom
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthContext, type AuthContextValue } from '../auth'
import { DirectionProvider } from '../direction'
import { ThemeProvider } from '../theme/ThemeProvider'
import Login from './Login'

let container: HTMLDivElement
let root: ReturnType<typeof createRoot>
let refreshUser: ReturnType<typeof vi.fn>

beforeEach(() => {
  localStorage.clear()
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
  refreshUser = vi.fn(async () => undefined)
})

afterEach(() => {
  act(() => { root.unmount() })
  container.remove()
  vi.restoreAllMocks()
})

function authValue(): AuthContextValue {
  return {
    user: null,
    status: 'login_required',
    refreshUser: refreshUser as () => Promise<void>,
    clearAuth: () => undefined,
    logout: async () => undefined,
    authFetch: fetch,
  }
}

async function renderLogin() {
  await act(async () => {
    root.render(
      <MemoryRouter>
        <ThemeProvider>
          <DirectionProvider>
            <AuthContext.Provider value={authValue()}>
              <Login />
            </AuthContext.Provider>
          </DirectionProvider>
        </ThemeProvider>
      </MemoryRouter>,
    )
  })
}

function setInput(input: HTMLInputElement, value: string) {
  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set
  setter?.call(input, value)
  input.dispatchEvent(new Event('input', { bubbles: true }))
}

describe('Login', () => {
  it('renders the approved authentication frame and controls', async () => {
    await renderLogin()

    expect(container.textContent).toContain('Sign in to FlowHub')
    expect(container.textContent).toContain('Use your workspace account.')
    expect(container.textContent).toContain('Remember me')
    expect(container.textContent).toContain('Forgot password?')
    expect(container.textContent).toContain('Need access? Contact your workspace Owner.')
    expect(container.textContent).toContain('Privacy · Security · Support')
    expect(container.querySelector('input[type="checkbox"]')?.hasAttribute('checked')).toBe(true)
    expect(container.querySelector('[aria-label="Switch to dark mode"]')).not.toBeNull()
  })

  it('submits the existing login contract and stores returned tokens', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      new Response(JSON.stringify({ token: 'access-token', refresh_token: 'refresh-token' }), { status: 200 }),
    )
    await renderLogin()

    const identifier = container.querySelector('#login-identifier') as HTMLInputElement
    const password = container.querySelector('#login-password') as HTMLInputElement
    await act(async () => {
      setInput(identifier, 'owner@flowhub.app')
      setInput(password, 'secret-pass')
    })
    const form = container.querySelector('form')
    await act(async () => {
      form?.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    })

    expect(fetchMock).toHaveBeenCalledWith('/api/auth/login', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ username: 'owner@flowhub.app', password: 'secret-pass' }),
    }))
    expect(localStorage.getItem('wp_token')).toBe('access-token')
    expect(localStorage.getItem('wp_refresh_token')).toBe('refresh-token')
    expect(refreshUser).toHaveBeenCalledOnce()
  })
})
