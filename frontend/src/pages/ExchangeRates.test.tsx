// @vitest-environment jsdom
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthContext, type AuthContextValue, type AuthUser } from '../auth'
import { NotificationProvider } from '../notifications/NotificationProvider'
import { ServiceProvider, type Services } from '../services/ServiceContext'
import type { ExchangeRateDiagnostics } from '../services/types'
import ExchangeRates from './ExchangeRates'

let container: HTMLDivElement
let root: ReturnType<typeof createRoot>

const definitions = [
  { provider: 'navasan', external_symbol: 'usd_sell', canonical_code: 'USD_TEHRAN_SELL', display_name: 'USD Tehran Sell', display_name_fa: 'فروش دلار تهران', classification: 'market', side: 'sell', unit: 'IRR' },
  { provider: 'navasan', external_symbol: 'usd_buy', canonical_code: 'USD_TEHRAN_BUY', display_name: 'USD Tehran Buy', display_name_fa: 'خرید دلار تهران', classification: 'market', side: 'buy', unit: 'IRR' },
  { provider: 'navasan', external_symbol: 'eur', canonical_code: 'EUR_MARKET', display_name: 'EUR Market', display_name_fa: 'یورو بازار', classification: 'market', side: null, unit: 'IRR' },
  { provider: 'navasan', external_symbol: 'aed_sell', canonical_code: 'AED_DUBAI_SELL', display_name: 'AED Dubai Sell', display_name_fa: 'فروش درهم دبی', classification: 'market', side: 'sell', unit: 'IRR' },
]

const rates = definitions.slice(0, 3).map((item, position) => ({
  ...item,
  position,
  value: position === 0 ? '123.45' : null,
  change: null,
  provider_timestamp: null,
  fetched_at: null,
  status: position === 0 ? 'fresh' as const : 'unavailable' as const,
  snapshot_id: position === 0 ? 'snapshot-1' : null,
}))

const diagnostics: ExchangeRateDiagnostics = {
  provider_id: 'navasan',
  provider_type: 'navasan',
  display_name: 'Navasan',
  enabled: true,
  base_url: 'https://api.navasan.tech',
  request_timeout: 10,
  refreshes_per_day: 24,
  daily_request_limit: 120,
  reserved_request_count: 10,
  schedule_timezone: 'Asia/Tehran',
  api_key_configured: true,
  api_key_masked: '********',
  status: 'healthy',
  estimated_scheduled_usage: 25,
  safe_scheduled_limit: 109,
  internal_daily_usage: 5,
  internal_completed_usage: 4,
  provider_usage: { daily_usage: 7, hourly_usage: 1, monthly_usage: 20, last_use: null },
  effective_usage: 7,
  remaining_safe_requests: 1,
  usage_discrepancy: 2,
  usage_reconciliation_status: 'reconciled',
  usage_reconciled_at: '2026-01-01T10:00:00',
  usage_error_code: null,
  last_success_at: '2026-01-01T10:00:00',
  last_failure_at: null,
  last_error: null,
  next_scheduled_refresh: '2026-01-01T11:00:00',
  next_eligible_refresh: '2026-01-01T11:00:00',
  runner_state: 'idle',
  runner_heartbeat_at: '2026-01-01T10:01:00',
}

function authValue(user: AuthUser): AuthContextValue {
  return {
    user,
    status: 'authenticated',
    refreshUser: async () => undefined,
    clearAuth: () => undefined,
    logout: async () => undefined,
    authFetch: vi.fn(),
  }
}

function serviceBundle() {
  const exchangeRates = {
    getSupported: vi.fn(async () => definitions),
    getLatest: vi.fn(async () => ({ selections: ['usd_sell', 'eur', 'aed_sell'], rates })),
    updateSelections: vi.fn(async (selections: string[]) => ({ selections, rates })),
    getAdminConfig: vi.fn(async () => diagnostics),
    updateAdminConfig: vi.fn(async () => diagnostics),
    testConnection: vi.fn(async () => ({ ok: true, status: 'healthy' })),
    synchronizeUsage: vi.fn(async () => ({ status: 'reconciled' })),
    getDiagnostics: vi.fn(async () => diagnostics),
    refresh: vi.fn(async () => ({ status: 'success', records: 3 })),
  }
  const services = {
    exchangeRates,
    settings: {} as Services['settings'],
    health: {} as Services['health'],
    products: {} as Services['products'],
    sources: {} as Services['sources'],
    workspace: {} as Services['workspace'],
    activity: {} as Services['activity'],
    commerce: {} as Services['commerce'],
    writePipeline: {} as Services['writePipeline'],
  } satisfies Services
  return { services, exchangeRates }
}

beforeEach(() => {
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
})

afterEach(() => {
  act(() => { root.unmount() })
  container.remove()
  vi.restoreAllMocks()
})

async function renderPage(user: AuthUser) {
  const bundle = serviceBundle()
  await act(async () => {
    root.render(
      <MemoryRouter>
        <NotificationProvider>
          <AuthContext.Provider value={authValue(user)}>
            <ServiceProvider services={bundle.services}>
              <ExchangeRates />
            </ServiceProvider>
          </AuthContext.Provider>
        </NotificationProvider>
      </MemoryRouter>,
    )
  })
  await act(async () => { await Promise.resolve() })
  return bundle
}

describe('ExchangeRates', () => {
  it('shows three ordered choices to a normal user without administrative controls', async () => {
    const bundle = await renderPage({
      username: 'viewer',
      role: 'viewer',
      is_admin: false,
      is_super_admin: false,
      permissions: { can_access_site: true, can_view_settings: true },
    })
    expect(container.querySelectorAll('select')).toHaveLength(3)
    expect(container.textContent).toContain('Your header rates')
    expect(container.textContent).not.toContain('Super Admin provider controls')
    expect(bundle.exchangeRates.getAdminConfig).not.toHaveBeenCalled()
    const duplicate = container.querySelectorAll('select')[1]?.querySelector('option[value="usd_sell"]')
    expect(duplicate?.hasAttribute('disabled')).toBe(true)
  })

  it('shows masked, budget-aware controls only to the owner', async () => {
    await renderPage({
      username: 'owner',
      role: 'owner',
      is_admin: true,
      is_super_admin: true,
      permissions: { can_access_site: true, can_view_settings: true },
    })
    expect(container.textContent).toContain('Super Admin provider controls')
    expect(container.querySelector<HTMLInputElement>('input[type="password"]')?.placeholder).toBe('********')
    expect(container.textContent).toContain('Provider and FlowHub usage differ by 2 requests')
    expect(container.textContent).toContain('Test connection')
    expect(container.textContent).toContain('Synchronize usage')
    expect(container.textContent).toContain('Next scheduled refresh')
  })

  it('asks for confirmation near the safe limit before manual refresh', async () => {
    const bundle = await renderPage({
      username: 'owner',
      role: 'owner',
      is_admin: true,
      is_super_admin: true,
      permissions: { can_access_site: true, can_view_settings: true },
    })
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    const button = Array.from(container.querySelectorAll('button')).find(item => item.textContent?.includes('Refresh now'))
    await act(async () => { button?.click() })
    expect(window.confirm).toHaveBeenCalledTimes(1)
    expect(bundle.exchangeRates.refresh).not.toHaveBeenCalled()
  })
})
