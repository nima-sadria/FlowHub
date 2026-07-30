import path from 'node:path'
import { mkdirSync, readFileSync } from 'node:fs'
import { expect, test, type Page, type Route } from '@playwright/test'

// Visual + structural audit of the Figma Screen/Dashboard (159:12911) hierarchy:
// header, four KPI cards, workflow summary strip, two chart cards, recent
// activity, and channel health. Captures 1440x900 evidence for Light/Dark and
// LTR/RTL. All network traffic is mocked inside this spec; nothing leaves the
// isolated browser.

const screenshotRoot = path.resolve('..', 'docs', 'screenshots', 'v1.3', 'business-dashboard-cards')
mkdirSync(screenshotRoot, { recursive: true })
const mockLogo = readFileSync(path.resolve('public', 'flowhub-logo.png'))
const interFont = readFileSync(path.resolve('public', 'static', 'fonts', 'Inter-VariableFont_opsz,wght.ttf'))

interface TrafficAudit {
  externalRequests: string[]
  unhandledApiRequests: string[]
  writeRequests: string[]
}

function iso(daysAgo: number, minutesAgo = 0): string {
  return new Date(Date.now() - daysAgo * 86_400_000 - minutesAgo * 60_000).toISOString()
}

function channelHealth(
  channelId: string,
  channelType: string,
  status: 'Operational' | 'Warning',
  summary: string,
  nextRecommendedAction: string,
) {
  return {
    channelId,
    channelType,
    enabled: true,
    accessMode: 'read_only',
    status,
    summary,
    lastChecked: iso(0, 2),
    latency: 18,
    lastSuccessfulOperation: iso(0, 5),
    lastErrorCategory: null,
    capabilityState: { read_products: true, write_prices: true },
    nextRecommendedAction,
    dimensions: {},
    lastProductRead: iso(0, 5),
    lastProductWrite: null,
    lastOrderSync: iso(0, 10),
    polling: { cursor: null, lastRunAt: null },
    webhooks: {
      supported: false,
      received: 0,
      queued: 0,
      processed: 0,
      deadLetter: 0,
      lastReceivedAt: null,
      lastProcessedAt: null,
    },
  }
}

function buildOrders() {
  const channels = [
    ['shopify:primary', 14],
    ['woocommerce:primary', 11],
    ['snappshop:main', 9],
    ['tapsishop:main', 7],
    ['basalam:main', 6],
    ['digikala:main', 5],
    ['torob:main', 4],
    ['emalls:main', 3],
  ] as const
  const items = []
  let internalId = 1
  for (const [channelId, count] of channels) {
    for (let n = 0; n < count; n += 1) {
      items.push({
        internalId: internalId++,
        channelId,
        connectorType: channelId.split(':')[0],
        providerOrderId: `provider-${channelId}-${n}`,
        orderNumber: String(10_000 + internalId),
        providerStatus: 'paid',
        normalizedStatus: 'completed',
        createdAtProvider: iso(n % 14, n * 7),
        updatedAtProvider: null,
        currency: 'USD',
        finalAmount: 40 + ((n * 23) % 140),
        itemCount: 1 + (n % 3),
        synchronizationState: 'synced',
        eventSource: 'poll',
        errorState: null,
        lastSeenAt: null,
        customerDisplay: null,
        paymentStatus: 'paid',
        fulfillmentStatus: 'fulfilled',
      })
    }
  }
  return { items, total: items.length, page: 1, pageSize: 50 }
}

const ORDERS = buildOrders()

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({ status, contentType: 'application/json; charset=utf-8', body: JSON.stringify(body) })
}

