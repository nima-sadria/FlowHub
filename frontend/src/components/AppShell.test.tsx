// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { AuthContext } from '../auth'
import type { AuthContextValue } from '../auth'
import { ThemeProvider } from '../theme/ThemeProvider'
import AppShell from './AppShell'

let container: HTMLDivElement
let root: ReturnType<typeof createRoot>

const authValue: AuthContextValue = {
  user: {
    username: 'admin',
    role: 'admin',
    is_admin: true,
    is_super_admin: false,
    permissions: {},
  },
  status: 'authenticated',
  refreshUser: async () => {},
  clearAuth: () => {},
  logout: async () => {},
  authFetch: async () => new Response('', { status: 200 }),
}

beforeEach(() => {
  localStorage.clear()
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
})

afterEach(() => {
  act(() => { root.unmount() })
  container.remove()
})

describe('AppShell layout', () => {
  it('keeps the sidebar and main content in independent viewport-height scroll regions', () => {
    act(() => {
      root.render(
        <AuthContext.Provider value={authValue}>
          <ThemeProvider>
            <MemoryRouter initialEntries={['/products']}>
              <Routes>
                <Route element={<AppShell />}>
                  <Route path="/products" element={<div style={{ height: 2400 }}>Products page</div>} />
                </Route>
              </Routes>
            </MemoryRouter>
          </ThemeProvider>
        </AuthContext.Provider>,
      )
    })

    const shell = container.firstElementChild
    const sidebar = container.querySelector('aside')
    const nav = container.querySelector('aside nav')
    const main = container.querySelector('main')

    expect(shell?.className).toContain('h-[100dvh]')
    expect(shell?.className).toContain('overflow-hidden')
    expect(sidebar?.className).toContain('h-[100dvh]')
    expect(sidebar?.className).toContain('min-h-0')
    expect(nav?.className).toContain('min-h-0')
    expect(nav?.className).toContain('overflow-y-auto')
    expect(main?.className).toContain('min-h-0')
    expect(main?.className).toContain('overflow-y-auto')
    expect(main?.className).toContain('overflow-x-hidden')
  })
})
