// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { MemoryRouter, useLocation } from 'react-router'
import { DirectionProvider } from '../direction'
import { ThemeProvider } from '../theme/ThemeProvider'
import Topbar from './Topbar'
import { changeLocale } from '../i18n'
import type { ExchangeRateService } from '../services/exchangeRates/ExchangeRateService'

let container: HTMLDivElement
let root: ReturnType<typeof createRoot>

;(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true

beforeEach(() => {
  localStorage.clear()
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
})

afterEach(async () => {
  act(() => { root.unmount() })
  container.remove()
  await changeLocale('en')
})

function LocationProbe() {
  const location = useLocation()
  return <output data-location>{`${location.pathname}${location.search}`}</output>
}

function renderTopbar({ initialPath = '/home', sidebarCollapsed = false, exchangeRates, hasUnreadNotifications }: { initialPath?: string; sidebarCollapsed?: boolean; exchangeRates?: ExchangeRateService; hasUnreadNotifications?: boolean } = {}) {
  act(() => {
    root.render(
      <MemoryRouter initialEntries={[initialPath]}>
        <ThemeProvider>
          <DirectionProvider>
            <Topbar
              user={{ username: 'admin', role: 'admin' }}
              onMenuClick={() => undefined}
              onToggleCollapse={() => undefined}
              sidebarCollapsed={sidebarCollapsed}
              onLogout={() => undefined}
              exchangeRates={exchangeRates}
              hasUnreadNotifications={hasUnreadNotifications}
            />
            <LocationProbe />
          </DirectionProvider>
        </ThemeProvider>
      </MemoryRouter>,
    )
  })
}

describe('Topbar', () => {
  it('renders the functional global controls from the final design', () => {
    renderTopbar()

    expect(container.querySelector('input[aria-label="Search"]')).not.toBeNull()
    expect(container.querySelector('#global-search[name="global-search"]')).not.toBeNull()
    expect(container.querySelector('[aria-label="Notifications"]')).not.toBeNull()
    expect(container.querySelector('[aria-label="Switch to dark mode"]')).not.toBeNull()
    expect(container.querySelector('[aria-label="Language"]')).not.toBeNull()
    expect(container.querySelector('[aria-label="Language"]')?.className).toContain('fh-topbar-language')
    expect(container.querySelector('[aria-label="Collapse sidebar"]')).not.toBeNull()
    expect(container.querySelector('[aria-label="Collapse sidebar"]')?.className).toContain('fh-topbar-ghost')
    expect(container.querySelector('[aria-label="Notifications"]')?.className).toContain('fh-topbar-control')
    expect(container.querySelector('[aria-label="Notifications"]')?.getAttribute('data-unread')).toBeNull()
  })

  it('uses a two-level mobile header with an independently toggled action row', () => {
    renderTopbar()

    const primary = container.querySelector('.fh-topbar-primary')
    const brand = container.querySelector<HTMLButtonElement>('.fh-topbar-mobile-brand')
    const toggle = container.querySelector<HTMLButtonElement>('[aria-controls="topbar-mobile-actions"]')
    const actions = container.querySelector('#topbar-mobile-actions')
    const search = container.querySelector('form.fh-topbar-search')

    expect(primary).not.toBeNull()
    expect(brand?.getAttribute('dir')).toBe('ltr')
    expect(toggle?.getAttribute('aria-expanded')).toBe('false')
    expect(actions?.className).not.toContain('fh-topbar-actions-open')
    expect(search?.className).toContain('xl:block')

    act(() => { toggle!.click() })

    expect(toggle?.getAttribute('aria-expanded')).toBe('true')
    expect(actions?.className).toContain('fh-topbar-actions-open')
  })

  it('shows the signed-in user with role in the account chip', () => {
    renderTopbar()

    const account = container.querySelector('[aria-label="User menu"]')
    expect(account?.textContent).toContain('admin')
    expect(account?.className).toContain('fh-topbar-user')
    expect(account?.querySelector('.fh-topbar-user-chevron')).not.toBeNull()

    act(() => { (account as HTMLButtonElement).click() })

    expect(account?.getAttribute('aria-expanded')).toBe('true')
    expect(container.querySelector('.fh-topbar-account-menu')).not.toBeNull()
    expect(container.querySelector('.fh-topbar-account-profile')).not.toBeNull()
    expect(container.querySelector('.fh-topbar-account-menu .rounded-xl.border')).toBeNull()
  })

  it('derives the notification indicator from unread state', () => {
    renderTopbar({ hasUnreadNotifications: true })

    expect(container.querySelector('[aria-label="Notifications"]')?.getAttribute('data-unread')).toBe('true')
  })

  it('switches the sidebar toggle label with the collapsed state', () => {
    renderTopbar({ sidebarCollapsed: true })

    expect(container.querySelector('[aria-label="Expand sidebar"]')).not.toBeNull()
    expect(container.querySelector('[aria-label="Collapse sidebar"]')).toBeNull()
  })

  it('preserves product parameters when submitting a global search', () => {
    renderTopbar({ initialPath: '/products?workspace=catalog-workspace&status=active' })
    const input = container.querySelector<HTMLInputElement>('input[aria-label="Search"]')
    const form = input?.closest('form')
    expect(input).not.toBeNull()
    expect(form).not.toBeNull()

    act(() => {
      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set
      setter?.call(input, 'red shoe')
      input!.dispatchEvent(new Event('input', { bubbles: true }))
    })
    act(() => {
      form!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    })

    const location = container.querySelector('[data-location]')?.textContent ?? ''
    expect(location).toContain('/products?')
    expect(location).toContain('workspace=catalog-workspace')
    expect(location).toContain('status=active')
    expect(location).toContain('q=red+shoe')
  })

  it('switches language and direction from the language menu', () => {
    renderTopbar()

    const langButton = container.querySelector<HTMLButtonElement>('[aria-label="Language"]')
    expect(langButton).not.toBeNull()
    act(() => { langButton!.click() })

    const persian = container.querySelector<HTMLButtonElement>('.fh-dropdown-item.fh-persian-text')
    expect(persian).not.toBeNull()
    act(() => { persian!.click() })

    expect(document.documentElement.dir).toBe('rtl')
    expect(document.documentElement.lang).toBe('fa')
  })

  it('renders exactly three cached rates and a deliberate compact menu without numeric precision loss', async () => {
    const exchangeRates = {
      getLatest: vi.fn(async () => ({
        selections: ['usd_sell', 'eur', 'aed_sell'],
        rates: [
          { provider: 'navasan', external_symbol: 'usd_sell', canonical_code: 'USD_TEHRAN_SELL', display_name: 'USD Tehran Sell', display_name_fa: 'دلار', classification: 'market', side: 'sell', unit: 'IRR', position: 0, value: '123456789012345678.12500000', change: '1', provider_timestamp: null, fetched_at: null, status: 'fresh' as const, snapshot_id: '1' },
          { provider: 'navasan', external_symbol: 'eur', canonical_code: 'EUR_MARKET', display_name: 'EUR Market', display_name_fa: 'یورو', classification: 'market', side: null, unit: 'IRR', position: 1, value: '2', change: '-1', provider_timestamp: null, fetched_at: null, status: 'stale' as const, snapshot_id: '2' },
          { provider: 'navasan', external_symbol: 'aed_sell', canonical_code: 'AED_DUBAI_SELL', display_name: 'AED Dubai Sell', display_name_fa: 'درهم', classification: 'market', side: 'sell', unit: 'IRR', position: 2, value: null, change: null, provider_timestamp: null, fetched_at: null, status: 'unavailable' as const, snapshot_id: null },
        ],
      })),
    } as unknown as ExchangeRateService

    renderTopbar({ exchangeRates })
    await act(async () => { await Promise.resolve() })

    const desktop = container.querySelector('.fh-topbar-rates')
    expect(desktop?.querySelectorAll('.fh-topbar-rate')).toHaveLength(3)
    expect(desktop?.textContent).toContain('123,456,789,012,345,678.125')
    expect(container.querySelector('details.fh-topbar-rates-compact')).not.toBeNull()
    expect(container.querySelector('.fh-topbar-rates-compact summary [data-icon="rateLimits"]')).not.toBeNull()
    expect(container.querySelector('.fh-topbar-control-badge')?.textContent).toBe('3')
    expect(exchangeRates.getLatest).toHaveBeenCalledTimes(1)
  })

  it('keeps the exchange-rate control visible when provider data is unavailable', async () => {
    const exchangeRates = {
      getLatest: vi.fn(async () => ({ selections: [], rates: [] })),
    } as unknown as ExchangeRateService

    renderTopbar({ exchangeRates })
    await act(async () => { await Promise.resolve() })

    expect(container.querySelector('.fh-topbar-rates-compact summary [data-icon="rateLimits"]')).not.toBeNull()
    expect(container.querySelector('.fh-topbar-rates .fh-topbar-rate-unavailable')).not.toBeNull()
    expect(container.querySelector('.fh-topbar-rates-compact summary')?.getAttribute('data-state')).toBe('unavailable')
    expect(container.textContent).toContain('Unavailable')
    expect(container.querySelector('.fh-topbar-control-badge')).toBeNull()
  })

})