async function installStrictDashboardMocks(page: Page, audit: TrafficAudit) {
  await page.route('**/*', async route => {
    const request = route.request()
    const url = new URL(request.url())
    const method = request.method().toUpperCase()

    if (url.hostname !== '127.0.0.1' && url.hostname !== 'localhost') {
      audit.externalRequests.push(`${method} ${url.href}`)
      return route.abort('blockedbyclient')
    }

    if (url.pathname.startsWith('/static/logos/')) {
      return route.fulfill({ status: 200, contentType: 'image/png', body: mockLogo })
    }
    if (url.pathname === '/static/fonts/Inter-VariableFont_opsz,wght.ttf') {
      return route.fulfill({ status: 200, contentType: 'font/ttf', body: interFont })
    }
    if (!url.pathname.startsWith('/api/')) return route.continue()
    if (method !== 'GET') audit.writeRequests.push(`${method} ${url.pathname}`)

    if (url.pathname === '/api/auth/me' && method === 'GET') {
      return json(route, {
        username: 'visual-owner',
        role: 'admin',
        is_admin: true,
        is_super_admin: false,
        permissions: { can_access_site: true, can_fetch: true, can_view_logs: true, can_view_settings: true },
        maintenance: { enabled: false, message: '' },
      })
    }
    if (url.pathname === '/api/v2/setup/status' && method === 'GET') {
      return json(route, { completed: true })
    }
    if (url.pathname === '/api/v2/dashboard/business-summary' && method === 'GET') {
      return json(route, {
        generatedAt: iso(0, 1),
        metrics: {
          productsWithChanges: 24,
          readyForReview: 18,
          readyForApply: 6,
          blockingIssues: 1,
          warnings: 3,
          affectedProducts: 2,
          outOfStockProducts: 16,
          pendingUpdates: 6,
          failedUpdates: 0,
          ordersToday: 72,
          ordersYesterday: 64,
          updatesAppliedToday: 30,
          updatesAppliedYesterday: 26,
          revenueToday: [{ currency: 'USD', amount: 12_480 }],
        },
      })
    }
    if (url.pathname === '/api/health' && method === 'GET') {
      return json(route, { status: 'ok', env: 'test', version: 'dashboard-visual-mock' })
    }
    if (url.pathname === '/api/v2/exchange-rates/me' && method === 'GET') {
      return json(route, { selections: [], rates: [] })
    }
    if (url.pathname === '/api/v2/diagnostics/channels/health' && method === 'GET') {
      return json(route, {
        checkedAt: iso(0, 2),
        summary: { overall: 'Operational', counts: { Operational: 1, Warning: 0, Error: 0, 'Unable to check': 0, Disabled: 0 } },
        items: [
          channelHealth('shopify:primary', 'shopify', 'Operational', 'Shopify is operational.', 'No immediate action required.'),
        ],
        external_call_performed: false,
      })
    }
    if (url.pathname === '/api/v2/sources' && method === 'GET') {
      return json(route, {
        items: [
          { id: 'source-primary-catalog', name: 'Primary catalog', type: 'nextcloud_excel', displayUrl: '', status: 'error', lastSynced: iso(0, 4), productCount: 1_300 },
        ],
      })
    }
    if (url.pathname === '/api/v2/products' && method === 'GET') {
      return json(route, { items: [], total: 1_300, page: 1, pageSize: 1, configured: true })
    }
    if (url.pathname === '/api/v2/orders' && method === 'GET') {
      return json(route, ORDERS)
    }
    if (url.pathname === '/api/v2/activity' && method === 'GET') {
      return json(route, {
        items: [
          { id: 'activity-1', timestamp: iso(0, 2), kind: 'user_action', level: 'success', actor: 'visual-owner', action: 'price_updated', detail: 'Classic T-Shirt' },
          { id: 'activity-2', timestamp: iso(0, 5), kind: 'system_log', level: 'success', actor: 'system', action: 'order_synchronized', detail: '#10482' },
        ],
        total: 2,
        page: 1,
        pageSize: 2,
      })
    }

    audit.unhandledApiRequests.push(`${method} ${url.pathname}${url.search}`)
    return json(route, { code: 'UNHANDLED_TEST_REQUEST' }, 500)
  })
}

