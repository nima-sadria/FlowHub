// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { MemoryRouter } from 'react-router-dom'
import { ThemeProvider } from '../theme/ThemeProvider'
import Topbar from './Topbar'

let container: HTMLDivElement
let root: ReturnType<typeof createRoot>

beforeEach(() => {
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
})

afterEach(() => {
  act(() => { root.unmount() })
  container.remove()
})

describe('Topbar', () => {
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
})
