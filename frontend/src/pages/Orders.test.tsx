// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { createRoot } from 'react-dom/client'
import { act } from 'react'
import { ApiError } from '../api/client'
import { ServiceProvider, type Services } from '../services/ServiceContext'
import type { ChannelOrderDetail, ChannelOrderListItem } from '../services/types'
import Orders from './Orders'

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
  window.history.replaceState({}, '', '/')
})

describe('Orders page', () => {
  it('applies URL filters when opened from an actionable summary', async () => {
    const mock = services()
    let requested: unknown
    mock.orders!.getOrders = async filter => {
      requested = filter
      return { items: [], total: 0, page: 1, pageSize: 25 }
    }
    window.history.replaceState({}, '', '/orders?dateFrom=2026-08-10&dateTo=2026-08-10')

    await act(async () => {
      root.render(<ServiceProvider services={mock}><Orders /></ServiceProvider>)
    })
    await flush()

    expect(requested).toMatchObject({ dateFrom: '2026-08-10', dateTo: '2026-08-10' })
  })

  it('does not show WooCommerce sync evidence for a selected channel without its own status', async () => {
    const mock = services()
    mock.orders!.getOrders = async () => ({ items: [], total: 0, page: 1, pageSize: 25 })
    mock.orders!.getSyncStatus = async () => ({
      items: [{
        channelId: 'woocommerce:primary',
        connectorType: 'woocommerce',
        displayName: 'WooCommerce',
        enabled: true,
        state: 'ready',
        lastRunAt: '2026-08-12T10:00:00Z',
        lastSuccessAt: '2026-08-12T10:00:00Z',
        lastFailureAt: null,
        failureCategory: null,
      }],
    })
    window.history.replaceState({}, '', '/orders?channelId=technolife:main')

    await act(async () => {
      root.render(<ServiceProvider services={mock}><Orders /></ServiceProvider>)
    })
    await flush()

    const strip = container.querySelector('[data-orders-sync-strip]') as HTMLElement
    expect(strip.textContent).toContain('Unavailable')
    expect(strip.textContent).not.toContain('Synced')
    expect(strip.textContent).not.toContain('Last synchronized')
    const sync = Array.from(container.querySelectorAll('button')).find(button => button.textContent === 'Sync orders') as HTMLButtonElement
    expect(sync.disabled).toBe(true)
  })

  it('preserves an explicitly custom legacy alias in the Channel filter and order rows', async () => {
    const mock = services()
    const base = (await mock.orders!.getOrders({ page: 1, pageSize: 25 })).items[0]!
    mock.orders!.getOrders = async () => ({
      items: [{ ...base, channelId: 'woocommerce:primary', connectorType: 'woocommerce' }],
      total: 1,
      page: 1,
      pageSize: 25,
    })
    mock.orders!.getSyncStatus = async () => ({
      items: [{
        channelId: 'woocommerce:primary',
        connectorType: 'woocommerce',
        displayName: 'ووکامرس',
        displayNameCustom: true,
        enabled: true,
        state: 'ready',
        lastRunAt: null,
        lastSuccessAt: null,
        lastFailureAt: null,
        failureCategory: null,
      }],
    })

    await act(async () => {
      root.render(<ServiceProvider services={mock}><Orders /></ServiceProvider>)
    })
    await flush()

    const channelOption = container.querySelector('select option[value="woocommerce:primary"]')
    expect(channelOption?.textContent).toBe('ووکامرس')
    expect(container.querySelector('[data-orders-row]')?.textContent).toContain('ووکامرس')
  })

  it('shows normalized channel orders and detail without customer national ID', async () => {
    await act(async () => {
      root.render(
        <ServiceProvider services={services()}>
          <Orders />
        </ServiceProvider>,
      )
    })
    await flush()

    expect(container.textContent).toContain('T-200')
    expect(container.textContent).toContain('Tapsi')
    expect(container.textContent).toContain('Cancelled')
    expect(container.textContent).toContain('IRR')
    expect(container.textContent).toContain('27,000 IRR')
    expect(container.textContent).toContain('Test buyer')
    expect(container.querySelector('.overflow-x-auto table')?.className).toContain('min-w-[1020px]')

    const detailButton = Array.from(container.querySelectorAll('button')).find(
      button => button.textContent === 'T-200',
    )
    await act(async () => {
      detailButton?.focus()
      detailButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    await flush()

    expect(container.querySelector('[data-order-details-dialog]')).toBeTruthy()
    expect(container.querySelector('[role="dialog"]')?.textContent).toContain('Order details')
    expect(container.querySelector('[role="dialog"]')?.textContent).toContain('provider-200')
    expect(container.querySelector('[role="dialog"]')?.textContent).toContain('7')
    expect(container.textContent).toContain('tap-item-1')
    expect(container.textContent).toContain('No SKU product')
    expect(container.textContent).toContain('9,000 IRR')
    expect(container.textContent).not.toContain('national')

    const close = container.querySelector<HTMLButtonElement>('[aria-label="Close order details"]')
    await act(async () => close?.click())
    expect(container.querySelector('[data-order-details-dialog]')).toBeNull()
    expect(document.activeElement).toBe(detailButton)
  })

  it('opens visible details from the row menu and invokes the internal order endpoint binding', async () => {
    const mock = services()
    const getOrder = vi.fn(mock.orders!.getOrder)
    mock.orders!.getOrder = getOrder
    await act(async () => root.render(<ServiceProvider services={mock}><Orders /></ServiceProvider>))
    await flush()

    await act(async () => container.querySelector<HTMLButtonElement>('[data-row-menu-trigger]')?.click())
    const viewDetails = Array.from(container.querySelectorAll<HTMLButtonElement>('[role="menuitem"]'))
      .find(button => button.textContent === 'View details')
    await act(async () => viewDetails?.click())
    await flush()

    expect(getOrder).toHaveBeenCalledWith(7)
    expect(container.querySelector('[data-order-details-dialog]')).toBeTruthy()
    expect(container.querySelector('[data-order-detail]')?.textContent).toContain('Test buyer')
  })

  it('distinguishes never-synchronized state and runs an explicit read-only sync', async () => {
    const mock = services()
    let syncCalls = 0
    mock.orders!.getOrders = async () => ({ items: [], total: 0, page: 1, pageSize: 25 })
    mock.orders!.getSyncStatus = async () => ({
      items: [{
        channelId: 'woocommerce:primary',
        connectorType: 'woocommerce',
        displayName: 'WooCommerce',
        enabled: true,
        state: 'never_run',
        lastRunAt: null,
        lastSuccessAt: null,
        lastFailureAt: null,
        failureCategory: null,
      }],
    })
    mock.orders!.syncChannel = async channelId => {
      syncCalls += 1
      return {
        channelId,
        source: 'reconciliation',
        processed: 0,
        duplicates: 0,
        state: 'completed',
        canonicalInventoryMutated: false,
        productPricesWritten: false,
        providerMutationPerformed: false,
      }
    }

    await act(async () => {
      root.render(<ServiceProvider services={mock}><Orders /></ServiceProvider>)
    })
    await flush()

    expect(container.textContent).toContain('Order synchronization has not run yet')
    const syncButton = Array.from(container.querySelectorAll('button')).find(
      button => button.textContent === 'Sync orders',
    )
    await act(async () => {
      syncButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    await flush()
    expect(syncCalls).toBe(1)
  })

  it('retries a per-row sync failure from the Sync column', async () => {
    const failingRow: ChannelOrderListItem = {
      internalId: 9,
      channelId: 'woocommerce:primary',
      connectorType: 'woocommerce',
      providerOrderId: 'provider-900',
      orderNumber: 'W-900',
      providerStatus: '5',
      normalizedStatus: 'processing',
      createdAtProvider: '2026-07-11T10:00:00Z',
      updatedAtProvider: '2026-07-11T10:05:00Z',
      currency: 'IRR',
      finalAmount: 15000,
      itemCount: 1,
      synchronizationState: 'failed',
      eventSource: 'woocommerce_poll',
      errorState: 'timeout',
      lastSeenAt: '2026-07-11T10:05:00Z',
      customerDisplay: 'Retry buyer',
      paymentStatus: 'paid',
      fulfillmentStatus: 'pending',
    }
    const mock = services()
    let retriedChannelId = ''
    mock.orders!.getOrders = async () => ({ items: [failingRow], total: 1, page: 1, pageSize: 25 })
    mock.orders!.syncChannel = async channelId => {
      retriedChannelId = channelId
      return {
        channelId,
        source: 'reconciliation',
        processed: 1,
        duplicates: 0,
        state: 'completed',
        canonicalInventoryMutated: false,
        productPricesWritten: false,
        providerMutationPerformed: false,
      }
    }

    await act(async () => {
      root.render(<ServiceProvider services={mock}><Orders /></ServiceProvider>)
    })
    await flush()

    const retryButton = Array.from(container.querySelectorAll('button')).find(
      button => button.textContent === 'Retry',
    )
    expect(retryButton).toBeTruthy()
    await act(async () => {
      retryButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    await flush()

    expect(retriedChannelId).toBe('woocommerce:primary')
  })

  it('shows a recoverable error when order details cannot be loaded', async () => {
    const mock = services()
    mock.orders!.getOrder = async () => { throw new Error('detail unavailable') }

    await act(async () => {
      root.render(<ServiceProvider services={mock}><Orders /></ServiceProvider>)
    })
    await flush()

    const detailButton = Array.from(container.querySelectorAll('button')).find(
      button => button.textContent === 'T-200',
    )
    await act(async () => {
      detailButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    await flush()

    expect(container.querySelector('[role="alert"]')?.textContent).toContain('Order details could not be loaded')
    expect(container.querySelector('[data-order-details-dialog]')).toBeTruthy()
  })

  it('shows a specific not-found state', async () => {
    const mock = services()
    mock.orders!.getOrder = async () => { throw new ApiError(404, 'not found') }

    await act(async () => root.render(<ServiceProvider services={mock}><Orders /></ServiceProvider>))
    await flush()
    const detailButton = Array.from(container.querySelectorAll('button')).find(
      button => button.textContent === 'T-200',
    )
    await act(async () => detailButton?.dispatchEvent(new MouseEvent('click', { bubbles: true })))
    await flush()

    expect(container.querySelector('[role="alert"]')?.textContent).toContain('This order could not be found')
    expect(container.querySelector('[data-order-details-dialog]')).toBeTruthy()
  })

  it('keeps valid order details visible when optional exchange rates are unavailable', async () => {
    const mock = services()
    mock.exchangeRates = {
      getLatest: async () => { throw new Error('optional exchange-rate failure') },
    } as unknown as Services['exchangeRates']

    await act(async () => root.render(<ServiceProvider services={mock}><Orders /></ServiceProvider>))
    await flush()
    const detailButton = Array.from(container.querySelectorAll('button')).find(
      button => button.textContent === 'T-200',
    )
    await act(async () => detailButton?.dispatchEvent(new MouseEvent('click', { bubbles: true })))
    await flush()

    expect(container.querySelector('[data-order-detail]')?.textContent).toContain('Test buyer')
    expect(container.querySelector('[role="alert"]')).toBeNull()
  })
})

function services(): Services {
  const row: ChannelOrderListItem = {
    internalId: 7,
    channelId: 'tapsi:1',
    connectorType: 'tapsishop',
    providerOrderId: 'provider-200',
    orderNumber: 'T-200',
    providerStatus: '2',
    normalizedStatus: 'cancelled',
    createdAtProvider: '2026-07-11T10:00:00Z',
    updatedAtProvider: '2026-07-11T10:05:00Z',
    currency: 'IRR',
    finalAmount: 27000,
    itemCount: 1,
    synchronizationState: 'synced',
    eventSource: 'tapsishop_webhook',
    errorState: null,
    lastSeenAt: '2026-07-11T10:05:00Z',
    customerDisplay: 'Test buyer',
    paymentStatus: 'paid',
    fulfillmentStatus: 'pending',
  }
  const detail: ChannelOrderDetail = {
    ...row,
    items: [{
      providerItemId: 'tap-item-1',
      externalProductId: 'tap-prod-1',
      sku: null,
      productNumber: null,
      parentProductNumber: null,
      name: 'No SKU product',
      quantity: 3,
      canceledQuantity: 3,
      deliverableQuantity: 0,
      originalPrice: 9000,
      finalPrice: 9000,
      itemStatus: 'cancelled',
      cancellationReason: null,
    }],
    shipments: [],
    invoices: [],
    timeline: [{ eventName: 'order_normalized', message: 'Stored', createdAt: '2026-07-11T10:05:00Z', metadata: {} }],
  }
  return {
    health: {} as Services['health'],
    products: {} as Services['products'],
    sources: {} as Services['sources'],
    settings: {} as Services['settings'],
    activity: {} as Services['activity'],
    commerce: {} as Services['commerce'],
    writePipeline: {} as Services['writePipeline'],
    orders: {
      getOrders: async () => ({ items: [row], total: 1, page: 1, pageSize: 50 }),
      getOrder: async () => detail,
      getSyncStatus: async () => ({
        items: [{
          channelId: 'woocommerce:primary',
          connectorType: 'woocommerce',
          displayName: 'WooCommerce',
          enabled: true,
          state: 'ready',
          lastRunAt: '2026-07-11T10:05:00Z',
          lastSuccessAt: '2026-07-11T10:05:00Z',
          lastFailureAt: null,
          failureCategory: null,
        }],
      }),
      syncChannel: async channelId => ({
        channelId,
        source: 'reconciliation',
        processed: 1,
        duplicates: 0,
        state: 'completed',
        canonicalInventoryMutated: false,
        productPricesWritten: false,
        providerMutationPerformed: false,
      }),
    },
  }
}

function flush() {
  return act(async () => {
    await Promise.resolve()
    await Promise.resolve()
  })
}
