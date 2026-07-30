// @vitest-environment jsdom
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { MemoryRouter } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthContext, type AuthContextValue } from '../auth'
import { NotificationProvider } from '../notifications/NotificationProvider'
import { ServiceProvider, type Services } from '../services/ServiceContext'
import type { CommerceChannel } from '../services/types'
import type { CommerceService } from '../services/commerce/CommerceService'
import type { OrderService } from '../services/orders/OrderService'
import { changeLocale } from '../i18n'
import Channels from './Channels'

const admin: AuthContextValue = { user: { username: 'admin', role: 'admin', is_admin: true, is_super_admin: false, permissions: {} }, status: 'authenticated', refreshUser: async () => {}, clearAuth: () => {}, logout: async () => {}, authFetch: fetch }
const viewer: AuthContextValue = { ...admin, user: { username: 'viewer', role: 'viewer', is_admin: false, is_super_admin: false, permissions: { can_access_site: true } } }

function channel(overrides: Partial<CommerceChannel> = {}): CommerceChannel {
  return {
    id: 'woocommerce:primary',
    provider: 'woocommerce',
    name: 'WooCommerce EU',
    type: 'Channel',
    status: 'active',
    implemented: true,
    placeholder: false,
    read_only: false,
    write_blocked: false,
    runtime_write_blocked: false,
    credential_status: 'configured',
    last_health_check: '2026-07-23T10:00:00Z',
    health: { status: 'healthy', message: '', latency_ms: 80, error_code: null },
    capabilities: {},
    capabilities_summary: [],
    settings_available: true,
    cached_products: 2418,
    cached_variations: 0,
    last_cache_refresh: '2026-07-23T10:00:00Z',
    cache_refresh_status: 'completed',
    ...overrides,
  }
}

