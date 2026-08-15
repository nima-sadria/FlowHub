// @vitest-environment jsdom
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { MemoryRouter } from 'react-router'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { AuthContext, type AuthContextValue } from '../auth'
import SettingsNav from './SettingsNav'

let container: HTMLDivElement
let root: ReturnType<typeof createRoot>

const auth: AuthContextValue = {
  user: {
    id: 1, username: 'owner', email: 'owner@example.com', role: 'owner', is_admin: true, is_super_admin: true,
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

describe('SettingsNav active state', () => {
  for (const [path, label] of [
    ['/settings', 'General'],
    ['/settings/exchange-rates', 'Exchange Rates'],
    ['/settings/users', 'Users'],
    ['/settings/rate-limits', 'Rate Limits'],
    ['/settings/advanced', 'Advanced Settings'],
  ] as const) {
    it(`marks only ${label} active on ${path}`, () => {
      act(() => root.render(
        <AuthContext.Provider value={auth}>
          <MemoryRouter initialEntries={[path]}><SettingsNav /></MemoryRouter>
        </AuthContext.Provider>,
      ))

      const current = container.querySelectorAll('a[aria-current="page"]')
      expect(current).toHaveLength(1)
      expect(current[0].textContent).toBe(label)
    })
  }
})
