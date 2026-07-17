// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { createRoot } from 'react-dom/client'
import { act } from 'react'
import { AuthContext, type AuthContextValue, type AuthUser } from '../auth'
import { NotificationProvider } from '../notifications/NotificationProvider'
import { ServiceProvider, type Services } from '../services/ServiceContext'
import type { RateLimitSettings } from '../services/types'
import Settings from './Settings'

let container: HTMLDivElement
let root: ReturnType<typeof createRoot>

const user: AuthUser = {
  username: 'admin',
  role: 'admin',
  is_admin: true,
  is_super_admin: false,
  permissions: { can_access_site: true, can_fetch: true, can_view_settings: true },
}

const rateLimits: RateLimitSettings = {
  read_requests_per_minute: 60,
  write_requests_per_minute: 30,
  read_delay_ms: 1000,
  write_delay_ms: 2000,
  inherits_to_all_connectors: true,
  per_connector_override_available: false,
  scheduler_started: false,
  automatic_sync: false,
  runtime_write_blocked: true,
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
  return {
    settings: {
      getSettings: async () => ({
        woocommerceUrl: '',
        nextcloudUrl: '',
        syncIntervalMinutes: 60,
        timezone: 'UTC',
        currency: 'EUR',
        environment: 'production',
      }),
      updateSettings: async patch => ({
        woocommerceUrl: '',
        nextcloudUrl: '',
        syncIntervalMinutes: patch.syncIntervalMinutes ?? 60,
        timezone: patch.timezone ?? 'UTC',
        currency: patch.currency ?? 'EUR',
        environment: 'production',
      }),
      getRateLimits: async () => rateLimits,
      updateRateLimits: async patch => ({ ...rateLimits, ...patch }),
    },
    health: {} as Services['health'],
    products: {} as Services['products'],
    sources: {} as Services['sources'],
    workspace: {} as Services['workspace'],
    activity: {} as Services['activity'],
    commerce: {} as Services['commerce'],
    writePipeline: {} as Services['writePipeline'],
  }
}

beforeEach(() => {
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
  vi.stubGlobal('fetch', vi.fn(async input => {
    const url = String(input)
    if (url.includes('/api/v2/users')) {
      return new Response(JSON.stringify({
        items: [{
          id: 1,
          username: 'admin',
          role: 'admin',
          is_active: true,
          created_at: '2026-01-01T00:00:00',
          is_admin: true,
          is_super_admin: false,
        }],
        total: 1,
      }), { status: 200 })
    }
    return new Response(JSON.stringify({ status: 'ok', version: '1.0.0' }), { status: 200 })
  }))
})

afterEach(() => {
  act(() => { root.unmount() })
  container.remove()
  vi.unstubAllGlobals()
})

async function renderPage() {
  await act(async () => {
    root.render(
      <NotificationProvider>
        <AuthContext.Provider value={authValue()}>
          <ServiceProvider services={services()}>
            <Settings />
          </ServiceProvider>
        </AuthContext.Provider>
      </NotificationProvider>,
    )
  })
  await act(async () => { await Promise.resolve() })
  return container
}

describe('Settings', () => {
  it('shows Rate Limits as a Settings section', async () => {
    const c = await renderPage()

    expect(c.textContent).toContain('Settings')
    expect(c.textContent).toContain('User Management')
    expect(c.textContent).toContain('admin')
    expect(c.textContent).toContain('General')
    expect(c.textContent).toContain('Advanced')
    expect(c.textContent).toContain('Read Requests / Minute')
    expect(c.textContent).toContain('Write Requests / Minute')
  })
})
