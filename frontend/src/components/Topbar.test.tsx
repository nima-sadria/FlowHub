// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { MemoryRouter } from 'react-router-dom'
import { DirectionProvider } from '../direction'
import { ThemeProvider } from '../theme/ThemeProvider'
import Topbar from './Topbar'
import { changeLocale } from '../i18n'

let container: HTMLDivElement
let root: ReturnType<typeof createRoot>

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
    expect(container.querySelector('[aria-label="Language"]')).not.toBeNull()
    expect(container.querySelector('[aria-label="Collapse sidebar"]')).not.toBeNull()
  })

  it('shows the signed-in user with role in the account chip', () => {
    renderTopbar()

    const account = container.querySelector('[aria-label="User menu"]')
    expect(account?.textContent).toContain('admin')
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