describe('Channels page', () => {
  let container: HTMLDivElement
  let root: ReturnType<typeof createRoot>
  let testChannel: ReturnType<typeof vi.fn>
  let getChannels: ReturnType<typeof vi.fn>
  let getOrders: ReturnType<typeof vi.fn>
  let services: Services

  beforeEach(async () => {
    await changeLocale('en')
    container = document.createElement('div')
    document.body.appendChild(container)
    root = createRoot(container)
    getChannels = vi.fn().mockResolvedValue({
      items: [
        channel(),
        channel({ id: 'snappshop:main', provider: 'snappshop', name: 'SnappShop Store', health: { status: 'degraded', message: '', latency_ms: null, error_code: null }, cached_products: 1876 }),
        channel({ id: 'digikala:pos', provider: 'digikala', name: 'Digikala POS', status: 'disabled', cached_products: 512 }),
      ],
      relationship_map: { nodes: [], example: [], runtime_write_blocked: true, read_only: true },
    })
    getOrders = vi.fn().mockResolvedValue({ items: [], total: 72, page: 1, pageSize: 1 })
    testChannel = vi.fn().mockResolvedValue({ ok: true })
    services = {
      commerce: { getChannels, testChannel, refreshChannelCache: vi.fn() } as unknown as CommerceService,
      orders: { getOrders } as unknown as OrderService,
      health: {} as Services['health'],
      products: {} as Services['products'],
      sources: {} as Services['sources'],
      workspace: {} as Services['workspace'],
      settings: {} as Services['settings'],
      activity: {} as Services['activity'],
      writePipeline: {} as Services['writePipeline'],
    }
  })

  afterEach(async () => {
    act(() => root.unmount())
    container.remove()
    await changeLocale('en')
  })

  async function render(auth = admin) {
    await act(async () => {
      root.render(<AuthContext.Provider value={auth}><NotificationProvider><MemoryRouter><ServiceProvider services={services}><Channels /></ServiceProvider></MemoryRouter></NotificationProvider></AuthContext.Provider>)
      await Promise.resolve(); await Promise.resolve(); await Promise.resolve()
    })
  }

  it('renders real KPI totals and channel cards from live data, with Orders Today from the orders service', async () => {
    await render()

    expect(container.textContent).toContain('Connected Channels')
    expect(container.querySelector('.fh-kpi-card-value')?.textContent).toContain('3')
    expect(container.textContent).toContain('4,806')
    expect(container.textContent).toContain('Orders Today')
    expect(container.textContent).toContain('72')
    expect(getOrders).toHaveBeenCalledWith(expect.objectContaining({ pageSize: 1 }))

    expect(container.querySelectorAll('[data-channel-card]')).toHaveLength(3)
    expect(container.querySelector('[data-channel-card="woocommerce:primary"]')?.textContent).toContain('Healthy')
    expect(container.querySelector('[data-channel-card="snappshop:main"]')?.textContent).toContain('Needs review')
    expect(container.querySelector('[data-channel-card="digikala:pos"]')?.textContent).toContain('Disabled')
  })

  it('excludes Coming Soon placeholders from the Connected Channels KPI', async () => {
    getChannels.mockResolvedValueOnce({
      items: [
        channel(),
        channel({
          id: 'future:main',
          provider: 'future',
          name: 'Future Channel',
          implemented: false,
          placeholder: true,
          credential_status: 'not_configured',
        }),
      ],
      relationship_map: { nodes: [], example: [], runtime_write_blocked: true, read_only: true },
    })

    await render()

    expect(container.querySelector('.fh-kpi-card-value')?.textContent).toBe('1')
    expect(container.querySelectorAll('[data-channel-card]')).toHaveLength(2)
  })

  it('filters channels by search text', async () => {
    await render()

    const search = container.querySelector('input[type="search"]') as HTMLInputElement
    const valueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set
    await act(async () => {
      valueSetter?.call(search, 'snapp')
      search.dispatchEvent(new Event('input', { bubbles: true }))
    })

    expect(Array.from(container.querySelectorAll('[data-channel-card]')).map(item => item.getAttribute('data-channel-card')))
      .toEqual(['snappshop:main'])
  })

  it('calls the real testChannel action for a specific channel', async () => {
    await render()

    const card = container.querySelector('[data-channel-card="woocommerce:primary"]') as HTMLElement
    const testButton = Array.from(card.querySelectorAll('button')).find(item => item.textContent === 'Test connection') as HTMLButtonElement
    await act(async () => { testButton.click(); await Promise.resolve(); await Promise.resolve() })

    expect(testChannel).toHaveBeenCalledWith('woocommerce:primary')
  })

  it('does not offer Test/Refresh/Configure actions on a disabled channel', async () => {
    await render()

    const card = container.querySelector('[data-channel-card="digikala:pos"]') as HTMLElement
    expect(card.querySelectorAll('button')).toHaveLength(0)
    expect(card.textContent).not.toContain('Configure')
  })

  it('keeps admin actions hidden for a read-only user', async () => {
    await render(viewer)

    expect(container.textContent).not.toContain('Add channel')
    expect(container.textContent).not.toContain('Configure')
    expect(container.textContent).not.toContain('Test connection')
    expect(container.textContent).not.toContain('Refresh product cache')
  })

  it('shows a retryable error when the channel list cannot be loaded', async () => {
    getChannels.mockRejectedValueOnce(new Error('offline'))
    await render()

    expect(container.querySelector('[role="alert"]')?.textContent).toContain('Unable to load Commerce Hub')
    getChannels.mockResolvedValueOnce({ items: [channel()], relationship_map: { nodes: [], example: [], runtime_write_blocked: true, read_only: true } })
    const retry = Array.from(container.querySelectorAll('button')).find(button => button.textContent === 'Retry') as HTMLButtonElement
    await act(async () => { retry.click(); await Promise.resolve(); await Promise.resolve() })

    expect(container.querySelector('[data-channel-card="woocommerce:primary"]')).not.toBeNull()
  })
})
