// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { createRoot } from 'react-dom/client'
import { act } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { AuthContext, type AuthContextValue, type AuthUser } from '../auth'
import { DirectionProvider } from '../direction'
import { NotificationProvider } from '../notifications/NotificationProvider'
import { ServiceProvider, type Services } from '../services/ServiceContext'
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
      getRateLimits: async () => { throw new Error('not used') },
      updateRateLimits: async () => { throw new Error('not used') },
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
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ status: 'ok', version: '1.0.0' }), { status: 200 })))
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
        <MemoryRouter>
          <DirectionProvider>
            <AuthContext.Provider value={authValue()}>
              <ServiceProvider services={services()}>
                <Settings />
              </ServiceProvider>
            </AuthContext.Provider>
          </DirectionProvider>
        </MemoryRouter>
      </NotificationProvider>,
    )
  })
  await act(async () => { await Promise.resolve() })
  return container
}

describe('Settings', () => {
  it('renders the Figma General settings structure with existing service values', async () => {
    const c = await renderPage()

    expect(c.textContent).toContain('General')
    expect(c.textContent).toContain('Workspace preferences')
    expect(c.textContent).toContain('Localization preview')
    expect(c.textContent).toContain('English · EUR · UTC')
    expect(c.querySelector('a[href="/settings/users"]')).not.toBeNull()
    expect(c.querySelector('a[href="/rate-limits"]')).not.toBeNull()
  })
})
