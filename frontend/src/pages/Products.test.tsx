// @vitest-environment jsdom
import { act, StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { MemoryRouter, Route, Routes } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../api/client'
import { NotificationProvider } from '../notifications/NotificationProvider'
import { ServiceProvider, type Services } from '../services/ServiceContext'
import type {
  Product,
  ProductChannelPriceOperation,
  ProductChannelPriceStateSet,
} from '../services/types'
import Products from './Products'

;(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true

function setInputValue(input: HTMLInputElement, value: string) {
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set
  setter?.call(input, value)
  input.dispatchEvent(new Event('input', { bubbles: true }))
}

const PRODUCT: Product = {
  id: '101', name: 'Cached Product', sku: 'SKU-101', currentPrice: 100, sourcePrice: null,
  currency: 'EUR', status: 'synced', lastSynced: new Date('2026-08-22T10:00:00Z'),
  categoryNames: ['Default'], productType: 'simple', connectorId: 'woocommerce:primary',
}

const CHANNEL_STATE: ProductChannelPriceStateSet = {
  product: { id: '101', name: 'Cached Product', sku: 'SKU-101', productType: 'simple' },
  version: 'v1',
  canonical: { label: 'Canonical/business price', value: 100, currency: 'EUR', unit: 'store currency', freshness: 'fresh', lastSyncedAt: null, staleToken: 'canon-1' },
  channels: [
    {
      channelId: 'woocommerce:primary', channelName: 'WooCommerce', connectorType: 'woocommerce',
      channelProductId: 'wc-101', sku: 'SKU-101', connectionState: 'connected', healthStatus: 'ok',
      canRead: true, canWrite: true, readOnly: false, writeCapability: 'products.write_price',
      currentValue: 100, proposedValue: 100, currency: 'EUR', unit: 'EUR', normalizedValue: 100,
      normalizedCurrency: 'EUR', normalizedUnit: 'EUR', freshness: 'fresh', lastSyncedAt: null,
      validationState: 'valid', validationMessage: null, pendingChange: false, staleToken: 'wc-token-1',
    },
    {
      channelId: 'snappshop:main', channelName: 'Snapp Shop', connectorType: 'snappshop',
      channelProductId: '', sku: '', connectionState: 'disconnected', healthStatus: 'unknown',
      canRead: true, canWrite: false, readOnly: true, writeCapability: 'products.write_price',
      currentValue: null, proposedValue: null, currency: 'IRR', unit: 'toman', normalizedValue: null,
      normalizedCurrency: 'IRR', normalizedUnit: 'rial', freshness: 'missing', lastSyncedAt: null,
      validationState: 'disconnected', validationMessage: 'Channel has no synchronized product row.', pendingChange: false, staleToken: 'missing',
    },
  ],
  dryRunRequired: true,
  applyRequiresApproval: true,
}

const OPERATION: ProductChannelPriceOperation = {
  id: 'mcp_1', productId: '101', sku: 'SKU-101', productName: 'Cached Product',
  status: 'dry_run_ready', version: 'v1', createdBy: 'owner', approvedBy: null, approvalReason: null,
  createdAt: '2026-08-22T10:00:00Z', approvedAt: null, appliedAt: null,
  summary: { total: 1, pending: 1, success: 0, failed: 0, external_write_performed: false },
  items: [{
    id: 1, channelId: 'woocommerce:primary', connectorType: 'woocommerce', channelProductId: 'wc-101',
    sku: 'SKU-101', currentValue: 100, proposedValue: 120, currency: 'EUR', unit: 'EUR',
    outboundValue: 120, outboundUnit: 'store currency', staleToken: 'wc-token-1', status: 'pending',
    validationState: 'valid', errorMessage: null, result: {},
  }],
  externalWritePerformed: false, applyRequiresApproval: true,
}

let container: HTMLDivElement
let root: ReturnType<typeof createRoot>

describe('Products manual Channel editor', () => {
  beforeEach(() => {
    container = document.createElement('div')
    document.body.appendChild(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root.unmount())
    container.remove()
    vi.restoreAllMocks()
  })

  it('lists cached products directly, without bootstrapping any Workspace', async () => {
    const getProducts = vi.fn(async () => ({ items: [PRODUCT], total: 1, page: 1, pageSize: 50, configured: true }))
    await renderProducts(servicesFor({ getProducts }))
    await waitFor(() => container.textContent?.includes('Cached Product') === true)

    expect(getProducts).toHaveBeenCalledWith({ search: '', status: 'all', page: 1, pageSize: 50 })
  })

  it('opens the manual channel editor for a selected product without running Source comparison or auto-selection', async () => {
    const getProducts = vi.fn(async () => ({ items: [PRODUCT], total: 1, page: 1, pageSize: 50, configured: true }))
    const getChannelPrices = vi.fn(async () => CHANNEL_STATE)
    await renderProducts(servicesFor({ getProducts, getChannelPrices }))
    await waitFor(() => container.querySelector('[data-open-channel-editor="101"]') !== null)
    await click('Cached Product')
    await waitFor(() => container.querySelector('[data-channel-editor="101"]') !== null)

    expect(getChannelPrices).toHaveBeenCalledWith('101')
    expect(container.querySelector('[data-channel-row="woocommerce:primary"]')).not.toBeNull()
    expect(container.querySelector('[data-channel-row="snappshop:main"]')).not.toBeNull()
  })

  it('runs validate -> Dry Run -> Approve -> Apply as an explicit safe-write sequence', async () => {
    const getProducts = vi.fn(async () => ({ items: [PRODUCT], total: 1, page: 1, pageSize: 50, configured: true }))
    const getChannelPrices = vi.fn(async () => CHANNEL_STATE)
    const validateChannelPrices = vi.fn(async () => CHANNEL_STATE)
    const createChannelPriceDryRun = vi.fn(async () => OPERATION)
    const approveChannelPriceOperation = vi.fn(async () => ({ ...OPERATION, status: 'approved' as const }))
    const applyChannelPriceOperation = vi.fn(async () => ({ ...OPERATION, status: 'applied' as const, externalWritePerformed: true, summary: { ...OPERATION.summary, success: 1, pending: 0 } }))
    await renderProducts(servicesFor({
      getProducts, getChannelPrices, validateChannelPrices, createChannelPriceDryRun,
      approveChannelPriceOperation, applyChannelPriceOperation,
    }))
    await waitFor(() => container.querySelector('[data-open-channel-editor="101"]') !== null)
    await click('Cached Product')
    await waitFor(() => container.querySelector('[data-channel-editor="101"]') !== null)

    const input = container.querySelector('[data-channel-row="woocommerce:primary"] input') as HTMLInputElement
    expect(input).not.toBeNull()
    await act(async () => { setInputValue(input, '120'); await Promise.resolve() })

    await click('Validate')
    expect(validateChannelPrices).toHaveBeenCalledWith('101', {
      version: 'v1',
      changes: [{ channelId: 'woocommerce:primary', proposedValue: 120, unit: 'EUR', staleToken: 'wc-token-1' }],
    })

    await click('Dry Run')
    expect(createChannelPriceDryRun).toHaveBeenCalledWith('101', {
      version: 'v1',
      changes: [{ channelId: 'woocommerce:primary', proposedValue: 120, unit: 'EUR', staleToken: 'wc-token-1' }],
    })
    await waitFor(() => container.textContent?.includes('dry_run_ready') === true)

    await click('Approve')
    expect(approveChannelPriceOperation).toHaveBeenCalledWith('mcp_1')
    await waitFor(() => container.textContent?.includes('approved') === true)

    await click('Apply')
    expect(applyChannelPriceOperation).toHaveBeenCalledWith('mcp_1')
    await waitFor(() => container.textContent?.includes('applied') === true)
  })

  it('surfaces a stale-conflict as a distinct, reloadable state instead of a generic error', async () => {
    const getProducts = vi.fn(async () => ({ items: [PRODUCT], total: 1, page: 1, pageSize: 50, configured: true }))
    const getChannelPrices = vi.fn(async () => CHANNEL_STATE)
    const createChannelPriceDryRun = vi.fn(async () => {
      throw new ApiError(409, 'changed', 'STALE_CHANNEL_PRICE_STATE')
    })
    await renderProducts(servicesFor({ getProducts, getChannelPrices, createChannelPriceDryRun }))
    await waitFor(() => container.querySelector('[data-open-channel-editor="101"]') !== null)
    await click('Cached Product')
    await waitFor(() => container.querySelector('[data-channel-editor="101"]') !== null)

    const input = container.querySelector('[data-channel-row="woocommerce:primary"] input') as HTMLInputElement
    await act(async () => { setInputValue(input, '120'); await Promise.resolve() })
    await click('Dry Run')
    await waitFor(() => container.textContent?.includes('Try again') === true)
    expect(container.textContent).not.toContain('"code"')

    const callsBeforeRetry = getChannelPrices.mock.calls.length
    await click('Try again')
    await waitFor(() => getChannelPrices.mock.calls.length > callsBeforeRetry)
  })

  it('renders a not-configured state without any product source', async () => {
    const getProducts = vi.fn(async () => ({ items: [], total: 0, page: 1, pageSize: 50, configured: false }))
    await renderProducts(servicesFor({ getProducts }))
    await waitFor(() => container.textContent?.includes('No product connector configured') === true)
  })
})

async function renderProducts(services: Services, initialPath = '/products') {
  await act(async () => {
    root.render(<StrictMode><MemoryRouter initialEntries={[initialPath]}><NotificationProvider><ServiceProvider services={services}><Routes><Route path="/products" element={<Products />} /></Routes></ServiceProvider></NotificationProvider></MemoryRouter></StrictMode>)
    await Promise.resolve()
  })
}

function servicesFor(overrides: {
  getProducts?: ReturnType<typeof vi.fn>
  getChannelPrices?: ReturnType<typeof vi.fn>
  validateChannelPrices?: ReturnType<typeof vi.fn>
  createChannelPriceDryRun?: ReturnType<typeof vi.fn>
  approveChannelPriceOperation?: ReturnType<typeof vi.fn>
  applyChannelPriceOperation?: ReturnType<typeof vi.fn>
} = {}): Services {
  return {
    products: {
      getProducts: overrides.getProducts ?? vi.fn(async () => ({ items: [PRODUCT], total: 1, page: 1, pageSize: 50, configured: true })),
      async getCategories() { return [] },
      async getProduct() { return PRODUCT },
      getChannelPrices: overrides.getChannelPrices ?? vi.fn(async () => CHANNEL_STATE),
      validateChannelPrices: overrides.validateChannelPrices ?? vi.fn(async () => CHANNEL_STATE),
      createChannelPriceDryRun: overrides.createChannelPriceDryRun ?? vi.fn(async () => OPERATION),
      getChannelPriceOperation: vi.fn(async () => OPERATION),
      approveChannelPriceOperation: overrides.approveChannelPriceOperation ?? vi.fn(async () => ({ ...OPERATION, status: 'approved' as const })),
      applyChannelPriceOperation: overrides.applyChannelPriceOperation ?? vi.fn(async () => ({ ...OPERATION, status: 'applied' as const })),
    },
    health: {}, sources: {}, settings: {}, activity: {}, commerce: {}, writePipeline: {}, orders: {},
    unifiedWorkspace: undefined,
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
