// @vitest-environment jsdom
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { MemoryRouter } from 'react-router'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
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

function renderAt(path: string) {
  act(() => root.render(
    <MemoryRouter initialEntries={[path]}>
      <Sidebar open collapsed={false} onClose={() => undefined} user={user} health="ok" />
    </MemoryRouter>,
  ))
}

describe('Sidebar Settings active state', () => {
  it('does not keep General active on the Users route', () => {
    renderAt('/settings/users')
    const active = Array.from(container.querySelectorAll('.fh-menu-item-active'))
    expect(active).toHaveLength(1)
    expect(active[0].textContent).toContain('Users')
  })

  it('marks General active only on the exact General route', () => {
    renderAt('/settings')
    const active = Array.from(container.querySelectorAll('.fh-menu-item-active'))
    expect(active).toHaveLength(1)
    expect(active[0].textContent).toContain('General')
  })
})
