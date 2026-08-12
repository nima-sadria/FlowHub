// @vitest-environment jsdom
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router'
import { AuthContext, type AuthContextValue } from '../auth'
import { NotificationProvider } from '../notifications/NotificationProvider'
import { ServiceProvider, type Services } from '../services/ServiceContext'
import type { CommerceService } from '../services/commerce/CommerceService'
import type { CommerceChannel } from '../services/types'
import ChannelDetail from './ChannelDetail'

const admin: AuthContextValue = {
  user: { username: 'admin', role: 'admin', is_admin: true, is_super_admin: false, permissions: {} },
  status: 'authenticated',
  refreshUser: async () => {},
  clearAuth: () => {},
  logout: async () => {},
  authFetch: fetch,
}

const digikala: CommerceChannel = {
  id: 'digikala:main',
  provider: 'digikala',
  name: 'Digikala',
  type: 'Channel',
  status: 'coming_soon',
  implemented: true,
  implementation_status: 'IMPLEMENTED_UNVERIFIED',
  placeholder: true,
  enabled: false,
  read_only: true,
  write_blocked: true,
  runtime_write_blocked: true,
  credential_status: 'not_configured',
  last_health_check: null,
  health: { status: 'unknown', message: '', latency_ms: null, error_code: null },
  capabilities: {},
  capabilities_summary: [],
  settings_available: false,
  cached_products: 0,
  cached_variations: 0,
  last_cache_refresh: null,
  cache_refresh_status: 'not_run',
}

describe('Channel detail Coming Soon presentation', () => {
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

  it('preserves the provider identity but does not fetch configuration or offer operational actions', async () => {
    const getChannelConfiguration = vi.fn()
    const commerce = {
      getChannels: vi.fn().mockResolvedValue({ items: [digikala] }),
      getChannelConfiguration,
    } as unknown as CommerceService
    const services = {
      commerce,
      health: {},
      products: {},
      sources: {},
      workspace: {},
      settings: {},
      activity: {},
      writePipeline: {},
      orders: undefined,
    } as unknown as Services

    await act(async () => {
      root.render(
        <AuthContext.Provider value={admin}>
          <NotificationProvider>
            <MemoryRouter initialEntries={['/channels/digikala:main']}>
              <ServiceProvider services={services}>
                <Routes><Route path="/channels/:channelId" element={<ChannelDetail />} /></Routes>
              </ServiceProvider>
            </MemoryRouter>
          </NotificationProvider>
        </AuthContext.Provider>,
      )
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(container.querySelector('[data-testid="channel-coming-soon-detail"]')).not.toBeNull()
    expect(container.textContent).toContain('Digikala')
    expect(container.textContent).toContain('Coming Soon')
    expect(container.textContent).not.toContain('Test connection')
    expect(container.textContent).not.toContain('Settings')
    expect(getChannelConfiguration).not.toHaveBeenCalled()
  })
})
