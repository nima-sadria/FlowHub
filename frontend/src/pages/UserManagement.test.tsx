// @vitest-environment jsdom
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthContext, type AuthContextValue, type AuthUser } from '../auth'
import { NotificationProvider } from '../notifications/NotificationProvider'
import UserManagement from './UserManagement'

let container: HTMLDivElement
let root: ReturnType<typeof createRoot>

const user: AuthUser = {
  username: 'owner',
  role: 'owner',
  is_admin: true,
  is_super_admin: true,
  permissions: { can_access_site: true, can_view_settings: true },
}

const owner = {
  id: 1,
  username: 'owner',
  role: 'owner',
  is_active: true,
  created_at: '2026-01-01T00:00:00Z',
  is_admin: true,
  is_super_admin: true,
}

const viewer = {
  id: 2,
  username: 'catalog-viewer',
  role: 'viewer',
  is_active: false,
  created_at: '2026-02-01T00:00:00Z',
  is_admin: false,
  is_super_admin: false,
}

function responseFor(input: RequestInfo | URL, init?: RequestInit): Response {
  const url = String(input)
  if (url.endsWith('/api/v2/users') && !init?.method) {
    return new Response(JSON.stringify({ items: [owner, viewer], total: 2 }), { status: 200 })
  }
  if (url.endsWith('/api/v2/users') && init?.method === 'POST') {
    return new Response(JSON.stringify({ ...viewer, id: 3, username: 'new-user', is_active: true }), { status: 201 })
  }
  return new Response('{}', { status: 404 })
}

function authValue(): AuthContextValue {
  return {
    user,
    status: 'authenticated',
    refreshUser: async () => undefined,
    clearAuth: () => undefined,
    logout: async () => undefined,
    authFetch: vi.fn(async (input, init) => responseFor(input, init)),
  }
}

beforeEach(() => {
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
})

afterEach(() => {
  act(() => { root.unmount() })
  container.remove()
})

async function renderPage() {
  const auth = authValue()
  await act(async () => {
    root.render(
      <MemoryRouter>
        <NotificationProvider>
          <AuthContext.Provider value={auth}>
            <UserManagement />
          </AuthContext.Provider>
        </NotificationProvider>
      </MemoryRouter>,
    )
  })
  await act(async () => { await Promise.resolve() })
  return { page: container, auth }
}

describe('UserManagement', () => {
  it('renders real API users, roles, and account states', async () => {
    const { page } = await renderPage()
    expect(page.textContent).toContain('User Management')
    expect(page.textContent).toContain('owner')
    expect(page.textContent).toContain('catalog-viewer')
    expect(page.textContent).toContain('Viewer')
    expect(page.textContent).toContain('Disabled')
  })

  it('opens the create-user editor with backend role choices', async () => {
    const { page } = await renderPage()
    const buttons = Array.from(page.querySelectorAll('button'))
    const createButton = buttons.find(button => button.textContent?.includes('Create user'))
    expect(createButton).not.toBeUndefined()
    await act(async () => { createButton?.dispatchEvent(new MouseEvent('click', { bubbles: true })) })
    expect(page.querySelector('form')).not.toBeNull()
    expect(page.textContent).toContain('Owner')
    expect(page.textContent).toContain('Operator')
    expect(page.textContent).toContain('Viewer')
  })
})
