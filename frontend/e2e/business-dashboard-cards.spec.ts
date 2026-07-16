import path from 'node:path'
import { mkdirSync, readFileSync } from 'node:fs'
import { expect, test, type Page, type Route } from '@playwright/test'

const screenshotRoot = path.resolve('..', 'docs', 'screenshots', 'v1.3', 'business-dashboard-cards')
mkdirSync(screenshotRoot, { recursive: true })
const mockLogo = readFileSync(path.resolve('public', 'flowhub-logo.png'))

interface TrafficAudit {
  externalRequests: string[]
  unhandledApiRequests: string[]
  writeRequests: string[]
}

const channelItems = [
  channelHealth('woocommerce:primary', 'woocommerce', 'Operational', 'WooCommerce is operational.', 'No immediate action required.'),
  channelHealth('snappshop:main', 'snappshop', 'Warning', 'Accepted webhook receipts are waiting for processing.', 'Review queued webhook receipts.'),
]

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
    lastChecked: '2026-07-16T06:00:00Z',
    latency: 18,
    lastSuccessfulOperation: '2026-07-16T05:55:00Z',
    lastErrorCategory: null,
    capabilityState: { read_products: true, write_prices: true },
    nextRecommendedAction,
    dimensions: {},
    lastProductRead: '2026-07-16T05:55:00Z',
    lastProductWrite: null,
    lastOrderSync: '2026-07-16T05:50:00Z',
    polling: { cursor: null, lastRunAt: null },
    webhooks: {
      supported: channelType === 'snappshop',
      received: channelType === 'snappshop' ? 4 : 0,
      queued: channelType === 'snappshop' ? 1 : 0,
      processed: channelType === 'snappshop' ? 3 : 0,
      deadLetter: 0,
      lastReceivedAt: channelType === 'snappshop' ? '2026-07-16T05:40:00Z' : null,
      lastProcessedAt: channelType === 'snappshop' ? '2026-07-16T05:35:00Z' : null,
    },
  }
}

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({ status, contentType: 'application/json; charset=utf-8', body: JSON.stringify(body) })
}

async function installStrictDashboardMocks(page: Page, audit: TrafficAudit) {
  await page.addInitScript(() => {
    localStorage.setItem('wp_token', 'dashboard-visual-isolated-token')
    if (!localStorage.getItem('flowhub.locale')) localStorage.setItem('flowhub.locale', 'en')
  })

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
    if (url.pathname === '/api/health' && method === 'GET') {
      return json(route, { status: 'ok', env: 'test', version: 'dashboard-visual-mock' })
    }
    if (url.pathname === '/api/v2/diagnostics/channels/health' && method === 'GET') {
      return json(route, {
        checkedAt: '2026-07-16T06:00:00Z',
        summary: { overall: 'Warning', counts: { Operational: 1, Warning: 1, Error: 0, 'Unable to check': 0, Disabled: 0 } },
        items: channelItems,
        external_call_performed: false,
      })
    }
    if (url.pathname === '/api/v2/sources' && method === 'GET') {
      return json(route, {
        items: [
          { id: 'source-daily-prices', name: 'Daily pricing sheet', type: 'nextcloud_excel', displayUrl: '', status: 'active', lastSynced: '2026-07-16T05:45:00Z', productCount: 2415 },
          { id: 'source-supplier', name: 'Supplier price list', type: 'nextcloud_excel', displayUrl: '', status: 'error', lastSynced: null, productCount: 0 },
        ],
      })
    }
    if (url.pathname === '/api/v2/products' && method === 'GET') {
      return json(route, { items: [], total: 2415, page: 1, pageSize: 1, configured: true })
    }
    if (url.pathname === '/api/v2/activity' && method === 'GET') {
      return json(route, {
        items: [
          { id: 'activity-1', timestamp: '2026-07-16T05:50:00Z', kind: 'user_action', level: 'success', actor: 'visual-owner', action: 'source_read_completed', detail: null },
          { id: 'activity-2', timestamp: '2026-07-16T05:40:00Z', kind: 'system_log', level: 'warning', actor: 'system', action: 'channel_health_warning', detail: null },
        ],
        total: 2,
        page: 1,
        pageSize: 5,
      })
    }

    audit.unhandledApiRequests.push(`${method} ${url.pathname}${url.search}`)
    return json(route, { code: 'UNHANDLED_TEST_REQUEST' }, 500)
  })
}

