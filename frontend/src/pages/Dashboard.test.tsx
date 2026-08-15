// @vitest-environment jsdom
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { MemoryRouter } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthContext, type AuthContextValue, type AuthUser } from '../auth'
import { changeLocale } from '../i18n'
import { ServiceProvider, type Services } from '../services/ServiceContext'
import type { ChannelHealthResponse, ChannelOrderListItem, Source } from '../services/types'
import Dashboard from './Dashboard'

;(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true

let container: HTMLDivElement
let root: ReturnType<typeof createRoot>

const user: AuthUser = {
  id: 1,
  username: 'admin',
  email: 'admin@example.com',
  role: 'admin',
  is_admin: true,
  is_super_admin: false,
  permissions: { can_access_site: true, can_fetch: true, can_view_settings: true },
}

function authValue(): AuthContextValue {
  return {
    user,
    status: 'authenticated',
    refreshUser: async () => undefined,
    clearAuth: () => undefined,
    logout: async () => undefined,
    authFetch: fetch,
  }
}

function channelHealthFixture(): ChannelHealthResponse {
  return {
    checkedAt: new Date().toISOString(),
    summary: { overall: 'Warning', counts: { Operational: 1, Warning: 1 } },
    external_call_performed: false,
    items: [
      {
        channelId: 'woocommerce:primary',
        channelType: 'woocommerce',
        enabled: true,
        accessMode: 'read_only',
        status: 'Operational',
        summary: 'WooCommerce is operational.',
        lastChecked: new Date().toISOString(),
        latency: 15,
        lastSuccessfulOperation: new Date().toISOString(),
        lastErrorCategory: null,
        capabilityState: { read_products: true, write_prices: true },
        connectionTestSupported: true,
        credentialsConfigured: true,
        nextRecommendedAction: 'No immediate action required.',
        dimensions: {},
        lastProductRead: new Date().toISOString(),
        lastProductWrite: null,
        lastOrderSync: new Date().toISOString(),
        polling: { cursor: null, lastRunAt: null },
        webhooks: { supported: false, received: 0, queued: 0, processed: 0, deadLetter: 0, lastReceivedAt: null, lastProcessedAt: null },
      },
      {
        channelId: 'tapsishop:main',
        channelType: 'tapsishop',
        enabled: true,
        accessMode: 'read_only',
        status: 'Warning',
        summary: 'Accepted webhook receipts are waiting for processing.',
        lastChecked: new Date().toISOString(),
        latency: 31,
        lastSuccessfulOperation: new Date().toISOString(),
        lastErrorCategory: null,
        capabilityState: { read_products: true, write_prices: true },
        connectionTestSupported: true,
        credentialsConfigured: true,
        nextRecommendedAction: 'Review queued webhook receipts.',
        dimensions: {},
        lastProductRead: new Date().toISOString(),
        lastProductWrite: null,
        lastOrderSync: new Date().toISOString(),
        polling: { cursor: null, lastRunAt: null },
        webhooks: { supported: true, received: 1, queued: 1, processed: 0, deadLetter: 0, lastReceivedAt: new Date().toISOString(), lastProcessedAt: null },
      },
    ],
  }
}

function sourceFixture(): Source[] {
  return [
    { id: 'source-csv', name: 'CSV', type: 'nextcloud_excel', displayUrl: '', status: 'active', lastSynced: new Date(Date.now() - 300_000), productCount: 2415 },
    { id: 'source-nextcloud', name: 'Nextcloud', type: 'nextcloud_excel', displayUrl: '', status: 'error', lastSynced: null, productCount: 0 },
  ]
}

function businessSummaryFixture() {
  return {
    generatedAt: new Date().toISOString(),
    metrics: {
      productsWithChanges: 84,
      readyForReview: 76,
      readyForApply: 12,
      blockingIssues: 3,
      warnings: 5,
      affectedProducts: 7,
      outOfStockProducts: 9,
      pendingUpdates: 2,
      failedUpdates: 1,
      ordersToday: 6,
      ordersYesterday: 4,
      updatesAppliedToday: 18,
      updatesAppliedYesterday: 12,
      revenueToday: [{ currency: 'IRR', amount: 15_000_000 }],
    },
    businessObservability: {
      openBlockingByDomain: { source_acquisition: 0, pricing: 0, channels: 0, write_pipeline: 2 },
      writePipelinePartialFailureRate30d: 0.25,
      oldestUnresolvedBlockingEventAgeSeconds: 3_600,
    },
  }
}

function services(): Services {
  const channelHealth = channelHealthFixture()
  return {
    health: {
      getHealth: vi.fn(),
      getChannelHealth: vi.fn(async () => channelHealth),
      refreshChannelHealth: vi.fn(),
    },
    sources: { getSources: vi.fn(async () => sourceFixture()) } as unknown as Services['sources'],
    products: {
      getProducts: vi.fn(async () => ({ items: [], total: 1284, page: 1, pageSize: 1 })),
    } as unknown as Services['products'],
    activity: {
      getEvents: vi.fn(async () => ({
        items: [
          { id: 'event-1', timestamp: new Date(), kind: 'user_action', level: 'success', actor: 'admin', action: 'source_read_completed', detail: null },
          { id: 'event-2', timestamp: new Date(), kind: 'system_log', level: 'warning', actor: 'system', action: 'channel_health_warning', detail: null },
        ],
        total: 2,
        page: 1,
        pageSize: 2,
      })),
    } as unknown as Services['activity'],
    workspace: {} as Services['workspace'],
    settings: {} as Services['settings'],
    commerce: {} as Services['commerce'],
    writePipeline: {} as Services['writePipeline'],
    orders: {} as Services['orders'],
  }
}

beforeEach(async () => {
  await changeLocale('en')
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
  vi.stubGlobal('fetch', vi.fn(async input => {
    const url = String(input)
    if (url.includes('/api/v2/dashboard/business-summary')) {
      return new Response(JSON.stringify(businessSummaryFixture()), { status: 200 })
    }
    return new Response('{}', { status: 404 })
  }))
})

afterEach(async () => {
  act(() => { root.unmount() })
  container.remove()
  vi.unstubAllGlobals()
  await changeLocale('en')
})

async function renderPage(mockServices = services()) {
  await act(async () => {
    root.render(
      <MemoryRouter>
        <ServiceProvider services={mockServices}>
          <AuthContext.Provider value={authValue()}>
            <Dashboard />
          </AuthContext.Provider>
        </ServiceProvider>
      </MemoryRouter>,
    )
  })
  await act(async () => { await Promise.resolve() })
  return { container, mockServices }
}

function kpiCardText(label: string): string {
  const labelEl = Array.from(container.querySelectorAll('p')).find(p => p.textContent === label)
  if (!labelEl) throw new Error(`Missing KPI card: ${label}`)
  return labelEl.parentElement?.parentElement?.textContent ?? ''
}

describe('Dashboard', () => {
  it('renders the primary KPI row from live catalog and business data, without fabricating trends', async () => {
    await renderPage()

    expect(kpiCardText('Products Ready')).toContain('1,275')
    expect(kpiCardText('Products Ready')).toContain('9 out of stock')
    expect(kpiCardText('Review Required')).toContain('76')
    expect(kpiCardText('Review Required')).toContain('3 blocking')
    expect(kpiCardText('Apply Ready')).toContain('12')
    expect(kpiCardText('Apply Ready')).toContain('Ready')
    expect(kpiCardText('Orders Today')).toContain('6')
    expect(kpiCardText('Orders Today')).toContain('+50%')
  })

  it('shows the pricing workflow strip and action summary from real metrics', async () => {
    await renderPage()

    expect(container.textContent).toContain('Pricing workflow')
    expect(container.textContent).toContain('76 review')
    expect(container.textContent).toContain('2 dry run')
    expect(container.textContent).toContain('12 apply')
    expect(container.textContent).toContain('Revenue today')
    expect(container.textContent).toContain('15,000,000 IRR')
    expect(container.textContent).toContain('Blocking')
    expect(container.textContent).toContain('Warnings')

    const strip = container.querySelector('.fh-status-strip')
    expect(strip).not.toBeNull()
    expect(strip?.querySelectorAll('.fh-status-strip-cell')).toHaveLength(7)
    expect(strip?.querySelector('.fh-status-strip-footer')).not.toBeNull()
    expect(strip?.querySelector('.fh-status-strip-badges')).not.toBeNull()
    expect(strip?.querySelectorAll('.fh-status-strip-badge')).toHaveLength(3)

    expect(strip?.querySelector('[data-status-metric="revenue"] .fh-status-strip-value')?.getAttribute('data-state')).toBe('neutral')
    expect(strip?.querySelector('[data-status-metric="blocking"] .fh-status-strip-value')?.getAttribute('data-state')).toBe('error')
    expect(strip?.querySelector('[data-status-metric="warnings"] .fh-status-strip-value')?.getAttribute('data-state')).toBe('warning')
    expect(strip?.querySelector('[data-status-metric="freshness"] .fh-status-strip-value')?.getAttribute('data-state')).toBe('neutral')

    // Business Observability v1 KPIs (Owner-approved set): open blocking
    // events by domain, Write Pipeline 30-day partial-failure rate, and the
    // oldest unresolved blocking event's age.
    expect(strip?.querySelector('[data-status-metric="business-events-open"] .fh-status-strip-value')?.textContent).toBe('2')
    expect(strip?.querySelector('[data-status-metric="business-events-open"] .fh-status-strip-value')?.getAttribute('data-state')).toBe('error')
    expect(strip?.querySelector('[data-status-metric="write-batch-success-rate"] .fh-status-strip-value')?.textContent).toBe('75%')
    expect(strip?.querySelector('[data-status-metric="write-batch-success-rate"] .fh-status-strip-value')?.getAttribute('data-state')).toBe('warning')
    expect(strip?.querySelector('[data-status-metric="oldest-open-business-event"] .fh-status-strip-value')?.getAttribute('data-state')).toBe('warning')
  })

  it('keeps revenue currencies separate and uses resolved channel names in chart tooltips', async () => {
    const mockServices = services()
    const health = channelHealthFixture()
    health.items[1] = {
      ...health.items[1],
      displayName: 'فروشگاه تهران',
      displayNameCustom: true,
    }
    vi.mocked(mockServices.health.getChannelHealth).mockResolvedValue(health)
    const order = (
      internalId: number,
      channelId: string,
      currency: string,
      amount: number,
      daysAgo: number,
    ): ChannelOrderListItem => ({
      internalId,
      channelId,
      connectorType: channelId.split(':')[0],
      providerOrderId: `provider-${internalId}`,
      orderNumber: `${internalId}`,
      providerStatus: 'paid',
      normalizedStatus: 'completed',
      createdAtProvider: new Date(Date.now() - daysAgo * 86_400_000).toISOString(),
      updatedAtProvider: null,
      currency,
      finalAmount: amount,
      itemCount: 1,
      synchronizationState: 'synced',
      eventSource: 'poll',
      errorState: null,
      lastSeenAt: null,
      customerDisplay: null,
      paymentStatus: 'paid',
      fulfillmentStatus: 'fulfilled',
    })
    mockServices.orders = {
      getOrders: vi.fn(async () => ({
        items: [
          order(1, 'woocommerce:primary', 'EUR', 100, 3),
          order(2, 'woocommerce:primary', 'EUR', 200, 2),
          order(3, 'tapsishop:main', 'USD', 50, 3),
          order(4, 'tapsishop:main', 'USD', 75, 2),
        ],
        total: 4,
        page: 1,
        pageSize: 50,
      })),
    } as unknown as Services['orders']

    await renderPage(mockServices)

    expect(container.querySelectorAll('[data-revenue-currency]')).toHaveLength(2)
    expect(container.querySelector('[data-revenue-currency="EUR"]')).not.toBeNull()
    expect(container.querySelector('[data-revenue-currency="USD"]')).not.toBeNull()
    expect(container.querySelector('[title^="WooCommerce:"]')).not.toBeNull()
    expect(container.querySelector('[title^="فروشگاه تهران:"]')).not.toBeNull()
    expect(container.querySelector('[title^="TapsiShop:"]')).toBeNull()
    expect(container.textContent).toContain('Last 30 days')
    expect(container.textContent).not.toContain('Loaded orders')
  })

  it('unifies channel and source health into one prioritized list, healthy first', async () => {
    await renderPage()

    const rows = Array.from(container.querySelectorAll<HTMLElement>('[data-health-row]'))
    expect(rows).toHaveLength(2)
    expect(rows[0].dataset.healthTone).toBe('success')
    expect(rows[0].textContent).toContain('Healthy')
    expect(container.textContent).toContain('Channel health')
  })

  it('uses persisted channel display-name metadata in Dashboard health rows', async () => {
    const mockServices = services()
    const health = channelHealthFixture()
    health.items = [
      { ...health.items[0], displayName: 'ووکامرس', displayNameCustom: false },
      { ...health.items[1], displayName: 'فروشگاه تهران', displayNameCustom: true },
    ]
    vi.mocked(mockServices.health.getChannelHealth).mockResolvedValue(health)
    vi.mocked(mockServices.sources.getSources).mockResolvedValue([])

    await renderPage(mockServices)

    const systemDefault = container.querySelector('[data-health-row="channel:woocommerce:primary"]')
    const ownerCustom = container.querySelector('[data-health-row="channel:tapsishop:main"]')
    expect(systemDefault?.textContent).toContain('WooCommerce')
    expect(systemDefault?.textContent).not.toContain('ووکامرس')
    expect(ownerCustom?.textContent).toContain('فروشگاه تهران')
  })

  it('shows warning tone and the correct entity icon for attention-tier health rows', async () => {
    const mockServices = services()
    const onlyWarningChannel = channelHealthFixture()
    onlyWarningChannel.items = [onlyWarningChannel.items[1]]
    onlyWarningChannel.summary = { overall: 'Warning', counts: { Warning: 1 } }
    vi.mocked(mockServices.health.getChannelHealth).mockResolvedValue(onlyWarningChannel)
    vi.mocked(mockServices.sources.getSources).mockResolvedValue([
      { id: 'source-nextcloud', name: 'Nextcloud', type: 'nextcloud_excel', displayUrl: '', status: 'error', lastSynced: null, productCount: 0 },
    ])

    await renderPage(mockServices)

    const rows = Array.from(container.querySelectorAll<HTMLElement>('[data-health-row]'))
    expect(rows).toHaveLength(2)
    expect(rows.every(row => row.dataset.healthTone === 'warning')).toBe(true)
    expect(rows.every(row => row.textContent?.includes('Warning'))).toBe(true)
    expect(container.textContent).toContain('2 warnings')
  })

  it('localizes the dashboard in Persian while preserving RTL', async () => {
    await changeLocale('fa')
    await renderPage()

    expect(document.documentElement.dir).toBe('rtl')
    expect(kpiCardText('محصولات آماده')).toContain('۱٬۲۷۵')
    expect(kpiCardText('نیازمند بازبینی')).toContain('۷۶')
    expect(kpiCardText('آماده اعمال')).toContain('۱۲')
    expect(container.textContent).toContain('فرایند قیمت‌گذاری')
    expect(container.textContent).toContain('وضعیت کانال‌ها')
  })

  it('shows a real business-summary failure without fabricating KPI values', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new Error('isolated summary failure') }))
    await renderPage()

    expect(kpiCardText('Review Required')).toContain('-')
    expect(kpiCardText('Review Required')).not.toMatch(/\b0\b/)
    expect(kpiCardText('Apply Ready')).toContain('-')
    expect(kpiCardText('Apply Ready')).not.toMatch(/\b0\b/)
  })
})
