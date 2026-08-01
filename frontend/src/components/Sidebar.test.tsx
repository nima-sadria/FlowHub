// @vitest-environment jsdom
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { MemoryRouter } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { AuthUser } from '../auth'
import Sidebar from './Sidebar'

let container: HTMLDivElement
let root: ReturnType<typeof createRoot>

const user: AuthUser = {
  username: 'owner', role: 'owner', is_admin: true, is_super_admin: true,
  permissions: {
    can_access_site: true,
    can_fetch: true,
    can_view_settings: true,
    can_manage_sources: true,
    can_read_audit: true,
  },
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

function renderAt(path: string, { collapsed = false, onExpand = () => undefined } = {}) {
  act(() => root.render(
    <MemoryRouter initialEntries={[path]}>
      <Sidebar open collapsed={collapsed} onClose={() => undefined} onExpand={onExpand} user={user} health="ok" />
    </MemoryRouter>,
  ))
}

describe('Sidebar Settings active state', () => {
  it('does not keep General active on the Users route', () => {
    renderAt('/settings/users')
    const active = Array.from(container.querySelectorAll('.fh-menu-item-active'))
    expect(active).toHaveLength(1)
    expect(active[0].textContent).toContain('Users')
    expect(container.querySelector<HTMLButtonElement>('[aria-controls="sidebar-settings-submenu"]')?.dataset.active).toBe('true')
  })

  it('marks General active only on the exact General route', () => {
    renderAt('/settings')
    const active = Array.from(container.querySelectorAll('.fh-menu-item-active'))
    expect(active).toHaveLength(1)
    expect(active[0].textContent).toContain('General')
  })

  it('auto-expands the parent and renders all canonical Settings children', () => {
    renderAt('/settings/rate-limits')

    const parent = container.querySelector<HTMLButtonElement>('[aria-controls="sidebar-settings-submenu"]')
    expect(parent?.getAttribute('aria-expanded')).toBe('true')
    expect(container.querySelectorAll('#sidebar-settings-submenu a')).toHaveLength(5)
    expect(container.querySelector('a[href="/settings/exchange-rates"]')).not.toBeNull()
    expect(container.querySelector('a[href="/settings/rate-limits"]')).not.toBeNull()
    expect(container.querySelector('a[href="/settings/advanced"]')).not.toBeNull()
  })

  it('supports native button activation and expands a collapsed sidebar', () => {
    const onExpand = vi.fn()
    renderAt('/home', { collapsed: true, onExpand })

    const parent = container.querySelector<HTMLButtonElement>('[aria-controls="sidebar-settings-submenu"]')
    expect(parent?.getAttribute('aria-expanded')).toBe('false')
    act(() => { parent!.click() })

    expect(onExpand).toHaveBeenCalledTimes(1)
    expect(parent?.getAttribute('aria-expanded')).toBe('true')
    expect(parent?.tagName).toBe('BUTTON')
  })
})
