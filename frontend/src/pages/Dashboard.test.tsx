// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { createRoot } from 'react-dom/client'
import { act } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { AuthContext, type AuthContextValue, type AuthUser } from '../auth'
import { ServiceProvider, type Services } from '../services/ServiceContext'
import type { ChannelHealthResponse } from '../services/types'
import Dashboard from './Dashboard'

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
    authFetch: fetch,
  }
}

function services(): Services {
  const channelHealth: ChannelHealthResponse = {
    checkedAt: new Date().toISOString(),
    summary: { overall: 'Warning', counts: { Operational: 1, Warning: 1, Error: 0, 'Unable to check': 0, Disabled: 0 } },
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
        summary: 'Webhook processing is delayed.',
        lastChecked: new Date().toISOString(),
        latency: 31,
        lastSuccessfulOperation: new Date().toISOString(),
        lastErrorCategory: null,
        capabilityState: { read_products: true, write_prices: true },
        nextRecommendedAction: 'Review queued webhooks.',
        dimensions: {},
        lastProductRead: new Date().toISOString(),
        lastProductWrite: null,
        lastOrderSync: new Date().toISOString(),
        polling: { cursor: null, lastRunAt: null },
        webhooks: { supported: true, received: 1, queued: 1, processed: 0, deadLetter: 0, lastReceivedAt: new Date().toISOString(), lastProcessedAt: null },
      },
    ],
  }
  return {
    health: {
      getHealth: vi.fn(),
      getChannelHealth: vi.fn(async () => channelHealth),
      refreshChannelHealth: vi.fn(),
    },
    sources: { getSources: vi.fn(async () => []) } as unknown as Services['sources'],
    products: { getProducts: vi.fn(async () => ({ items: [], total: 0, page: 1, pageSize: 1 })) } as unknown as Services['products'],
    activity: { getEvents: vi.fn(async () => ({ items: [], total: 0, page: 1, pageSize: 5 })) } as unknown as Services['activity'],
    workspace: {} as Services['workspace'],
    settings: {} as Services['settings'],
    commerce: {} as Services['commerce'],
    writePipeline: {} as Services['writePipeline'],
    orders: {} as Services['orders'],
  }
}

beforeEach(() => {
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
  vi.stubGlobal('fetch', vi.fn(async input => {
    const url = String(input)
    if (url.includes('/api/health')) {
      return new Response(JSON.stringify({ status: 'ok', env: 'test', version: '1.0.0' }), { status: 200 })
    }
    return new Response('{}', { status: 404 })
  }))
})

afterEach(() => {
  act(() => { root.unmount() })
  container.remove()
  vi.unstubAllGlobals()
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

describe('Dashboard', () => {
  it('uses normalized channel health for the channel status summary', async () => {
    const { container: c, mockServices } = await renderPage()

    expect(mockServices.health.getChannelHealth).toHaveBeenCalled()
    expect(c.textContent).toContain('Channels')
    expect(c.textContent).toContain('Warning')
    expect(c.textContent).toContain('Webhook processing is delayed.')
  })
})
