// @vitest-environment jsdom
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { NotificationProvider } from '../notifications/NotificationProvider'
import { ServiceProvider, type Services } from '../services/ServiceContext'
import type { Product } from '../services/types'
import Products from './Products'
import { sourceWorkspaceApi } from '../features/sourceWorkspace/api'

;(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true

const PRODUCT: Product = {
  id: '101', name: 'Test Product', sku: 'SKU-101', currentPrice: 100, sourcePrice: null,
  currency: 'EUR', status: 'synced', lastSynced: new Date('2026-07-11T10:00:00Z'),
  categoryNames: ['Default'], productType: 'simple', connectorId: 'woocommerce:primary',
}

let activeRoot: ReturnType<typeof createRoot>

describe('Products pricing workspace entry', () => {
  let container: HTMLDivElement
  let root: ReturnType<typeof createRoot>

  beforeEach(() => {
    container = document.createElement('div')
    document.body.appendChild(container)
    root = createRoot(container)
    activeRoot = root
    vi.spyOn(sourceWorkspaceApi, 'channels').mockResolvedValue({ items: [] })
  })

  afterEach(() => {
    act(() => root.unmount())
    container.remove()
    vi.restoreAllMocks()
  })

  it('keeps Product identity read-only and removes the modal-first Edit prices action', async () => {
    await renderProducts(servicesFor())
    expect(container.textContent).toContain('Pricing workspace')
    expect(container.textContent).toContain('Edit inline in the pricing workspace')
    expect(container.textContent).not.toContain('Edit prices')
    expect(container.querySelector('input[aria-label="Select Test Product for Workspace"]')).not.toBeNull()
  })

  it('selects visible results and opens one safe grouped workspace', async () => {
    const createManual = vi.fn(async () => ({ id: 'workspace-1' }))
    await renderProducts(servicesFor({ createManual }))
    await click('Select visible')
    expect(container.textContent).toContain('1 products selected')
    await click('Open pricing workspace')
    expect(createManual).toHaveBeenCalledWith(expect.stringContaining('Pricing workspace'), [{ connector_id: 'woocommerce:primary', product_id: '101' }])
  })

  it('requires an explicit product selection before opening the pricing workspace', async () => {
    await renderProducts(servicesFor())
    expect(button('Open pricing workspace')?.disabled).toBe(true)
  })
})

async function renderProducts(services: Services) {
  await act(async () => {
    activeRoot.render(<MemoryRouter><NotificationProvider><ServiceProvider services={services}><Products /></ServiceProvider></NotificationProvider></MemoryRouter>)
    await Promise.resolve()
    await Promise.resolve()
  })
}

function servicesFor(overrides: { createManual?: ReturnType<typeof vi.fn> } = {}): Services {
  return {
    products: {
      async getProducts() { return { items: [PRODUCT], total: 1, page: 1, pageSize: 50, configured: true } },
      async getCategories() { return [] },
      async getProduct() { return PRODUCT },
      async getChannelPrices() { throw new Error('not used by the pricing workspace entry') },
      async validateChannelPrices() { throw new Error('not used by the pricing workspace entry') },
      async createChannelPriceDryRun() { throw new Error('not used by the pricing workspace entry') },
      async getChannelPriceOperation() { throw new Error('not used by the pricing workspace entry') },
      async approveChannelPriceOperation() { throw new Error('not used by the pricing workspace entry') },
      async applyChannelPriceOperation() { throw new Error('not used by the pricing workspace entry') },
    },
    unifiedWorkspace: {
      createManual: overrides.createManual ?? vi.fn(async () => ({ id: 'workspace-1' })),
    },
    health: {}, sources: {}, workspace: {}, settings: {}, activity: {}, commerce: {}, writePipeline: {}, orders: {},
  } as unknown as Services
}

async function click(label: string) {
  const button = Array.from(document.querySelectorAll('button')).find(item => item.textContent?.trim() === label)
  expect(button).not.toBeUndefined()
  await act(async () => { (button as HTMLButtonElement).click(); await Promise.resolve() })
}

function button(label: string): HTMLButtonElement | null {
  return Array.from(document.querySelectorAll('button')).find(item => item.textContent?.trim() === label) ?? null
}
