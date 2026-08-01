// @vitest-environment jsdom
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { MemoryRouter } from 'react-router'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { AuthContext, type AuthContextValue } from '../auth'
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
  it('provides a truthful, route-active Settings surface without configuration actions', () => {
    act(() => root.render(
      <AuthContext.Provider value={auth}>
        <MemoryRouter initialEntries={['/settings/advanced']}><AdvancedSettings /></MemoryRouter>
      </AuthContext.Provider>,
    ))

    expect(container.querySelector('h1')?.textContent).toBe('Advanced Settings')
    expect(container.querySelector('a[aria-current="page"]')?.textContent).toBe('Advanced Settings')
    expect(container.querySelector('.fh-badge-neutral')?.textContent).toBe('Unavailable')
    expect(container.querySelectorAll('button')).toHaveLength(0)
  })
})
