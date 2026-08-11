// @vitest-environment jsdom
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { MemoryRouter, useLocation } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthContext, type AuthContextValue } from '../auth'
import { NotificationProvider } from '../notifications/NotificationProvider'
import { ServiceProvider, type Services } from '../services/ServiceContext'
import type { CommerceChannel, CommerceTypeOption } from '../services/types'
import type { CommerceService } from '../services/commerce/CommerceService'
import type { OrderService } from '../services/orders/OrderService'
import { changeLocale } from '../i18n'
import { channelConnectionEvidence } from './ChannelDetail'
import Channels from './Channels'

const admin: AuthContextValue = { user: { username: 'admin', role: 'admin', is_admin: true, is_super_admin: false, permissions: {} }, status: 'authenticated', refreshUser: async () => {}, clearAuth: () => {}, logout: async () => {}, authFetch: fetch }
const viewer: AuthContextValue = { ...admin, user: { username: 'viewer', role: 'viewer', is_admin: false, is_super_admin: false, permissions: { can_access_site: true } } }

function LocationProbe() {
  const location = useLocation()
  return <output data-testid="location-probe">{location.pathname}{location.search}</output>
}

function setInputValue(input: HTMLInputElement, value: string) {
  Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set?.call(input, value)
  input.dispatchEvent(new Event('input', { bubbles: true }))
}

