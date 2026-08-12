import path from 'node:path'
import { mkdirSync } from 'node:fs'
import { expect, test, type Page, type Route } from '@playwright/test'

// Visual + structural audit of the Figma Screen/Channels hierarchy: header
// with Add channel, a KPI stat row (Connected Channels / Healthy Listings /
// Needs Attention / Orders Today), a condensed search + health-state
// toolbar, and a flat grid of channel cards (icon, health badge, "Checked x
// ago", listings count, Configure link, Test/Refresh actions). Captures
// 1440x900 evidence for Light/Dark and LTR/RTL. All network traffic is
// mocked inside this spec; nothing leaves the isolated browser.

const screenshotRoot = path.resolve('..', 'docs', 'screenshots', 'v1.3', 'channels-screen')
mkdirSync(screenshotRoot, { recursive: true })

interface ChannelFixture {
  id: string
  name: string
  provider: string
  status: string
  healthStatus: string
  lastHealthCheck: string
  cachedProducts: number
}

const NOW = new Date()
function minutesAgo(minutes: number): string {
  return new Date(NOW.getTime() - minutes * 60_000).toISOString()
}

const CHANNELS: ChannelFixture[] = [
  { id: 'woocommerce:primary', name: 'WooCommerce', provider: 'woocommerce', status: 'active', healthStatus: 'healthy', lastHealthCheck: minutesAgo(2), cachedProducts: 2418 },
  { id: 'snappshop:main', name: 'SnappShop', provider: 'snappshop', status: 'active', healthStatus: 'degraded', lastHealthCheck: minutesAgo(8), cachedProducts: 1876 },
  { id: 'tapsishop:main', name: 'TapsiShop', provider: 'tapsishop', status: 'active', healthStatus: 'healthy', lastHealthCheck: minutesAgo(5), cachedProducts: 940 },
  { id: 'digikala:main', name: 'Digikala', provider: 'digikala', status: 'disabled', healthStatus: 'unknown', lastHealthCheck: minutesAgo(1440), cachedProducts: 512 },
]
const ORDERS_TODAY = 72

// Card titles are derived from the channel id via formatChannelDisplayName,
// which is locale-aware for these known providers (see channelDisplayName.ts)
// rather than from the raw fixture `name` above.
const CHANNEL_DISPLAY_NAMES: Record<'en' | 'fa', Record<string, string>> = {
  en: { woocommerce: 'WooCommerce', snappshop: 'SnappShop', tapsishop: 'TapsiShop', digikala: 'Digikala' },
  fa: { woocommerce: 'ووکامرس', snappshop: 'اسنپ شاپ', tapsishop: 'تپ‌سی شاپ', digikala: 'دیجی‌کالا' },
}

interface TrafficAudit {
  externalRequests: string[]
  unhandledApiRequests: string[]
}

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({ status, contentType: 'application/json; charset=utf-8', body: JSON.stringify(body) })
}

function channelShape(fixture: ChannelFixture) {
  return {
    id: fixture.id,
    provider: fixture.provider,
    name: fixture.name,
    type: 'Channel',
    status: fixture.status,
    implemented: true,
    placeholder: false,
    read_only: false,
    write_blocked: false,
    runtime_write_blocked: false,
    credential_status: 'configured',
    enabled: fixture.status === 'active',
    last_health_check: fixture.lastHealthCheck,
    health: { status: fixture.healthStatus, message: '', latency_ms: 120, error_code: null },
    capabilities: {},
    capabilities_summary: [],
    settings_available: true,
    cached_products: fixture.cachedProducts,
    cached_variations: 0,
    last_cache_refresh: fixture.lastHealthCheck,
    cache_refresh_status: 'completed',
  }
}

async function installChannelsMocks(page: Page, audit: TrafficAudit) {
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
        username: 'channels-owner',
        role: 'admin',
        is_admin: true,
        is_super_admin: false,
        permissions: { can_access_site: true, can_fetch: true, can_view_logs: true, can_view_settings: true },
        maintenance: { enabled: false, message: '' },
      })
    }
    if (url.pathname === '/api/v2/setup/status' && method === 'GET') return json(route, { completed: true })
    if (url.pathname === '/api/health' && method === 'GET') return json(route, { status: 'ok', env: 'test', version: 'channels-visual-mock' })
    if (url.pathname === '/api/v2/exchange-rates/me' && method === 'GET') return json(route, { selections: [], rates: [] })
    if (url.pathname === '/api/v2/commerce/channels' && method === 'GET') {
      return json(route, { items: CHANNELS.map(channelShape) })
    }
    if (url.pathname === '/api/v2/orders' && method === 'GET') {
      return json(route, { items: [], total: ORDERS_TODAY, page: 1, pageSize: 1 })
    }

    audit.unhandledApiRequests.push(`${method} ${url.pathname}${url.search}`)
    return json(route, { code: 'UNHANDLED_TEST_REQUEST' }, 500)
  })
}

