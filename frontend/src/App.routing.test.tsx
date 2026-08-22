// @vitest-environment jsdom
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { LegacyWorkspaceIdRedirect } from './App'

;(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true

let container: HTMLDivElement
let root: ReturnType<typeof createRoot>

describe('Legacy /workspace/:workspaceId deep link', () => {
  beforeEach(() => {
    container = document.createElement('div')
    document.body.appendChild(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root.unmount())
    container.remove()
  })

  it('resolves an old bookmarked deep link back into the real Workspace page, never into Products', async () => {
    await act(async () => {
      root.render(
        <MemoryRouter initialEntries={['/workspace/legacy-workspace-42#anchor']}>
          <Routes>
            <Route path="/workspace/:workspaceId" element={<LegacyWorkspaceIdRedirect />} />
            <Route path="/workspace" element={<RouteProbe />} />
            <Route path="/products" element={<div data-products-landed>Should never land here</div>} />
          </Routes>
        </MemoryRouter>,
      )
      await Promise.resolve()
    })

    const probe = container.querySelector('[data-workspace-landed]')
    expect(probe).not.toBeNull()
    expect(probe?.getAttribute('data-pathname')).toBe('/workspace')
    expect(probe?.getAttribute('data-search')).toBe('?workspace=legacy-workspace-42')
    expect(probe?.getAttribute('data-hash')).toBe('#anchor')
    expect(container.querySelector('[data-products-landed]')).toBeNull()
  })
})

function RouteProbe() {
  const location = useLocation()
  return (
    <div
      data-workspace-landed
      data-pathname={location.pathname}
      data-search={location.search}
      data-hash={location.hash}
    />
  )
}
