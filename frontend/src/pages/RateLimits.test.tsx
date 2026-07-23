// @vitest-environment jsdom
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthContext, type AuthContextValue, type AuthUser } from '../auth'
import { NotificationProvider } from '../notifications/NotificationProvider'
import { ServiceProvider, type Services } from '../services/ServiceContext'
import type { RateLimitSettings } from '../services/types'
import RateLimits, { RateLimitsPanel } from './RateLimits'

let container: HTMLDivElement
let root: ReturnType<typeof createRoot>

const user: AuthUser = {
  username: 'admin',
  role: 'admin',
  is_admin: true,
  is_super_admin: false,
  permissions: { can_access_site: true, can_view_settings: true },
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
    logout: async () => undefined,
    authFetch: vi.fn(async () => new Response(JSON.stringify({
      rateLimiter: { requests_completed: 24, requests_delayed: 3, queue_length: 2 },
    }), { status: 200 })),
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
      updateRateLimits: async patch => ({
        ...rateLimits,
        ...patch,
        read_delay_ms: 60000 / patch.read_requests_per_minute,
        write_delay_ms: 60000 / patch.write_requests_per_minute,
      }),
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
})

afterEach(() => {
  act(() => { root.unmount() })
  container.remove()
})

async function renderPage() {
  await act(async () => {
    root.render(
      <MemoryRouter>
        <NotificationProvider>
          <AuthContext.Provider value={authValue()}>
            <ServiceProvider services={services()}>
              <RateLimits />
            </ServiceProvider>
          </AuthContext.Provider>
        </NotificationProvider>
      </MemoryRouter>,
    )
  })
  await act(async () => { await Promise.resolve() })
  return container
}

describe('RateLimits', () => {
  it('renders live limiter diagnostics and existing RPM settings', async () => {
    const page = await renderPage()
    expect(page.textContent).toContain(`Requests completed${(24).toLocaleString()}`)
    expect(page.textContent).toContain(`Requests delayed${(3).toLocaleString()}`)
    expect(page.textContent).toContain(`Queue length${(2).toLocaleString()}`)
    expect(page.textContent).toContain('Read requests per minute')
    expect(page.textContent).toContain('Write requests per minute')
    expect(page.textContent).toContain('Rolling window')
  })

  it('preserves delay labels in the embedded advanced settings panel', async () => {
    await act(async () => {
      root.render(
        <MemoryRouter>
          <NotificationProvider>
            <AuthContext.Provider value={authValue()}>
              <ServiceProvider services={services()}>
                <RateLimitsPanel embedded />
              </ServiceProvider>
            </AuthContext.Provider>
          </NotificationProvider>
        </MemoryRouter>,
      )
    })
    await act(async () => { await Promise.resolve() })

    expect(container.textContent).toContain('Read delay1.00 seconds')
    expect(container.textContent).toContain('Write delay2.00 seconds')
  })

  it('validates the existing RPM contract', async () => {
    const page = await renderPage()
    const input = page.querySelector('input') as HTMLInputElement
    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set
    await act(async () => {
      setter?.call(input, '0')
      input.dispatchEvent(new Event('input', { bubbles: true }))
    })
    expect(page.textContent).toContain('Read requests per minute must be between 1 and 1000.')
  })
})
