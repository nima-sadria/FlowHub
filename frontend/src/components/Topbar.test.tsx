// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { DirectionProvider } from '../direction'
import { ThemeProvider } from '../theme/ThemeProvider'
import Topbar from './Topbar'
import { changeLocale } from '../i18n'

let container: HTMLDivElement
let root: ReturnType<typeof createRoot>

;(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true

beforeEach(() => {
  localStorage.clear()
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
})

afterEach(async () => {
  act(() => { root.unmount() })
  container.remove()
  await changeLocale('en')
})

function LocationProbe() {
  const location = useLocation()
  return <output data-location>{`${location.pathname}${location.search}`}</output>
}

function renderTopbar({ initialPath = '/home', sidebarCollapsed = false } = {}) {
  act(() => {
    root.render(
      <MemoryRouter initialEntries={[initialPath]}>
        <ThemeProvider>
          <DirectionProvider>
            <Topbar
              user={{ username: 'admin', role: 'admin' }}
              onMenuClick={() => undefined}
              onToggleCollapse={() => undefined}
              sidebarCollapsed={sidebarCollapsed}
              onLogout={() => undefined}
            />
            <LocationProbe />
          </DirectionProvider>
        </ThemeProvider>
      </MemoryRouter>,
    )
  })
}

describe('Topbar', () => {
  it('renders the functional global controls from the final design', () => {
    renderTopbar()

    expect(container.querySelector('input[aria-label="Search"]')).not.toBeNull()
    expect(container.querySelector('[aria-label="Notifications"]')).not.toBeNull()
    expect(container.querySelector('[aria-label="Switch to dark mode"]')).not.toBeNull()
    expect(container.querySelector('[aria-label="Language"]')).not.toBeNull()
    expect(container.querySelector('[aria-label="Collapse sidebar"]')).not.toBeNull()
  })

  it('shows the signed-in user with role in the account chip', () => {
    renderTopbar()

    const account = container.querySelector('[aria-label="User menu"]')
    expect(account?.textContent).toContain('admin')
  })

  it('switches the sidebar toggle label with the collapsed state', () => {
    renderTopbar({ sidebarCollapsed: true })

    expect(container.querySelector('[aria-label="Expand sidebar"]')).not.toBeNull()
    expect(container.querySelector('[aria-label="Collapse sidebar"]')).toBeNull()
  })

  it('preserves product parameters when submitting a global search', () => {
    renderTopbar({ initialPath: '/products?workspace=catalog-workspace&status=active' })
    const input = container.querySelector<HTMLInputElement>('input[aria-label="Search"]')
    const form = input?.closest('form')
    expect(input).not.toBeNull()
    expect(form).not.toBeNull()

    act(() => {
      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set
      setter?.call(input, 'red shoe')
      input!.dispatchEvent(new Event('input', { bubbles: true }))
    })
    act(() => {
      form!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    })

    const location = container.querySelector('[data-location]')?.textContent ?? ''
    expect(location).toContain('/products?')
    expect(location).toContain('workspace=catalog-workspace')
    expect(location).toContain('status=active')
    expect(location).toContain('q=red+shoe')
  })

  it('switches language and direction from the language menu', () => {
    renderTopbar()

    const langButton = container.querySelector<HTMLButtonElement>('[aria-label="Language"]')
    expect(langButton).not.toBeNull()
    act(() => { langButton!.click() })

    const persian = container.querySelector<HTMLButtonElement>('.fh-dropdown-item.fh-persian-text')
    expect(persian).not.toBeNull()
    act(() => { persian!.click() })

    expect(document.documentElement.dir).toBe('rtl')
    expect(document.documentElement.lang).toBe('fa')
  })

})
