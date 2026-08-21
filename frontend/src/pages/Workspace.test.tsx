// @vitest-environment jsdom
import { act, StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { MemoryRouter, Route, Routes } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../api/client'
import { NotificationProvider } from '../notifications/NotificationProvider'
import { ServiceProvider, type Services } from '../services/ServiceContext'
import type { UnifiedWorkspaceResource } from '../services/unifiedWorkspace/types'
import Workspace from './Workspace'

vi.mock('../features/sourceWorkspace/DensePricingWorkspace', async () => {
  const React = await import('react')
  return {
    default: ({ workspace, initialSearch }: { workspace: UnifiedWorkspaceResource; initialSearch?: string }) => React.createElement(
      'section',
      { 'data-workspace-engine': workspace.id, 'data-initial-search': initialSearch },
      `Automated reconciliation ${workspace.id}`,
    ),
  }
})

;(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true

const WORKSPACE: UnifiedWorkspaceResource = {
  id: 'reconciliation-workspace', name: 'Pricing workspace', entryPoint: 'source', ownerUserId: 1,
  status: 'active', version: 1, snapshot: { id: 'snapshot-1', checksum: 'hash', schemaVersion: '1', createdAt: '2026-08-22T08:00:00Z' },
  draft: { id: 'draft-1', version: 0, currentRevisionId: null, status: 'draft' }, createdAt: '2026-08-22T08:00:00Z',
  sourceType: 'flowhub_sheet',
}

let container: HTMLDivElement
let root: ReturnType<typeof createRoot>

describe('Workspace automated reconciliation entry', () => {
  beforeEach(() => {
    window.sessionStorage.clear()
    container = document.createElement('div')
    document.body.appendChild(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root.unmount())
    container.remove()
    window.sessionStorage.clear()
    vi.restoreAllMocks()
  })

  it('mounts the canonical automated reconciliation engine, not the Products manual editor', async () => {
    const createCatalog = vi.fn(async () => WORKSPACE)
    await renderWorkspace(servicesFor({ createCatalog }))
    await waitFor(() => container.querySelector('[data-workspace-engine="reconciliation-workspace"]') !== null)

    expect(createCatalog).toHaveBeenCalledWith('Pricing workspace')
  })

  it('remembers the bootstrapped workspace under its own session key, distinct from Products', async () => {
    const createCatalog = vi.fn(async () => WORKSPACE)
    await renderWorkspace(servicesFor({ createCatalog }))
    await waitFor(() => container.querySelector('[data-workspace-engine="reconciliation-workspace"]') !== null)

    expect(window.sessionStorage.getItem('flowhub.workspace.active_workspace')).toBe('reconciliation-workspace')
    expect(window.sessionStorage.getItem('flowhub.products.active_workspace')).toBeNull()
  })

  it('resumes an explicit workspace id from the query string without creating a new catalog', async () => {
    const getWorkspace = vi.fn(async () => WORKSPACE)
    const createCatalog = vi.fn(async () => WORKSPACE)
    await renderWorkspace(servicesFor({ createCatalog, getWorkspace }), '/workspace?workspace=reconciliation-workspace')
    await waitFor(() => container.querySelector('[data-workspace-engine="reconciliation-workspace"]') !== null)

    expect(getWorkspace).toHaveBeenCalledWith('reconciliation-workspace')
    expect(createCatalog).not.toHaveBeenCalled()
  })

  it('passes q through to the reconciliation engine search', async () => {
    const getWorkspace = vi.fn(async () => WORKSPACE)
    await renderWorkspace(
      servicesFor({ getWorkspace }),
      '/workspace?workspace=reconciliation-workspace&q=red%20shoe',
    )
    await waitFor(() => container.querySelector('[data-workspace-engine="reconciliation-workspace"]') !== null)

    const engine = container.querySelector('[data-workspace-engine="reconciliation-workspace"]')
    expect(engine?.getAttribute('data-initial-search')).toBe('red shoe')
  })

  it('shows a retryable error state without falling back to any manual product table', async () => {
    const createCatalog = vi.fn()
      .mockRejectedValueOnce(new ApiError(502, 'unsafe upstream prose'))
      .mockResolvedValueOnce(WORKSPACE)
    await renderWorkspace(servicesFor({ createCatalog }))
    await waitFor(() => container.textContent?.includes('Workspace unavailable (HTTP 502)') === true)

    expect(container.textContent).not.toContain('unsafe upstream prose')
    expect(container.querySelector('table')).toBeNull()
    await click('Try again')
    await waitFor(() => container.querySelector('[data-workspace-engine="reconciliation-workspace"]') !== null)
    expect(createCatalog).toHaveBeenCalledTimes(2)
  })

  it('surfaces an empty catalog scope as a distinct, actionable message', async () => {
    const createCatalog = vi.fn().mockRejectedValue(new ApiError(
      422,
      'No cached products match the requested catalog scope.',
      'CATALOG_SCOPE_EMPTY',
    ))
    await renderWorkspace(servicesFor({ createCatalog }))
    await waitFor(() => container.textContent?.includes('No eligible Source products are available for reconciliation yet.') === true)

    expect(container.textContent).not.toContain('HTTP 422')
  })
})

async function renderWorkspace(services: Services, initialPath = '/workspace') {
  await act(async () => {
    root.render(<StrictMode><MemoryRouter initialEntries={[initialPath]}><NotificationProvider><ServiceProvider services={services}><Routes><Route path="/workspace" element={<Workspace />} /></Routes></ServiceProvider></NotificationProvider></MemoryRouter></StrictMode>)
    await Promise.resolve()
  })
}

function servicesFor(overrides: {
  createCatalog?: ReturnType<typeof vi.fn>
  getWorkspace?: ReturnType<typeof vi.fn>
} = {}): Services {
  return {
    products: { getProducts: vi.fn(), async getCategories() { return [] }, async getProduct() { return null } },
    unifiedWorkspace: {
      createManual: vi.fn(),
      createCatalog: overrides.createCatalog ?? vi.fn(async () => WORKSPACE),
      getWorkspace: overrides.getWorkspace ?? vi.fn(async () => WORKSPACE),
    },
    health: {}, sources: {}, settings: {
      getSettings: vi.fn(async () => ({ currency: 'IRR', currencyUnit: 'TOMAN' })),
    }, activity: {}, commerce: {}, writePipeline: {}, orders: {},
  } as unknown as Services
}

async function waitFor(predicate: () => boolean) {
  for (let attempt = 0; attempt < 30; attempt += 1) {
    if (predicate()) return
    await act(async () => { await new Promise(resolve => setTimeout(resolve, 0)) })
  }
  expect(predicate()).toBe(true)
}

async function click(label: string) {
  const button = Array.from(container.querySelectorAll('button')).find(item => item.textContent?.trim() === label)
  expect(button).not.toBeUndefined()
  await act(async () => { (button as HTMLButtonElement).click(); await Promise.resolve() })
}
