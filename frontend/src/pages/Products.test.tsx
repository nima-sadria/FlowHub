// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { createRoot } from 'react-dom/client'
import { act } from 'react'
import { NotificationProvider } from '../notifications/NotificationProvider'
import { ServiceProvider, type Services } from '../services/ServiceContext'
import type { Product, ProductChannelPriceOperation, ProductChannelPriceStateSet } from '../services/types'
import Products from './Products'

(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true

let container: HTMLDivElement
let root: ReturnType<typeof createRoot>

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

describe('Products multi-channel price editor', () => {
  it('shows side-by-side channel prices with explicit rial and toman units', async () => {
    const services = servicesFor(makePriceState())
    await renderProducts(services)

    await click('Edit prices')

    expect(container.textContent).toContain('WooCommerce')
    expect(container.textContent).toContain('Snapp Shop')
    expect(container.textContent).toContain('Tapsi Shop')
    expect(container.textContent).toContain('toman')
    expect(container.textContent).toContain('rial')
    expect(container.textContent).toContain('source unit: toman')
    expect(input('Snapp Shop proposed price')?.value).toBe('100,000')
    expect(input('Tapsi Shop proposed price')?.value).toBe('1,000,000')
    expect(container.querySelector('[aria-label="Channel price comparison table"]')?.getAttribute('tabindex')).toBe('0')
    expect(container.querySelector('.min-w-\\[1120px\\]')).not.toBeNull()
  })

  it('submits a human-formatted price as an integer business value', async () => {
    const createDryRun = vi.fn(async () => makeOperation('dry_run_ready', 'snappshop:main'))
    await renderProducts(servicesFor(makePriceState(), { createDryRun }))

    await click('Edit prices')
    await changeInput('Snapp Shop proposed price', '1,250,000')
    await click('Preview / Dry Run')

    const payload = (createDryRun.mock.calls[0] as unknown[])[1] as { changes: Array<{ proposedValue: number }> }
    expect(payload.changes[0].proposedValue).toBe(1250000)
    expect(Number.isInteger(payload.changes[0].proposedValue)).toBe(true)
  })

  it('keeps disconnected and read-only channels non-editable while another channel can dry run', async () => {
    const state = makePriceState()
    state.channels[1] = { ...state.channels[1], readOnly: true, canWrite: false, validationState: 'read_only', validationMessage: 'Channel is not writable from this editor.' }
    state.channels[2] = { ...state.channels[2], connectionState: 'disconnected', canWrite: false, validationState: 'disconnected', validationMessage: 'Channel has no synchronized product row.' }
    const createDryRun = vi.fn(async () => makeOperation('dry_run_ready', 'woocommerce:primary'))
    const services = servicesFor(state, { createDryRun })
    await renderProducts(services)

    await click('Edit prices')

    expect(input('Snapp Shop proposed price')?.hasAttribute('disabled')).toBe(true)
    expect(input('Tapsi Shop proposed price')?.hasAttribute('disabled')).toBe(true)

    await changeInput('WooCommerce proposed price', '120')
    await click('Preview / Dry Run')

    expect(createDryRun).toHaveBeenCalledTimes(1)
    const dryRunPayload = (createDryRun.mock.calls[0] as unknown[])[1] as { changes: unknown[] }
    expect(dryRunPayload.changes).toEqual([
      { channelId: 'woocommerce:primary', proposedValue: 120, staleToken: 'woo-v1', unit: 'EUR' },
    ])
  })

  it('requires explicit approval before Apply and preserves dry run as no external write', async () => {
    const createDryRun = vi.fn(async () => makeOperation('dry_run_ready', 'snappshop:main'))
    const approve = vi.fn(async () => makeOperation('approved', 'snappshop:main'))
    const apply = vi.fn(async () => makeOperation('applied', 'snappshop:main'))
    const services = servicesFor(makePriceState(), { createDryRun, approve, apply })
    await renderProducts(services)

    await click('Edit prices')
    await changeInput('Snapp Shop proposed price', '120000')
    await click('Preview / Dry Run')

    expect(container.textContent).toContain('No external write')
    expect(button('Apply')?.hasAttribute('disabled')).toBe(true)

    await click('Approve')
    await click('Apply')

    expect(approve).toHaveBeenCalledTimes(1)
    expect(apply).toHaveBeenCalledTimes(1)
    expect(container.textContent).toContain('External write performed')
  })

  it('shows partial channel failures without marking successful channels as failed', async () => {
    const createDryRun = vi.fn(async () => makeOperation('dry_run_ready', 'snappshop:main', 'tapsishop:main'))
    const approve = vi.fn(async () => makeOperation('approved', 'snappshop:main', 'tapsishop:main'))
    const apply = vi.fn(async () => makeOperation('partially_failed', 'snappshop:main', 'tapsishop:main'))
    const services = servicesFor(makePriceState(), { createDryRun, approve, apply })
    await renderProducts(services)

    await click('Edit prices')
    await changeInput('Snapp Shop proposed price', '120000')
    await changeInput('Tapsi Shop proposed price', '1200000')
    await click('Preview / Dry Run')
    await click('Approve')
    await click('Apply')

    expect(container.textContent).toContain('Status: partially_failed')
    expect(container.textContent).toContain('Failed 1')
    expect(container.textContent).toContain('invalid price')
    expect(container.textContent).toContain('Success 1')
  })
})

async function renderProducts(services: Services) {
  await act(async () => {
    root.render(
      <NotificationProvider>
        <ServiceProvider services={services}>
          <Products />
        </ServiceProvider>
      </NotificationProvider>,
    )
  })
  await flush()
}

function servicesFor(
  state: ProductChannelPriceStateSet,
  overrides: {
    createDryRun?: ReturnType<typeof vi.fn>
    approve?: ReturnType<typeof vi.fn>
    apply?: ReturnType<typeof vi.fn>
  } = {},
) {
  const products = {
    async getProducts() {
      return { items: [PRODUCT], total: 1, page: 1, pageSize: 20, configured: true }
    },
    async getProduct() { return PRODUCT },
    async getCategories() { return [] },
    async getChannelPrices() { return state },
    async validateChannelPrices() { return state },
    createChannelPriceDryRun: overrides.createDryRun ?? vi.fn(async () => makeOperation('dry_run_ready', 'woocommerce:primary')),
    async getChannelPriceOperation() { return makeOperation('dry_run_ready', 'woocommerce:primary') },
    approveChannelPriceOperation: overrides.approve ?? vi.fn(async () => makeOperation('approved', 'woocommerce:primary')),
    applyChannelPriceOperation: overrides.apply ?? vi.fn(async () => makeOperation('applied', 'woocommerce:primary')),
  }
  return {
    products,
    health: {},
    sources: {},
    workspace: {},
    settings: {},
    activity: {},
    commerce: {},
    writePipeline: {},
  } as unknown as Services
}

const PRODUCT: Product = {
  id: '101',
  name: 'Test Product',
  sku: 'SKU-101',
  currentPrice: 100,
  sourcePrice: null,
  currency: 'EUR',
  status: 'synced',
  lastSynced: new Date('2026-07-11T10:00:00Z'),
  categoryNames: ['Default'],
  productType: 'simple',
}

function makePriceState(): ProductChannelPriceStateSet {
  return {
    product: { id: '101', name: 'Test Product', sku: 'SKU-101', productType: 'simple' },
    version: 'state-v1',
    canonical: { label: 'Canonical/business price', value: 100, currency: 'EUR', unit: 'store currency', freshness: 'fresh', lastSyncedAt: '2026-07-11T10:00:00Z', staleToken: 'canonical-v1' },
    dryRunRequired: true,
    applyRequiresApproval: true,
    channels: [
      channel('woocommerce:primary', 'WooCommerce', 'woocommerce', 100, 'EUR', 'EUR', 'woo-v1'),
      channel('snappshop:main', 'Snapp Shop', 'snappshop', 100000, 'IRR', 'toman', 'snapp-v1'),
      channel('tapsishop:main', 'Tapsi Shop', 'tapsishop', 1000000, 'IRR', 'rial', 'tapsi-v1'),
    ],
  }
}

function channel(channelId: string, channelName: string, connectorType: string, value: number, currency: string, unit: string, staleToken: string) {
  return {
    channelId,
    channelName,
    connectorType,
    channelProductId: `${channelId}:101`,
    sku: 'SKU-101',
    connectionState: 'connected',
    healthStatus: 'ok',
    canRead: true,
    canWrite: true,
    readOnly: false,
    writeCapability: 'products.write_price',
    currentValue: value,
    proposedValue: value,
    currency,
    unit,
    normalizedValue: channelId === 'snappshop:main' ? value * 10 : value,
    normalizedCurrency: channelId === 'woocommerce:primary' ? currency : 'IRR',
    normalizedUnit: channelId === 'woocommerce:primary' ? currency : 'rial',
    freshness: 'fresh',
    lastSyncedAt: '2026-07-11T10:00:00Z',
    validationState: 'valid' as const,
    validationMessage: null,
    pendingChange: false,
    staleToken,
  }
}

function makeOperation(status: ProductChannelPriceOperation['status'], ...channels: string[]): ProductChannelPriceOperation {
  const items = channels.map((channelId, index) => {
    const failed = status === 'partially_failed' && channelId === 'snappshop:main'
    const unit = channelId === 'snappshop:main' ? 'toman' : channelId === 'tapsishop:main' ? 'rial' : 'EUR'
    return {
      id: index + 1,
      channelId,
      connectorType: channelId.split(':')[0],
      channelProductId: `${channelId}:101`,
      sku: 'SKU-101',
      currentValue: channelId === 'woocommerce:primary' ? 100 : channelId === 'snappshop:main' ? 100000 : 1000000,
      proposedValue: channelId === 'woocommerce:primary' ? 120 : channelId === 'snappshop:main' ? 120000 : 1200000,
      currency: channelId === 'woocommerce:primary' ? 'EUR' : 'IRR',
      unit,
      outboundValue: channelId === 'woocommerce:primary' ? 120 : channelId === 'snappshop:main' ? 120000 : 1200000,
      outboundUnit: unit,
      staleToken: `${channelId}-v1`,
      status: failed ? 'failed' : status === 'applied' || status === 'partially_failed' ? 'applied' : 'pending',
      validationState: 'valid',
      errorMessage: failed ? 'invalid price' : null,
      result: {},
    }
  })
  return {
    id: 'mcp_test',
    productId: '101',
    sku: 'SKU-101',
    productName: 'Test Product',
    status,
    version: 'state-v1',
    createdBy: 'tester',
    approvedBy: status === 'approved' || status === 'applied' || status === 'partially_failed' ? 'tester' : null,
    approvalReason: null,
    createdAt: '2026-07-11T10:00:00Z',
    approvedAt: status === 'approved' || status === 'applied' || status === 'partially_failed' ? '2026-07-11T10:01:00Z' : null,
    appliedAt: status === 'applied' || status === 'partially_failed' ? '2026-07-11T10:02:00Z' : null,
    summary: {
      total: items.length,
      pending: status === 'dry_run_ready' || status === 'approved' ? items.length : 0,
      success: status === 'partially_failed' ? 1 : status === 'applied' ? items.length : 0,
      failed: status === 'partially_failed' ? 1 : 0,
      external_write_performed: status === 'applied' || status === 'partially_failed',
    },
    items,
    externalWritePerformed: status === 'applied' || status === 'partially_failed',
    applyRequiresApproval: true,
  }
}

async function click(label: string) {
  const target = button(label)
  expect(target).not.toBeNull()
  await act(async () => target!.click())
  await flush()
}

async function changeInput(label: string, value: string) {
  const target = input(label)
  expect(target).not.toBeNull()
  await act(async () => {
    setInputValue(target!, value)
    target!.dispatchEvent(new Event('input', { bubbles: true }))
    target!.dispatchEvent(new Event('change', { bubbles: true }))
  })
  await flush()
}

function setInputValue(target: HTMLInputElement, value: string) {
  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set
  setter?.call(target, value)
}

function button(label: string): HTMLButtonElement | null {
  return Array.from(container.querySelectorAll('button')).find(item => item.textContent?.trim() === label || item.getAttribute('aria-label') === label) ?? null
}

function input(label: string): HTMLInputElement | null {
  return container.querySelector(`input[aria-label="${label}"]`)
}

async function flush() {
  await act(async () => {
    await Promise.resolve()
    await Promise.resolve()
  })
}
