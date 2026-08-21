// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { createRoot } from 'react-dom/client'
import { act } from 'react'
import { AuthContext, type AuthContextValue, type AuthUser } from '../auth'
import { NotificationProvider } from '../notifications/NotificationProvider'
import { ServiceProvider, type Services } from '../services/ServiceContext'
import type { AppSettings } from '../services/types'
import { MemoryRouter } from 'react-router'
import Settings from './Settings'

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

function services(updateSettings: (patch: Partial<AppSettings>) => void = () => {}): Services {
  return {
    settings: {
      getSettings: async () => ({
        woocommerceUrl: '',
        nextcloudUrl: '',
        syncIntervalMinutes: 60,
        timezone: 'UTC',
        currency: 'EUR',
        currencyUnit: 'EUR',
        environment: 'production',
      }),
      updateSettings: async (patch: Partial<AppSettings>) => {
        updateSettings(patch)
        return {
          woocommerceUrl: '',
          nextcloudUrl: '',
          syncIntervalMinutes: patch.syncIntervalMinutes ?? 60,
          timezone: patch.timezone ?? 'UTC',
          currency: patch.currency ?? 'EUR',
          currencyUnit: patch.currencyUnit ?? 'EUR',
          environment: 'production',
        }
      },
      getRateLimits: vi.fn(),
      updateRateLimits: vi.fn(),
    },
    health: {} as Services['health'],
    products: {} as Services['products'],
    sources: {} as Services['sources'],
    activity: {} as Services['activity'],
    commerce: {} as Services['commerce'],
    writePipeline: {} as Services['writePipeline'],
    orders: {} as Services['orders'],
  } as unknown as Services
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

async function renderPage(updateSettings?: (patch: Partial<AppSettings>) => void) {
  await act(async () => {
    root.render(
      <NotificationProvider>
        <AuthContext.Provider value={authValue()}>
          <MemoryRouter>
            <ServiceProvider services={services(updateSettings)}>
              <Settings />
            </ServiceProvider>
          </MemoryRouter>
        </AuthContext.Provider>
      </NotificationProvider>,
    )
  })
  await act(async () => { await Promise.resolve() })
  return container
}

describe('Settings', () => {
  it('shows the General workspace preferences form with the shared Settings sub-navigation', async () => {
    const c = await renderPage()

    expect(c.textContent).toContain('General')
    const nav = c.querySelector('nav[aria-label="Settings"]')
    expect(nav?.textContent).toContain('Users')
    expect(nav?.textContent).toContain('Rate Limits')
    expect(nav?.textContent).toContain('Advanced')

    expect(c.textContent).toContain('Workspace preferences')
    expect(c.textContent).toContain('Regional defaults used across seller workflows.')
    expect(c.textContent).toContain('Localization preview')
    expect(c.textContent).toContain('English · EUR · UTC')
    expect(c.textContent).toContain('Ready')

    // The old embedded User Management table and Rate Limits panel are gone;
    // each now lives on its own dedicated page reachable from SettingsNav.
    expect(c.querySelector('table')).toBeNull()
    expect(c.textContent).not.toContain('User Management')
    expect(c.textContent).not.toContain('Create user')
    expect(c.textContent).not.toContain('Read Requests / Minute')
    expect(c.textContent).not.toContain('Sync interval')
    const calls = (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls.map(call => String(call[0]))
    expect(calls.some(url => url.includes('/api/v2/users'))).toBe(false)
  })

  it('tracks unsaved changes and saves the draft, including deferring the language switch until Save', async () => {
    const updateSettings = vi.fn()
    const c = await renderPage(updateSettings)

    expect(c.textContent).not.toContain('Unsaved changes')

    const timezoneSelect = Array.from(c.querySelectorAll('select')).find(select => select.querySelector('option[value="Asia/Tehran"]')) as HTMLSelectElement
    await act(async () => {
      timezoneSelect.value = 'Asia/Tehran'
      timezoneSelect.dispatchEvent(new Event('change', { bubbles: true }))
    })

    expect(c.textContent).toContain('Unsaved changes')
    expect(c.textContent).toContain('English · EUR · Asia/Tehran')

    const saveButton = Array.from(c.querySelectorAll('button')).find(button => button.textContent?.includes('Save Changes'))
    await act(async () => {
      saveButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await Promise.resolve()
    })

    expect(updateSettings).toHaveBeenCalledWith(expect.objectContaining({ timezone: 'Asia/Tehran' }))
    expect(c.textContent).not.toContain('Unsaved changes')
  })

  it('shows the full currency code and name in the dropdown, matching the approved design', async () => {
    const c = await renderPage()
    const currencySelect = Array.from(c.querySelectorAll('select')).find(select => select.querySelector('option[value="USD"]')) as HTMLSelectElement
    const usdOption = Array.from(currencySelect.options).find(option => option.value === 'USD')
    expect(usdOption?.textContent).toBe('USD — US Dollar')
  })

  it('requires an explicit Rial or Toman display unit for IRR', async () => {
    const c = await renderPage()
    const currencySelect = Array.from(c.querySelectorAll('select')).find(select => select.querySelector('option[value="IRR"]')) as HTMLSelectElement

    await act(async () => {
      currencySelect.value = 'IRR'
      currencySelect.dispatchEvent(new Event('change', { bubbles: true }))
    })

    const unitSelect = Array.from(c.querySelectorAll('select')).find(select => select.querySelector('option[value="TOMAN"]')) as HTMLSelectElement
    const saveButton = Array.from(c.querySelectorAll('button')).find(button => button.textContent?.includes('Save Changes')) as HTMLButtonElement
    expect(unitSelect.value).toBe('')
    expect(Array.from(unitSelect.options).map(option => option.value)).toEqual(['', 'RIAL', 'TOMAN'])
    expect(saveButton.disabled).toBe(true)
  })
})
