// @vitest-environment jsdom
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthContext, type AuthContextValue, type AuthUser } from '../auth'
import { changeLocale } from '../i18n'
import { ServiceProvider, type Services } from '../services/ServiceContext'
import type { ChannelHealthResponse, Source } from '../services/types'
import Dashboard from './Dashboard'

;(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true

let container: HTMLDivElement
let root: ReturnType<typeof createRoot>

const user: AuthUser = {
  username: 'admin',
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
    products: {} as Services['products'],
    activity: {
      getEvents: vi.fn(async () => ({
        items: [
          { id: 'event-1', timestamp: new Date(), kind: 'user_action', level: 'success', actor: 'admin', action: 'source_read_completed', detail: null },
          { id: 'event-2', timestamp: new Date(), kind: 'system_log', level: 'warning', actor: 'system', action: 'channel_health_warning', detail: null },
        ],
        total: 2,
        page: 1,
        pageSize: 5,
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

function card(id: string): HTMLElement {
  const element = container.querySelector<HTMLElement>(`[data-business-card="${id}"]`)
  if (!element) throw new Error(`Missing business card: ${id}`)
  return element
}

describe('Dashboard', () => {
  it('turns persisted business data into complete, actionable seller cards', async () => {
    const { mockServices } = await renderPage()

    expect(mockServices.health.getChannelHealth).toHaveBeenCalled()
    expect(container.querySelectorAll('[data-business-card]')).toHaveLength(8)
    expect(card('price-changes').textContent).toContain('84 changed products')
    expect(card('price-changes').title).toContain('Review today’s price changes')
    expect(card('ready-review').textContent).toContain('76 products')
    expect(card('ready-apply').textContent).toContain('12 products')
    expect(card('blocking').textContent).toContain('3 issues')
    expect(card('warnings').textContent).toContain('5 issues')
    expect(card('orders').textContent).toContain('6 orders')
    expect(card('orders').textContent).toContain('15,000,000 IRR')
    expect(card('inventory').textContent).toContain('9 affected products')
    expect(card('updates').textContent).toContain('1 failed update')
    expect(card('updates').querySelector('.fh-badge [data-icon="error"]')).not.toBeNull()
    expect(container.textContent).not.toContain('Backend')
    expect(container.textContent).not.toContain('Database')
    expect(container.textContent).not.toContain('Application')
  })

  it('uses meaningful empty states instead of bare zero values', async () => {
    const emptySummary = businessSummaryFixture()
    for (const key of Object.keys(emptySummary.metrics)) {
      if (key === 'revenueToday') emptySummary.metrics.revenueToday = []
      else {
        (emptySummary.metrics as unknown as Record<string, number>)[key] = 0
      }
    }
    vi.stubGlobal('fetch', vi.fn(async () => (
      new Response(JSON.stringify(emptySummary), { status: 200 })
    )))

    await renderPage()

    expect(card('price-changes').textContent).toContain('No price changes')
    expect(card('ready-review').textContent).toContain('Nothing ready for Review')
    expect(card('ready-apply').textContent).toContain('Nothing ready for Apply')
    expect(card('blocking').textContent).toContain('No blocking issues')
    expect(card('warnings').textContent).toContain('No warnings')
    expect(card('orders').textContent).toContain('No orders today')
    expect(card('inventory').textContent).toContain('No inventory alerts')
    expect(card('updates').textContent).toContain('Everything synchronized')
    for (const element of container.querySelectorAll('[data-business-card]')) {
      expect(element.querySelector('.fh-business-card-value')?.textContent).not.toBe('0')
    }
  })

  it('does not present a never-checked Channel as a warning', async () => {
    const mockServices = services()
    const originalHealth = await mockServices.health.getChannelHealth()
    const notChecked = {
      ...originalHealth.items[0],
      state: 'NOT_CHECKED' as const,
      status: 'Not checked' as const,
      reason_code: 'credentials_not_checked',
      checked_at: null,
      evidence_source: 'connector_health',
      is_actionable: true,
      recommended_action: 'Run connection test',
      nextRecommendedAction: 'Run connection test',
      lastSuccessfulVerification: null,
    }
    vi.mocked(mockServices.health.getChannelHealth).mockResolvedValue({
      ...originalHealth,
      summary: { overall: 'Not checked', overall_state: 'NOT_CHECKED', counts: { 'Not checked': 1 } },
      items: [notChecked],
    })

    await renderPage(mockServices)

    const channelRow = container.querySelector<HTMLElement>('[data-resource-id="woocommerce:primary"]')
    expect(channelRow?.textContent).toContain('Configured')
    expect(channelRow?.textContent).not.toContain('Warning')
  })

  it('uses the shared active, disabled, and attention ordering for dashboard resources', async () => {
    const mockServices = services()
    const originalHealth = await mockServices.health.getChannelHealth()
    const healthy = originalHealth.items[0]
    const warning = originalHealth.items[1]
    const disabled = {
      ...healthy,
      channelId: 'snappshop:main',
      channelType: 'snappshop',
      enabled: false,
      status: 'Disabled' as const,
      summary: 'Channel is disabled.',
    }
    vi.mocked(mockServices.health.getChannelHealth).mockResolvedValue({
      ...originalHealth,
      items: [disabled, warning, healthy],
    })
    vi.mocked(mockServices.sources.getSources).mockResolvedValue([
      { id: 'source-nextcloud', name: 'Nextcloud', type: 'nextcloud_excel', displayUrl: '', status: 'error', lastSynced: null, productCount: 0 },
      { id: 'source-csv', name: 'CSV', type: 'nextcloud_excel', displayUrl: '', status: 'active', lastSynced: null, productCount: 5 },
      { id: 'source-google', name: 'Google Sheets', type: 'nextcloud_excel', displayUrl: '', status: 'active', lastSynced: null, productCount: 8 },
    ])

    await renderPage(mockServices)
    const ids = Array.from(container.querySelectorAll<HTMLElement>('[data-resource-id]'))
      .map(element => element.dataset.resourceId)

    expect(ids).toEqual([
      'woocommerce:primary',
      'tapsishop:main',
      'snappshop:main',
      'source-csv',
      'source-google',
      'source-nextcloud',
    ])
    expect(container.querySelectorAll('[data-resource-section="disabled"]')).toHaveLength(1)
  })

  it('localizes business decisions in Persian while preserving RTL', async () => {
    await changeLocale('fa')
    await renderPage()

    expect(document.documentElement.dir).toBe('rtl')
    expect(card('price-changes').textContent).toContain('محصولات دارای تغییر قیمت')
    expect(card('ready-review').textContent).toContain('آماده بازبینی')
    expect(card('blocking').textContent).toContain('مشکلات مسدودکننده')
    expect(card('orders').textContent).toContain('سفارش‌ها و درآمد امروز')
    expect(card('updates').textContent).toContain('به‌روزرسانی‌های انتشار')
  })

  it('shows an actionable summary error without fabricating values', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new Error('isolated summary failure') }))
    await renderPage()

    expect(card('price-changes').textContent).toContain('Business data unavailable')
    expect(card('price-changes').textContent).toContain('No values are being estimated')
    expect(card('price-changes').textContent).toContain('Retry')
    expect(card('price-changes').querySelector('.fh-badge [data-icon="warning"]')).not.toBeNull()
  })
})