async function seedSession(page: Page, locale: 'en' | 'fa', theme: 'light' | 'dark') {
  await page.addInitScript(([selectedLocale, selectedTheme]) => {
    localStorage.setItem('wp_token', 'channels-visual-isolated-token')
    localStorage.setItem('flowhub.locale', selectedLocale)
    localStorage.setItem('wp_theme', selectedTheme)
  }, [locale, theme])
}

async function assertFigmaChannelsHierarchy(page: Page, locale: 'en' | 'fa') {
  const heading = locale === 'en' ? 'Channels' : 'کانال‌ها'
  await expect(page.getByRole('heading', { name: heading, level: 1 })).toBeVisible()

  if (locale === 'en') {
    await expect(page.getByRole('button', { name: 'Add channel' })).toBeVisible()
    await expect(page.getByRole('button', { name: /Connected Channels/ })).toBeVisible()
    await expect(page.getByText('Healthy Listings')).toBeVisible()
    await expect(page.getByText('Needs Attention', { exact: true })).toBeVisible()
    await expect(page.getByText('Orders Today')).toBeVisible()
    await expect(page.getByText('72').first()).toBeVisible()
    await expect(page.getByPlaceholder('Search channels')).toBeVisible()
    await expect(page.locator('.fh-chip-select .sr-only', { hasText: 'All health states' })).toBeAttached()
    await expect(page.getByText('4 channels')).toBeVisible()

    const grid = page.locator('.fh-channels-grid')
    for (const fixture of CHANNELS) await expect(grid.getByText(CHANNEL_DISPLAY_NAMES.en[fixture.provider], { exact: true }).first()).toBeVisible()
    await expect(grid.locator('[data-channel-card]')).toHaveCount(4)
    await expect(grid.getByText('Healthy', { exact: true }).first()).toBeVisible()
    const disabledCard = grid.locator('[data-channel-card="digikala:main"]')
    await expect(disabledCard.getByText('Disabled', { exact: true })).toHaveCount(1)
    await expect(disabledCard.locator('.fh-badge')).toHaveCount(1)
  } else {
    await expect(page.getByRole('button', { name: 'افزودن کانال' })).toBeVisible()
    await expect(page.getByRole('button', { name: /کانال‌های متصل/ })).toBeVisible()
    await expect(page.getByPlaceholder('جست‌وجوی کانال‌ها')).toBeVisible()
    const grid = page.locator('.fh-channels-grid')
    for (const fixture of CHANNELS) await expect(grid.getByText(CHANNEL_DISPLAY_NAMES.fa[fixture.provider], { exact: true }).first()).toBeVisible()
  }
}

test('channels matches the approved Figma hierarchy in Light/Dark and LTR/RTL at 1440x900', async ({ page }) => {
  test.setTimeout(180_000)
  const audit: TrafficAudit = { externalRequests: [], unhandledApiRequests: [] }
  await installChannelsMocks(page, audit)
  await page.setViewportSize({ width: 1440, height: 900 })

  const variants = [
    { locale: 'en', theme: 'light', dir: 'ltr' },
    { locale: 'en', theme: 'dark', dir: 'ltr' },
    { locale: 'fa', theme: 'light', dir: 'rtl' },
    { locale: 'fa', theme: 'dark', dir: 'rtl' },
  ] as const

  for (const variant of variants) {
    await seedSession(page, variant.locale, variant.theme)
    await page.goto('/channels')
    await expect(page.locator('html')).toHaveAttribute('lang', variant.locale)
    await expect(page.locator('html')).toHaveAttribute('dir', variant.dir)
    if (variant.theme === 'dark') {
      await expect(page.locator('html')).toHaveClass(/dark/)
    }
    await expect(page.locator('.fh-channels-grid').first()).toBeVisible()
    await assertFigmaChannelsHierarchy(page, variant.locale)
    await page.evaluate(() => document.fonts.ready)
    // Let the shared 300ms shell/theme transition finish before capturing reference pixels.
    await page.waitForTimeout(500)
    await page.screenshot({
      path: path.join(screenshotRoot, `channels-${variant.theme}-${variant.dir}-1440x900.png`),
      animations: 'disabled',
    })
  }

  expect(audit.externalRequests, 'No request may leave the isolated local browser environment').toEqual([])
  expect(audit.unhandledApiRequests, 'Every Channels API request must be explicitly mocked').toEqual([])
})