async function seedSession(page: Page, locale: 'en' | 'fa', theme: 'light' | 'dark') {
  await page.addInitScript(([selectedLocale, selectedTheme]) => {
    localStorage.setItem('wp_token', 'dashboard-visual-isolated-token')
    localStorage.setItem('flowhub.locale', selectedLocale)
    localStorage.setItem('wp_theme', selectedTheme)
  }, [locale, theme])
}

async function assertFigmaDashboardHierarchy(page: Page, locale: 'en' | 'fa') {
  const heading = locale === 'en' ? 'Dashboard' : 'داشبورد'
  await expect(page.getByRole('heading', { name: heading, level: 1 })).toBeVisible()

  if (locale === 'en') {
    // Shared shell: approved search wording, health footer, language badge,
    // and localized role label.
    await expect(page.getByPlaceholder('Search products, orders, sources...')).toBeVisible()
    await expect(page.getByText('All systems operational')).toBeVisible()
    await expect(page.getByText('EN', { exact: true })).toBeVisible()
    await expect(page.getByText('Admin', { exact: true })).toBeVisible()

    // Header: date subtitle and the primary review action.
    await expect(page.getByText('Live commerce overview')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Review 18 changes' })).toBeVisible()

    // Four KPI cards with the approved labels and live-bound values.
    for (const label of ['Products Ready', 'Review Required', 'Apply Ready', 'Orders Today']) {
      await expect(page.getByText(label, { exact: true })).toBeVisible()
    }
    await expect(page.getByText('1,284', { exact: true })).toBeVisible()
    await expect(page.getByText('18', { exact: true })).toBeVisible()
    await expect(page.getByText('72', { exact: true })).toBeVisible()

    // Workflow summary strip: revenue, blocking, warnings, freshness, stages.
    await expect(page.getByText('Revenue today')).toBeVisible()
    await expect(page.getByText('$12,480')).toBeVisible()
    await expect(page.getByText('Blocking', { exact: true })).toBeVisible()
    await expect(page.getByText('Warnings', { exact: true })).toBeVisible()
    await expect(page.getByText('Source freshness')).toBeVisible()
    await expect(page.getByText('Pricing workflow')).toBeVisible()
    await expect(page.getByText('18 review')).toBeVisible()
    await expect(page.getByText('6 dry run')).toBeVisible()
    await expect(page.getByText('6 apply')).toBeVisible()

    // Two chart cards.
    await expect(page.getByText('Revenue trend')).toBeVisible()
    await expect(page.getByText('Orders by channel')).toBeVisible()
    await expect(page.getByText('Last 30 days')).toHaveCount(2)
    await expect(page.locator('[data-revenue-currency="USD"]')).toBeVisible()

    // Recent activity with compact times.
    await expect(page.getByText('Recent activity')).toBeVisible()
    await expect(page.getByText('View all')).toBeVisible()
    await expect(page.getByText('Price updated')).toBeVisible()
    await expect(page.getByText('Order synchronized')).toBeVisible()
    await expect(page.getByText('2 min', { exact: true })).toBeVisible()
    await expect(page.getByText('5 min', { exact: true })).toBeVisible()

    // Channel health: healthy channel first, then the warning source.
    await expect(page.getByText('Channel health')).toBeVisible()
    const healthRows = page.locator('[data-health-row]')
    await expect(healthRows).toHaveCount(2)
    await expect(healthRows.nth(0)).toContainText('Shopify')
    await expect(healthRows.nth(0)).toContainText('Healthy')
    await expect(healthRows.nth(1)).toContainText('Primary catalog')
    await expect(healthRows.nth(1)).toContainText('Warning')
    await expect(page.getByText('1 warning')).toBeVisible()

    // The removed Business Overview section must stay removed.
    await expect(page.locator('[data-business-card]')).toHaveCount(0)
    await expect(page.getByText('Business overview')).toHaveCount(0)
  } else {
    await expect(page.getByPlaceholder('جست‌وجوی محصول، سفارش یا منبع...')).toBeVisible()
    await expect(page.getByText('همه سامانه‌ها فعال‌اند')).toBeVisible()
    await expect(page.getByText('فا', { exact: true })).toBeVisible()
    await expect(page.getByText('مدیر', { exact: true })).toBeVisible()
    await expect(page.getByText('قیمت به‌روزرسانی شد')).toBeVisible()
    await expect(page.getByText('سفارش همگام شد')).toBeVisible()
    await expect(page.getByText('نمای زنده فروش')).toBeVisible()
    await expect(page.getByRole('button', { name: 'بررسی ۱۸ تغییر' })).toBeVisible()
    for (const label of ['محصولات آماده', 'نیازمند بازبینی', 'آماده اعمال', 'سفارش‌های امروز']) {
      await expect(page.getByText(label, { exact: true })).toBeVisible()
    }
    await expect(page.getByText('فرایند قیمت‌گذاری')).toBeVisible()
    await expect(page.getByText('روند درآمد')).toBeVisible()
    await expect(page.getByText('سفارش‌ها به تفکیک کانال')).toBeVisible()
    await expect(page.getByText('فعالیت‌های اخیر')).toBeVisible()
    await expect(page.getByText('وضعیت کانال‌ها')).toBeVisible()
    await expect(page.locator('[data-health-row]')).toHaveCount(2)
  }
}

async function assertNoPageScrollbarAt1440x900(page: Page) {
  const layout = await page.evaluate(() => ({
    viewportWidth: window.innerWidth,
    viewportHeight: window.innerHeight,
    scrollWidth: document.documentElement.scrollWidth,
    scrollHeight: document.documentElement.scrollHeight,
  }))
  expect(layout.viewportWidth).toBe(1440)
  expect(layout.viewportHeight).toBe(900)
  expect(layout.scrollWidth, 'no horizontal page scrollbar at 1440x900').toBeLessThanOrEqual(1440)
  expect(layout.scrollHeight, 'no vertical page scrollbar at 1440x900').toBeLessThanOrEqual(900)
}

test('dashboard matches the approved Figma hierarchy in Light/Dark and LTR/RTL at 1440x900', async ({ page }) => {
  test.setTimeout(180_000)
  const audit: TrafficAudit = { externalRequests: [], unhandledApiRequests: [], writeRequests: [] }
  await installStrictDashboardMocks(page, audit)
  await page.setViewportSize({ width: 1440, height: 900 })

  const variants = [
    { locale: 'en', theme: 'light', dir: 'ltr' },
    { locale: 'en', theme: 'dark', dir: 'ltr' },
    { locale: 'fa', theme: 'light', dir: 'rtl' },
    { locale: 'fa', theme: 'dark', dir: 'rtl' },
  ] as const

  for (const variant of variants) {
    await seedSession(page, variant.locale, variant.theme)
    await page.goto('/home')
    await expect(page.locator('html')).toHaveAttribute('lang', variant.locale)
    await expect(page.locator('html')).toHaveAttribute('dir', variant.dir)
    if (variant.theme === 'dark') {
      await expect(page.locator('html')).toHaveClass(/dark/)
    }
    await assertFigmaDashboardHierarchy(page, variant.locale)
    await assertNoPageScrollbarAt1440x900(page)
    await page.evaluate(() => document.fonts.ready)
    await page.screenshot({
      path: path.join(screenshotRoot, `dashboard-${variant.theme}-${variant.dir}-1440x900.png`),
      animations: 'disabled',
    })
  }

  expect(audit.externalRequests, 'No request may leave the isolated local browser environment').toEqual([])
  expect(audit.unhandledApiRequests, 'Every Dashboard API request must be explicitly mocked').toEqual([])
  expect(audit.writeRequests, 'The visual audit must not execute any write request').toEqual([])
})
