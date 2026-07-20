// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { MemoryRouter } from 'react-router-dom'
import { DirectionProvider } from '../direction'
import { ThemeProvider } from '../theme/ThemeProvider'
import Topbar from './Topbar'

let container: HTMLDivElement
let root: ReturnType<typeof createRoot>

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

function renderTopbar() {
  act(() => {
    root.render(
      <MemoryRouter initialEntries={['/home']}>
        <ThemeProvider>
          <DirectionProvider>
            <Topbar
              user={{ username: 'admin', role: 'admin' }}
              onMenuClick={() => undefined}
              onToggleCollapse={() => undefined}
              onLogout={() => undefined}
            />
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
    expect(container.querySelector('[aria-label="Change language"]')).not.toBeNull()
    expect(container.querySelector('[aria-label="Toggle sidebar"]')).not.toBeNull()
  })

  it('shows the signed-in user with role in the account chip', () => {
    renderTopbar()

    const account = container.querySelector('[aria-label="User menu"]')
    expect(account?.textContent).toContain('admin')
  })

  it('switches language and direction from the language menu', () => {
    renderTopbar()

    const langButton = container.querySelector<HTMLButtonElement>('[aria-label="Change language"]')
    expect(langButton).not.toBeNull()
    act(() => { langButton!.click() })

    const options = Array.from(container.querySelectorAll<HTMLButtonElement>('.fh-dropdown-item'))
    const persian = options.find(option => option.textContent?.includes('فارسی'))
    expect(persian).not.toBeUndefined()
    act(() => { persian!.click() })

    expect(document.documentElement.dir).toBe('rtl')
    expect(document.documentElement.lang).toBe('fa')
  })
})