async function assertDecisionReadyDashboard(page: Page, locale: 'en' | 'fa') {
  await expect(page.locator('[data-business-card]')).toHaveCount(5)
  await expect(page.locator('[data-business-card] .fh-business-card-value')).toHaveCount(5)
  await expect(page.locator('[data-business-card] .fh-business-card-explanation')).toHaveCount(5)
  await expect(page.locator('[data-business-card] .fh-business-card-meaning')).toHaveCount(5)
  await expect(page.locator('[data-business-card] .fh-badge')).toHaveCount(5)
  await expect(page.locator('[data-business-card] .fh-business-card-recommendation')).toHaveCount(5)
  await expect(page.locator('[data-business-card] .fh-badge [data-icon]')).toHaveCount(5)

  if (locale === 'en') {
    await expect(page.getByRole('heading', { name: 'Business overview' })).toBeVisible()
    await expect(page.getByText('2,415 products are available for daily work.')).toBeVisible()
    await expect(page.getByText('1 of 2 ready')).toBeVisible()
    await expect(page.getByText('Review queued webhook receipts.')).toBeVisible()
    await expect(page.getByText('Ready for daily work')).toBeVisible()
    await expect(page.getByText('Backend', { exact: true })).toHaveCount(0)
    await expect(page.getByText('Database', { exact: true })).toHaveCount(0)
    await expect(page.getByText('Application', { exact: true })).toHaveCount(0)

    const toneStyles = await page.evaluate(() => {
      const productCard = document.querySelector<HTMLElement>('[data-business-card="products"]')
      const sourceCard = document.querySelector<HTMLElement>('[data-business-card="sources"]')
      if (!productCard || !sourceCard) return null
      return {
        productTone: productCard.dataset.tone,
        sourceTone: sourceCard.dataset.tone,
        productAccent: getComputedStyle(productCard).borderInlineStartColor,
        sourceAccent: getComputedStyle(sourceCard).borderInlineStartColor,
      }
    })
    expect(toneStyles).toMatchObject({ productTone: 'success', sourceTone: 'warning' })
    expect(toneStyles?.productAccent).not.toBe(toneStyles?.sourceAccent)
  } else {
    await expect(page.getByRole('heading', { name: 'نمای کسب‌وکار' })).toBeVisible()
    await expect(page.getByText('۲٬۴۱۵ محصول برای کار روزانه در دسترس است.')).toBeVisible()
    await expect(page.getByText('۱ از ۲ آماده')).toBeVisible()
    await expect(page.getByText('وب‌هوک‌های دریافت‌شده در صف را بررسی کنید.')).toBeVisible()
    await expect(page.getByText('آماده کار روزانه')).toBeVisible()
  }

  const layout = await page.evaluate(() => ({
    viewport: window.innerWidth,
    documentWidth: document.documentElement.scrollWidth,
    cards: Array.from(document.querySelectorAll<HTMLElement>('[data-business-card]')).map(card => ({
      id: card.dataset.businessCard,
      title: card.querySelector('.fh-business-card-title')?.textContent,
      value: card.querySelector('.fh-business-card-value')?.textContent,
      status: card.querySelector('.fh-badge')?.textContent,
      recommendation: card.querySelector('.fh-business-card-recommendation-text')?.textContent,
    })),
  }))
  expect(layout.documentWidth).toBeLessThanOrEqual(layout.viewport + 1)
  expect(layout.cards.every(card => card.title && card.value && card.status && card.recommendation)).toBe(true)
}

test('business dashboard is decision-ready in real Chrome for English LTR and Persian RTL', async ({ page }) => {
  test.setTimeout(90_000)
  const audit: TrafficAudit = { externalRequests: [], unhandledApiRequests: [], writeRequests: [] }
  await installStrictDashboardMocks(page, audit)

  const viewports = [
    { width: 1366, height: 768 },
    { width: 1440, height: 900 },
    { width: 1920, height: 1080 },
  ]

  for (const locale of ['en', 'fa'] as const) {
    if (locale === 'fa') {
      await page.evaluate(selectedLocale => localStorage.setItem('flowhub.locale', selectedLocale), locale)
    }
    for (const viewport of viewports) {
      await page.setViewportSize(viewport)
      await page.goto('/home')
      await expect(page.locator('html')).toHaveAttribute('lang', locale)
      await expect(page.locator('html')).toHaveAttribute('dir', locale === 'fa' ? 'rtl' : 'ltr')
      await assertDecisionReadyDashboard(page, locale)
      await page.screenshot({
        path: path.join(screenshotRoot, `dashboard-${locale}-${viewport.width}x${viewport.height}.png`),
        fullPage: true,
        animations: 'disabled',
      })
    }
  }

  expect(audit.externalRequests, 'No request may leave the isolated local browser environment').toEqual([])
  expect(audit.unhandledApiRequests, 'Every Dashboard API request must be explicitly mocked').toEqual([])
  expect(audit.writeRequests, 'The visual audit must not execute any write request').toEqual([])
})
