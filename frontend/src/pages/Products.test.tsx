// @vitest-environment jsdom
import { act, StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../api/client'
import { NotificationProvider } from '../notifications/NotificationProvider'
import { ServiceProvider, type Services } from '../services/ServiceContext'
import type { Product } from '../services/types'
import type { UnifiedWorkspaceResource } from '../services/unifiedWorkspace/types'
import Products from './Products'

vi.mock('../features/sourceWorkspace/DensePricingWorkspace', async () => {
  const React = await import('react')
  return {
    default: ({ workspace }: { workspace: UnifiedWorkspaceResource }) => React.createElement(
      'section',
      { 'data-inline-pricing-grid': workspace.id },
      `Inline pricing ${workspace.id}`,
    ),
  }
})

;(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true

const PRODUCT: Product = {
  id: '101', name: 'Cached Product', sku: 'SKU-101', currentPrice: 100, sourcePrice: null,
  currency: 'EUR', status: 'synced', lastSynced: new Date('2026-07-11T10:00:00Z'),
  categoryNames: ['Default'], productType: 'simple', connectorId: 'woocommerce:primary',
}

const WORKSPACE: UnifiedWorkspaceResource = {
  id: 'catalog-workspace', name: 'Pricing workspace', entryPoint: 'manual', ownerUserId: 1,
  status: 'active', version: 1, snapshot: { id: 'snapshot-1', checksum: 'hash', schemaVersion: '1', createdAt: '2026-07-17T08:00:00Z' },
  draft: { id: 'draft-1', version: 0, currentRevisionId: null, status: 'draft' }, createdAt: '2026-07-17T08:00:00Z',
}

const SOURCE_WORKSPACE: UnifiedWorkspaceResource = {
  ...WORKSPACE,
  id: 'source-workspace',
  entryPoint: 'source',
  sourceType: 'flowhub_sheet',
}

let container: HTMLDivElement
let root: ReturnType<typeof createRoot>

describe('Products inline pricing entry', () => {
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

  it('opens the dense pricing grid directly without product pre-selection or navigation', async () => {
    const createCatalog = vi.fn(async () => WORKSPACE)
    const getProducts = vi.fn(async () => ({ items: [PRODUCT], total: 1, page: 1, pageSize: 50, configured: true }))
    await renderProducts(servicesFor({ createCatalog, getProducts }))
    await waitFor(() => container.querySelector('[data-inline-pricing-grid="catalog-workspace"]') !== null)

    expect(createCatalog).toHaveBeenCalledWith('Pricing workspace')
    expect(container.textContent).not.toContain('Open pricing workspace')
    expect(container.textContent).not.toContain('Choose a product set first')
    expect(container.querySelector('input[type="checkbox"]')).toBeNull()
    expect(window.location.pathname).not.toBe('/workspace/catalog-workspace')
    expect(getProducts).not.toHaveBeenCalled()
  })

  it('resumes the immutable manual Workspace supplied by a compatibility redirect', async () => {
    const getWorkspace = vi.fn(async () => WORKSPACE)
    const createCatalog = vi.fn(async () => WORKSPACE)
    await renderProducts(servicesFor({ createCatalog, getWorkspace }), '/products?workspace=catalog-workspace')
    await waitFor(() => container.querySelector('[data-inline-pricing-grid="catalog-workspace"]') !== null)

    expect(getWorkspace).toHaveBeenCalledWith('catalog-workspace')
    expect(createCatalog).not.toHaveBeenCalled()
    expect(window.sessionStorage.getItem('flowhub.products.active_workspace')).toBeNull()
  })

  it('embeds a source-entry Workspace on Products without replacing the catalog session', async () => {
    window.sessionStorage.setItem('flowhub.products.active_workspace', 'catalog-workspace')
    const getWorkspace = vi.fn(async () => SOURCE_WORKSPACE)
    const createCatalog = vi.fn(async () => WORKSPACE)
    await renderProducts(servicesFor({ createCatalog, getWorkspace }), '/products?workspace=source-workspace')
    await waitFor(() => container.querySelector('[data-inline-pricing-grid="source-workspace"]') !== null)

    expect(getWorkspace).toHaveBeenCalledWith('source-workspace')
    expect(createCatalog).not.toHaveBeenCalled()
    expect(window.sessionStorage.getItem('flowhub.products.active_workspace')).toBe('catalog-workspace')
  })

  it('keeps cached products visible read-only with a precise localized retry when bootstrap fails', async () => {
    const createCatalog = vi.fn()
      .mockRejectedValueOnce(new ApiError(502, 'unsafe upstream prose'))
      .mockResolvedValueOnce(WORKSPACE)
    await renderProducts(servicesFor({ createCatalog }))
    await waitFor(() => container.textContent?.includes('Inline pricing is unavailable (HTTP 502)') === true)

    expect(container.textContent).toContain('Cached Product')
    expect(container.textContent).not.toContain('unsafe upstream prose')
    expect(container.querySelector('[data-product-id="101"] input')).toBeNull()
    await click('Retry inline pricing')
    await waitFor(() => container.querySelector('[data-inline-pricing-grid="catalog-workspace"]') !== null)
    expect(createCatalog).toHaveBeenCalledTimes(2)
  })
})

async function renderProducts(services: Services, initialPath = '/products') {
  await act(async () => {
    root.render(<StrictMode><MemoryRouter initialEntries={[initialPath]}><NotificationProvider><ServiceProvider services={services}><Routes><Route path="/products" element={<Products />} /></Routes></ServiceProvider></NotificationProvider></MemoryRouter></StrictMode>)
    await Promise.resolve()
  })
}

function servicesFor(overrides: {
  createCatalog?: ReturnType<typeof vi.fn>
  getWorkspace?: ReturnType<typeof vi.fn>
  getProducts?: ReturnType<typeof vi.fn>
} = {}): Services {
  return {
    products: {
      getProducts: overrides.getProducts ?? vi.fn(async () => ({ items: [PRODUCT], total: 1, page: 1, pageSize: 50, configured: true })),
      async getCategories() { return [] },
      async getProduct() { return PRODUCT },
    },
    unifiedWorkspace: {
      createManual: vi.fn(),
      createCatalog: overrides.createCatalog ?? vi.fn(async () => WORKSPACE),
      getWorkspace: overrides.getWorkspace ?? vi.fn(async () => WORKSPACE),
    },
    health: {}, sources: {}, workspace: {}, settings: {}, activity: {}, commerce: {}, writePipeline: {}, orders: {},
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
