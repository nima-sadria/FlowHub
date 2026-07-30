import path from 'node:path'
import { mkdirSync } from 'node:fs'
import { expect, test, type Page, type Route } from '@playwright/test'

// Visual + structural audit of the Figma Screen/Activity hierarchy: header
// with Export, a condensed toolbar (search + status/channel/user selects +
// Filters trigger), a "Today" event list with category-tinted icons, and a
// "Today" summary sidebar with real per-category counts. Captures 1440x900
// evidence for Light/Dark and LTR/RTL. All network traffic is mocked inside
// this spec; nothing leaves the isolated browser.

const screenshotRoot = path.resolve('..', 'docs', 'screenshots', 'v1.3', 'activity-screen')
mkdirSync(screenshotRoot, { recursive: true })

interface EventFixture {
  id: string
  kind: 'user_action' | 'system_log'
  level: string
  category: string
  actor: string
  action: string
  minutesAgo: number
}

const NOW = new Date()
function minutesAgoIso(minutes: number): string {
  return new Date(NOW.getTime() - minutes * 60_000).toISOString()
}

const EVENTS: EventFixture[] = [
  { id: 'evt-1', kind: 'system_log', level: 'info', category: 'products', actor: 'Classic T-Shirt', action: 'price_updated', minutesAgo: 2 },
  { id: 'evt-2', kind: 'system_log', level: 'success', category: 'orders', actor: '#10482', action: 'order_synchronized', minutesAgo: 5 },
  { id: 'evt-3', kind: 'system_log', level: 'info', category: 'sources', actor: 'Primary catalog', action: 'source_refreshed', minutesAgo: 12 },
  { id: 'evt-4', kind: 'user_action', level: 'warning', category: 'users', actor: 'Sara Ahmadi', action: 'user_permissions_changed', minutesAgo: 28 },
  { id: 'evt-5', kind: 'system_log', level: 'info', category: 'products', actor: 'Canvas Backpack', action: 'stock_updated', minutesAgo: 41 },
  { id: 'evt-6', kind: 'system_log', level: 'success', category: 'orders', actor: '#10478', action: 'retry_completed', minutesAgo: 60 },
  { id: 'evt-7', kind: 'system_log', level: 'info', category: 'sources', actor: 'Seasonal products', action: 'worksheet_enabled', minutesAgo: 120 },
  { id: 'evt-8', kind: 'system_log', level: 'info', category: 'products', actor: 'Running Shoes', action: 'status_updated', minutesAgo: 180 },
]
const TOTAL_EVENTS = 24
const TODAY_COUNTS: Record<string, number> = { products: 12, orders: 8, sources: 3, users: 1 }

interface TrafficAudit {
  externalRequests: string[]
  unhandledApiRequests: string[]
}

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({ status, contentType: 'application/json; charset=utf-8', body: JSON.stringify(body) })
}

function eventShape(fixture: EventFixture) {
  return {
    id: fixture.id,
    timestamp: minutesAgoIso(fixture.minutesAgo),
    kind: fixture.kind,
    level: fixture.level,
    category: fixture.category,
    actor: fixture.actor,
    action: fixture.action,
    detail: null,
  }
}

async function installActivityMocks(page: Page, audit: TrafficAudit) {
  await page.route('**/*', async route => {
    const request = route.request()
    const url = new URL(request.url())
    const method = request.method().toUpperCase()

    if (url.hostname !== '127.0.0.1' && url.hostname !== 'localhost') {
      audit.externalRequests.push(`${method} ${url.href}`)
      return route.abort('blockedbyclient')
    }
    if (!url.pathname.startsWith('/api/')) return route.continue()

    if (url.pathname === '/api/auth/me' && method === 'GET') {
      return json(route, {
        username: 'activity-owner',
        role: 'admin',
        is_admin: true,
        is_super_admin: false,
        permissions: { can_access_site: true, can_fetch: true, can_view_logs: true, can_view_settings: true },
        maintenance: { enabled: false, message: '' },
      })
    }
    if (url.pathname === '/api/v2/setup/status' && method === 'GET') return json(route, { completed: true })
    if (url.pathname === '/api/health' && method === 'GET') return json(route, { status: 'ok', env: 'test', version: 'activity-visual-mock' })
    if (url.pathname === '/api/v2/exchange-rates/me' && method === 'GET') return json(route, { selections: [], rates: [] })

    if (url.pathname === '/api/v2/activity' && method === 'GET') {
      const category = url.searchParams.get('category')
      const pageSize = Number(url.searchParams.get('pageSize') ?? '30')
      if (category && pageSize === 1) {
        return json(route, { items: [], total: TODAY_COUNTS[category] ?? 0, page: 1, pageSize: 1 })
      }
      return json(route, { items: EVENTS.map(eventShape), total: TOTAL_EVENTS, page: 1, pageSize: 30 })
    }
    if (url.pathname === '/api/v2/commerce/channels' && method === 'GET') {
      return json(route, {
        items: [
          { id: 'woocommerce:primary', provider: 'woocommerce', name: 'WooCommerce EU', type: 'Channel', status: 'active', implemented: true, placeholder: false, read_only: false, write_blocked: false, runtime_write_blocked: false, credential_status: 'configured', last_health_check: minutesAgoIso(2), health: { status: 'healthy', message: '', latency_ms: 80, error_code: null }, capabilities: {}, capabilities_summary: [], settings_available: true, cached_products: 2418, cached_variations: 0, last_cache_refresh: minutesAgoIso(2), cache_refresh_status: 'completed' },
        ],
      })
    }
    if (url.pathname === '/api/v2/users' && method === 'GET') {
      return json(route, { items: [{ id: 1, username: 'activity-owner', role: 'admin', is_active: true, created_at: minutesAgoIso(10_000), is_admin: true, is_super_admin: false }], total: 1 })
    }

    audit.unhandledApiRequests.push(`${method} ${url.pathname}${url.search}`)
    return json(route, { code: 'UNHANDLED_TEST_REQUEST' }, 500)
  })
}

