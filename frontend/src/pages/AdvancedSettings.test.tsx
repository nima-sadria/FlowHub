// @vitest-environment jsdom
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { MemoryRouter } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthContext, type AuthContextValue } from '../auth'
import { NotificationProvider } from '../notifications/NotificationProvider'
import AdvancedSettings from './AdvancedSettings'

let container: HTMLDivElement
let root: ReturnType<typeof createRoot>

const auth: AuthContextValue = {
  user: {
    username: 'owner', role: 'owner', is_admin: true, is_super_admin: true,
    permissions: { can_access_site: true, can_view_settings: true },
  },
  status: 'authenticated',
  refreshUser: async () => undefined,
  clearAuth: () => undefined,
  logout: async () => undefined,
  authFetch: fetch,
}

beforeEach(() => {
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
})

afterEach(() => {
  act(() => root.unmount())
  container.remove()
})

describe('AdvancedSettings', () => {
  it('lets administrators manage narrowly scoped Nextcloud private-network exceptions', async () => {
    const authFetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ trusted_private_networks: ['192.168.100.11/32'] }), { status: 200, headers: { 'Content-Type': 'application/json' } }))
    act(() => root.render(
      <AuthContext.Provider value={{ ...auth, authFetch }}>
        <NotificationProvider><MemoryRouter initialEntries={['/settings/advanced']}><AdvancedSettings /></MemoryRouter></NotificationProvider>
      </AuthContext.Provider>,
    ))
    await act(async () => undefined)
    expect(container.querySelector('h1')?.textContent).toBe('Advanced Settings')
    expect(container.querySelector('a[aria-current="page"]')?.textContent).toBe('Advanced Settings')
    expect((container.querySelector('textarea') as HTMLTextAreaElement).value).toBe('192.168.100.11/32')
    expect(container.querySelector('textarea')).not.toBeNull()
  })
})
