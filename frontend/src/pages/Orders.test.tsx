// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { createRoot } from 'react-dom/client'
import { act } from 'react'
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
})

describe('Orders page', () => {
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
    expect(container.textContent).toContain('tapsishop')
    expect(container.textContent).toContain('cancelled')
    expect(container.textContent).toContain('IRR')
    expect(container.textContent).toContain('27,000 IRR')
    expect(container.querySelector('.overflow-x-auto table')?.className).toContain('min-w-[1180px]')

    const detailButton = container.querySelector('button')
    await act(async () => {
      detailButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    await flush()

    expect(container.textContent).toContain('tap-item-1')
    expect(container.textContent).toContain('No SKU product')
    expect(container.textContent).toContain('9,000 IRR')
    expect(container.textContent).not.toContain('national')
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
    workspace: {} as Services['workspace'],
    settings: {} as Services['settings'],
    activity: {} as Services['activity'],
    commerce: {} as Services['commerce'],
    writePipeline: {} as Services['writePipeline'],
    orders: {
      getOrders: async () => ({ items: [row], total: 1, page: 1, pageSize: 50 }),
      getOrder: async () => detail,
    },
  }
}

function flush() {
  return act(async () => {
    await Promise.resolve()
    await Promise.resolve()
  })
}