async function seedSession(page: Page, locale: 'en' | 'fa', theme: 'light' | 'dark') {
  await page.addInitScript(([selectedLocale, selectedTheme]) => {
    localStorage.setItem('wp_token', 'activity-visual-isolated-token')
    localStorage.setItem('flowhub.locale', selectedLocale)
    localStorage.setItem('wp_theme', selectedTheme)
  }, [locale, theme])
}

async function assertFigmaActivityHierarchy(page: Page, locale: 'en' | 'fa') {
  const heading = locale === 'en' ? 'Activity' : 'فعالیت‌ها'
  await expect(page.getByRole('heading', { name: heading, level: 1 })).toBeVisible()

  if (locale === 'en') {
    await expect(page.getByRole('button', { name: 'Export' })).toBeVisible()
    await expect(page.getByPlaceholder('Search', { exact: true })).toBeVisible()
    await expect(page.locator('.fh-chip-select .sr-only', { hasText: 'All statuses' })).toBeAttached()
    await expect(page.locator('.fh-chip-select .sr-only', { hasText: 'All channels' })).toBeAttached()
    await expect(page.locator('.fh-chip-select .sr-only', { hasText: 'All users' })).toBeAttached()
    await expect(page.getByText('Filters', { exact: true })).toBeVisible()

    await expect(page.getByText('Price updated')).toBeVisible()
    await expect(page.getByText('Classic T-Shirt')).toBeVisible()
    await expect(page.getByText('Order synchronized')).toBeVisible()
    await expect(page.getByText('Sara Ahmadi')).toBeVisible()

    await expect(page.getByText('Product changes')).toBeVisible()
    await expect(page.getByText('Order syncs')).toBeVisible()
    await expect(page.getByText('Source refreshes')).toBeVisible()
    await expect(page.getByText('Permission changes')).toBeVisible()
    await expect(page.getByText('12', { exact: true })).toBeVisible()
    await expect(page.getByText('8', { exact: true }).first()).toBeVisible()
  } else {
    await expect(page.getByRole('button', { name: 'خروجی' })).toBeVisible()
    await expect(page.getByText('تغییرات محصول')).toBeVisible()
    await expect(page.getByText('همگام‌سازی سفارش‌ها')).toBeVisible()
  }
}

test('activity matches the approved Figma hierarchy in Light/Dark and LTR/RTL at 1440x900', async ({ page }) => {
  test.setTimeout(180_000)
  const audit: TrafficAudit = { externalRequests: [], unhandledApiRequests: [] }
  await installActivityMocks(page, audit)
  await page.setViewportSize({ width: 1440, height: 900 })

  const variants = [
    { locale: 'en', theme: 'light', dir: 'ltr' },
    { locale: 'en', theme: 'dark', dir: 'ltr' },
    { locale: 'fa', theme: 'light', dir: 'rtl' },
    { locale: 'fa', theme: 'dark', dir: 'rtl' },
  ] as const

  for (const variant of variants) {
    await seedSession(page, variant.locale, variant.theme)
    await page.goto('/activity')
    await expect(page.locator('html')).toHaveAttribute('lang', variant.locale)
    await expect(page.locator('html')).toHaveAttribute('dir', variant.dir)
    if (variant.theme === 'dark') {
      await expect(page.locator('html')).toHaveClass(/dark/)
    }
    await expect(page.locator('.fh-activity-toolbar')).toBeVisible()
    await assertFigmaActivityHierarchy(page, variant.locale)
    await page.evaluate(() => document.fonts.ready)
    await page.screenshot({
      path: path.join(screenshotRoot, `activity-${variant.theme}-${variant.dir}-1440x900.png`),
      animations: 'disabled',
    })
  }

  expect(audit.externalRequests, 'No request may leave the isolated local browser environment').toEqual([])
  expect(audit.unhandledApiRequests, 'Every Activity API request must be explicitly mocked').toEqual([])
})
