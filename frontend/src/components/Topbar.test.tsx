// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { MemoryRouter } from 'react-router-dom'
import { ThemeProvider } from '../theme/ThemeProvider'
import Topbar, { resolvePageTitle } from './Topbar'
import { changeLocale } from '../i18n'

let container: HTMLDivElement
let root: ReturnType<typeof createRoot>

beforeEach(() => {
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
})

afterEach(async () => {
  act(() => { root.unmount() })
  container.remove()
  await changeLocale('en')
})

describe('Topbar', () => {
  it('resolves static and dynamic route titles without treating dynamic ids as unknown routes', () => {
    expect(resolvePageTitle('/products')).toBe('Products')
    expect(resolvePageTitle('/workspace/ws-visual')).toBe('Workspace')
    expect(resolvePageTitle('/workspaces/ws-visual')).toBe('Workspace')
    expect(resolvePageTitle('/unified-workspace/ws-visual')).toBe('Workspace')
    expect(resolvePageTitle('/workspace/ws-visual', 'Spring Campaign')).toBe('Spring Campaign')
    expect(resolvePageTitle('/workspace')).toBe('Workspace')
    expect(resolvePageTitle('/not-a-route')).toBe('FlowHub')
  })

  it('does not render unavailable search or notification controls', () => {
    act(() => {
      root.render(
        <MemoryRouter initialEntries={['/home']}>
          <ThemeProvider>
            <Topbar health="ok" user={{ username: 'admin' }} onMenuClick={() => undefined} onLogout={() => undefined} />
          </ThemeProvider>
        </MemoryRouter>,
      )
    })

    expect(container.querySelector('[aria-label="Search"]')).toBeNull()
    expect(container.querySelector('[aria-label="Notifications"]')).toBeNull()
    expect(container.querySelector('[aria-label="Switch to dark mode"]')).not.toBeNull()
  })

  it('renders the connected state in Persian without translating the username', async () => {
    await changeLocale('fa')
    act(() => {
      root.render(
        <MemoryRouter initialEntries={['/home']}>
          <ThemeProvider>
            <Topbar health="ok" user={{ username: 'admin' }} onMenuClick={() => undefined} onLogout={() => undefined} />
          </ThemeProvider>
        </MemoryRouter>,
      )
    })

    expect(container.textContent).toContain('متصل')
    expect(container.textContent).toContain('admin')
    expect(container.textContent).not.toContain('Connected')
    await changeLocale('en')
  })
})