function channel(overrides: Partial<CommerceChannel> = {}): CommerceChannel {
  return {
    id: 'woocommerce:primary',
    provider: 'woocommerce',
    name: 'WooCommerce EU',
    type: 'Channel',
    status: 'active',
    implemented: true,
    placeholder: false,
    enabled: true,
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
  let getChannelTypes: ReturnType<typeof vi.fn>
  let getChannelConfiguration: ReturnType<typeof vi.fn>
  let saveChannel: ReturnType<typeof vi.fn>
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
        channel({ id: 'digikala:pos', provider: 'digikala', name: 'Digikala POS', status: 'disabled', enabled: false, cached_products: 512 }),
      ],
      relationship_map: { nodes: [], example: [], runtime_write_blocked: true, read_only: true },
    })
    getOrders = vi.fn().mockResolvedValue({ items: [], total: 72, page: 1, pageSize: 1 })
    testChannel = vi.fn().mockResolvedValue({ ok: true })
    const channelTypes: CommerceTypeOption[] = ['woocommerce:primary', 'snappshop:main', 'digikala:pos'].map(id => ({
      id,
      provider: id.split(':')[0],
      name: id === 'woocommerce:primary' ? 'WooCommerce EU' : id === 'snappshop:main' ? 'SnappShop Store' : 'Digikala',
      type: 'Channel',
      implemented: true,
      placeholder: false,
      read_only: false,
      runtime_write_blocked: false,
      settings_schema: id === 'woocommerce:primary' ? [
        { key: 'url', label: 'Store URL', required: true, secret: false },
        { key: 'key', label: 'Consumer key', required: true, secret: true },
        { key: 'secret', label: 'Consumer secret', required: true, secret: true },
      ] : [],
    }))
    getChannelTypes = vi.fn().mockResolvedValue({ items: channelTypes })
    getChannelConfiguration = vi.fn().mockImplementation(async (channelId: string) => ({
      channel_id: channelId,
      provider: channelId.split(':')[0],
      display_name: channelTypes.find(item => item.id === channelId)?.name ?? channelId,
      configured: channelId !== 'digikala:pos',
      enabled: channelId !== 'digikala:pos',
      access_mode: 'read_only' as const,
      settings: channelId === 'woocommerce:primary' ? { url: 'https://shop.example.test' } : {},
      secrets: channelId === 'woocommerce:primary' ? {
        key: { status: 'configured', replaced_at: '2026-08-10T10:00:00Z' },
        secret: { status: 'configured', replaced_at: '2026-08-10T10:00:00Z' },
      } : {},
      token_configured: false,
      webhook_token_configured: false,
      settings_schema: channelTypes.find(item => item.id === channelId)?.settings_schema ?? [],
      webhook_path: null,
      credentials_returned: false as const,
      currency_profile: { status: 'resolved' as const, currency: 'IRR', unit: 'RIAL' },
    }))
    saveChannel = vi.fn().mockResolvedValue({
      settings: { url: 'https://shop.example.test' },
      secrets: {
        key: { status: 'configured', replaced_at: '2026-08-10T10:00:00Z' },
        secret: { status: 'configured', replaced_at: '2026-08-10T10:00:00Z' },
      },
      configured: true,
      read_only: true,
      runtime_write_blocked: true,
      write_blocked: true,
    })
    services = {
      commerce: { getChannels, getChannelTypes, getChannelConfiguration, saveChannel, testChannel, refreshChannelCache: vi.fn() } as unknown as CommerceService,
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

  async function render(auth = admin, initialEntry = '/channels') {
    await act(async () => {
      root.render(<main><AuthContext.Provider value={auth}><NotificationProvider><MemoryRouter initialEntries={[initialEntry]}><LocationProbe /><ServiceProvider services={services}><Channels /></ServiceProvider></MemoryRouter></NotificationProvider></AuthContext.Provider></main>)
      await Promise.resolve(); await Promise.resolve(); await Promise.resolve()
    })
  }

  it('renders real KPI totals and channel cards from live data, with Orders Today from the orders service', async () => {
    await render()

    expect(container.textContent).toContain('Connected Channels')
    expect(container.querySelector('[data-channel-kpi="connected"] .fh-kpi-card-value')?.textContent).toBe('2')
    expect(container.querySelector('[data-channel-kpi="healthy-listings"] .fh-kpi-card-value')?.textContent).toBe('2,418')
    expect(container.textContent).toContain('2,418')
    expect(container.textContent).toContain('Orders Today')
    expect(container.textContent).toContain('72')
    expect(getOrders).toHaveBeenCalledWith(expect.objectContaining({ pageSize: 1 }))

    expect(container.querySelectorAll('[data-channel-card]')).toHaveLength(3)
    expect(container.querySelector('[data-channel-card="woocommerce:primary"]')?.textContent).toContain('Healthy')
    expect(container.querySelector('[data-channel-card="snappshop:main"]')?.textContent).toContain('Warning')
    expect(container.querySelector('[data-channel-card="snappshop:main"]')?.textContent).toContain('needs attention')
    expect(container.querySelector('[data-channel-card="digikala:pos"]')?.textContent).toContain('Setup required')
  })

  it('drills channel KPIs into the records behind each number', async () => {
    await render()

    await act(async () => {
      (container.querySelector('[data-channel-kpi="connected"]') as HTMLButtonElement).click()
    })
    expect(Array.from(container.querySelectorAll('[data-channel-card]')).map(item => item.getAttribute('data-channel-card')))
      .toEqual(['woocommerce:primary', 'snappshop:main'])

    await act(async () => {
      (container.querySelector('[data-channel-kpi="healthy-listings"]') as HTMLButtonElement).click()
    })
    expect(Array.from(container.querySelectorAll('[data-channel-card]')).map(item => item.getAttribute('data-channel-card')))
      .toEqual(['woocommerce:primary'])

    await act(async () => {
      (container.querySelector('[data-channel-kpi="attention"]') as HTMLButtonElement).click()
    })
    expect(Array.from(container.querySelectorAll('[data-channel-card]')).map(item => item.getAttribute('data-channel-card')))
      .toEqual(['snappshop:main', 'digikala:pos'])

    await act(async () => {
      (container.querySelector('[data-channel-kpi="orders-today"]') as HTMLButtonElement).click()
    })
    const today = new Date().toISOString().slice(0, 10)
    expect(container.querySelector('[data-testid="location-probe"]')?.textContent)
      .toBe(`/orders?dateFrom=${today}&dateTo=${today}`)
  })

  it('uses English for legacy system defaults while preserving a custom Persian channel name', async () => {
    getChannels.mockResolvedValueOnce({
      items: [
        channel({ name: 'ووکامرس' }),
        channel({ id: 'snappshop:main', provider: 'snappshop', name: 'اسنپ شاپ' }),
        channel({ id: 'tapsishop:main', provider: 'tapsishop', name: 'تپ‌سی شاپ' }),
        channel({ id: 'technolife:main', provider: 'technolife', name: 'تکنولایف' }),
        channel({ id: 'snappshop:tehran', provider: 'snappshop', name: 'فروشگاه تهران', display_name_custom: true }),
      ],
      relationship_map: { nodes: [], example: [], runtime_write_blocked: true, read_only: true },
    })

    await render()

    expect(container.querySelector('[data-channel-card="woocommerce:primary"]')?.textContent).toContain('WooCommerce')
    expect(container.querySelector('[data-channel-card="snappshop:main"]')?.textContent).toContain('SnappShop')
    expect(container.querySelector('[data-channel-card="tapsishop:main"]')?.textContent).toContain('TapsiShop')
    expect(container.querySelector('[data-channel-card="technolife:main"]')?.textContent).toContain('Technolife')
    expect(container.querySelector('[data-channel-card="snappshop:tehran"]')?.textContent).toContain('فروشگاه تهران')
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

  it('offers only the setup workflow on a disabled channel', async () => {
    await render()

    const card = container.querySelector('[data-channel-card="digikala:pos"]') as HTMLElement
    expect(Array.from(card.querySelectorAll('button')).map(button => button.textContent?.trim())).toEqual(['Setup now'])
    expect(card.querySelectorAll('.fh-badge')).toHaveLength(1)
    expect(card.textContent?.match(/Setup required/g) ?? []).toHaveLength(1)
    expect(card.textContent).not.toContain('Test connection')
    expect(card.textContent).not.toContain('Refresh cache')
  })

  it('does not display a backend-disabled configured channel as connected', async () => {
    getChannels.mockResolvedValueOnce({
      items: [channel({ enabled: false, status: 'configured', credential_status: 'configured' })],
      relationship_map: { nodes: [], example: [], runtime_write_blocked: true, read_only: true },
    })

    await render()

    const card = container.querySelector('[data-channel-card="woocommerce:primary"]') as HTMLElement
    expect(container.querySelector('[data-channel-kpi="connected"] .fh-kpi-card-value')?.textContent).toBe('0')
    expect(container.querySelector('[data-channel-kpi="healthy-listings"] .fh-kpi-card-value')?.textContent).toBe('0')
    expect(card.textContent).toContain('Setup required')
    expect(card.textContent).not.toContain('Connected')
    expect(Array.from(card.querySelectorAll('button')).map(button => button.textContent?.trim())).toEqual(['Setup now'])
  })

  it('distinguishes configured metadata from verified healthy evidence', async () => {
    getChannels.mockResolvedValueOnce({
      items: [channel({
        status: 'configured',
        health: { status: 'unknown', message: 'No health check has been recorded.', latency_ms: null, error_code: null },
        last_health_check: null,
      })],
      relationship_map: { nodes: [], example: [], runtime_write_blocked: true, read_only: true },
    })

    await render()

    const card = container.querySelector('[data-channel-card="woocommerce:primary"]') as HTMLElement
    expect(container.querySelector('[data-channel-kpi="connected"] .fh-kpi-card-value')?.textContent).toBe('1')
    expect(container.querySelector('[data-channel-kpi="healthy-listings"] .fh-kpi-card-value')?.textContent).toBe('0')
    expect(card.textContent).toContain('Configured')
    expect(card.textContent).not.toContain('Healthy')
    expect(card.textContent).not.toContain('Connected')
    expect(Array.from(card.querySelectorAll('button')).map(button => button.textContent?.trim())).toContain('Test connection')
  })

  it('opens Add Channel on the canonical page without rendering a second card collection', async () => {
    await render()

    const add = Array.from(container.querySelectorAll('button')).find(item => item.textContent?.trim() === 'Add channel') as HTMLButtonElement
    await act(async () => { add.click(); await Promise.resolve(); await Promise.resolve(); await Promise.resolve() })

    expect(container.querySelector('[data-testid="channel-configuration-dialog"]')).not.toBeNull()
    expect(container.querySelector('[role="dialog"]')?.textContent).toContain('Add channel')
    expect(container.querySelectorAll('[data-channel-card]')).toHaveLength(3)
    expect(getChannelTypes).toHaveBeenCalledTimes(1)
  })

  it('opens Setup Now and connected Settings in the same canonical dialog', async () => {
    await render()

    const setupCard = container.querySelector('[data-channel-card="digikala:pos"]') as HTMLElement
    const setup = Array.from(setupCard.querySelectorAll('button')).find(item => item.textContent?.trim() === 'Setup now') as HTMLButtonElement
    await act(async () => { setup.click(); await Promise.resolve(); await Promise.resolve(); await Promise.resolve() })
    expect(container.querySelector('[role="dialog"]')?.textContent).toContain('Configure Digikala — Pos')
    expect(getChannelConfiguration).toHaveBeenCalledWith('digikala:pos')
    expect(container.querySelector('main')?.className).toContain('fh-modal-scroll-lock')

    const close = Array.from(container.querySelectorAll('[role="dialog"] button')).find(item => item.textContent?.trim() === 'Close') as HTMLButtonElement
    await act(async () => close.click())
    expect(container.querySelector('main')?.className).not.toContain('fh-modal-scroll-lock')
    const connectedCard = container.querySelector('[data-channel-card="woocommerce:primary"]') as HTMLElement
    const settings = Array.from(connectedCard.querySelectorAll('button')).find(item => item.textContent?.trim() === 'Settings') as HTMLButtonElement
    await act(async () => { settings.click(); await Promise.resolve(); await Promise.resolve(); await Promise.resolve() })
    expect(container.querySelector('[role="dialog"]')?.textContent).toContain('Configure WooCommerce')
    expect(container.querySelectorAll('[data-channel-card]')).toHaveLength(3)
  })

  it('shows configured channel secrets as write-only and preserves them when Save submits blanks', async () => {
    await render()
    const card = container.querySelector('[data-channel-card="woocommerce:primary"]') as HTMLElement
    const settings = Array.from(card.querySelectorAll('button')).find(item => item.textContent?.trim() === 'Settings') as HTMLButtonElement
    await act(async () => { settings.click(); await Promise.resolve(); await Promise.resolve(); await Promise.resolve() })

    const dialog = container.querySelector('[role="dialog"]') as HTMLElement
    const secretInputs = Array.from(dialog.querySelectorAll<HTMLInputElement>('input[type="password"]'))
    expect(secretInputs).toHaveLength(2)
    expect(secretInputs.every(input => input.value === '')).toBe(true)
    expect(secretInputs.every(input => input.placeholder === 'Configured — type a new password to replace')).toBe(true)
    expect(dialog.textContent?.match(/Configured; leave blank to keep unchanged\./g)).toHaveLength(2)

    const test = Array.from(dialog.querySelectorAll('button')).find(item => item.textContent?.trim() === 'Test connection') as HTMLButtonElement
    await act(async () => { test.click(); await Promise.resolve(); await Promise.resolve() })
    expect(testChannel).toHaveBeenLastCalledWith('woocommerce:primary', expect.objectContaining({ secrets: {} }))
    expect(saveChannel).not.toHaveBeenCalled()

    const save = Array.from(dialog.querySelectorAll('button')).find(item => item.textContent?.trim() === 'Save configuration') as HTMLButtonElement
    await act(async () => { save.click(); await Promise.resolve(); await Promise.resolve(); await Promise.resolve() })
    expect(saveChannel).toHaveBeenCalledWith('woocommerce:primary', expect.objectContaining({ secrets: {} }))
  })

  it('tests a draft replacement without persisting it until Save', async () => {
    await render()
    const card = container.querySelector('[data-channel-card="woocommerce:primary"]') as HTMLElement
    const settings = Array.from(card.querySelectorAll('button')).find(item => item.textContent?.trim() === 'Settings') as HTMLButtonElement
    await act(async () => { settings.click(); await Promise.resolve(); await Promise.resolve(); await Promise.resolve() })

    const dialog = container.querySelector('[role="dialog"]') as HTMLElement
    const keyInput = dialog.querySelector<HTMLInputElement>('input[type="password"]') as HTMLInputElement
    await act(async () => setInputValue(keyInput, 'replacement-key'))
    const test = Array.from(dialog.querySelectorAll('button')).find(item => item.textContent?.trim() === 'Test connection') as HTMLButtonElement
    await act(async () => { test.click(); await Promise.resolve(); await Promise.resolve() })

    expect(testChannel).toHaveBeenLastCalledWith(
      'woocommerce:primary',
      expect.objectContaining({ secrets: { key: 'replacement-key' } }),
    )
    expect(saveChannel).not.toHaveBeenCalled()

    const save = Array.from(dialog.querySelectorAll('button')).find(item => item.textContent?.trim() === 'Save configuration') as HTMLButtonElement
    await act(async () => { save.click(); await Promise.resolve(); await Promise.resolve(); await Promise.resolve() })
    expect(saveChannel).toHaveBeenCalledWith(
      'woocommerce:primary',
      expect.objectContaining({ secrets: { key: 'replacement-key' } }),
    )
  })

  it('exposes the isolated development-only partial-failure browser fixture', async () => {
    await render(admin, '/channels?qa=partial')
    expect(container.textContent).toContain('Some Channel information is unavailable')
  })

  it('keeps admin actions hidden for a read-only user', async () => {
    await render(viewer)

    const actionLabels = Array.from(container.querySelectorAll('button')).map(button => button.textContent?.trim())
    expect(actionLabels).not.toContain('Add channel')
    expect(actionLabels).not.toContain('Setup now')
    expect(actionLabels).not.toContain('Test connection')
    expect(actionLabels).not.toContain('Refresh cache')
    expect(actionLabels).not.toContain('Settings')
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

describe('Channel detail connection evidence', () => {
  it('requires enabled healthy evidence before presenting a healthy connection', () => {
    expect(channelConnectionEvidence(channel({ enabled: true, health: { status: 'healthy', message: '', latency_ms: 1, error_code: null } }))).toBe('healthy')
    expect(channelConnectionEvidence(channel({ enabled: true, status: 'configured', health: { status: 'unknown', message: '', latency_ms: null, error_code: null } }))).toBe('configured')
    expect(channelConnectionEvidence(channel({ enabled: true, health: { status: 'unhealthy', message: '', latency_ms: null, error_code: 'network' } }))).toBe('warning')
    expect(channelConnectionEvidence(channel({ enabled: false, credential_status: 'configured', health: { status: 'healthy', message: '', latency_ms: 1, error_code: null } }))).toBe('setupRequired')
  })
})
