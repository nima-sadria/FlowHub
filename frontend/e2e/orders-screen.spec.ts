import path from 'node:path'
import { mkdirSync } from 'node:fs'
import { expect, test, type Page, type Route } from '@playwright/test'

// Visual + structural audit of the Figma Screen/Orders hierarchy: header with
// Sync orders, a sync status strip, a condensed filter toolbar (search/order
// state/channel/saved views/filters), a table with Columns/Sort controls and
// a per-row Sync column + row actions menu, numbered pagination, and a bottom
// "Order synchronization" summary card. Captures 1440x900 evidence for
// Light/Dark and LTR/RTL. All network traffic is mocked inside this spec;
// nothing leaves the isolated browser.

const screenshotRoot = path.resolve('..', 'docs', 'screenshots', 'v1.3', 'orders-screen')
mkdirSync(screenshotRoot, { recursive: true })

interface OrderFixture {
  internalId: number
  orderNumber: string
  customerDisplay: string
  normalizedStatus: string
  paymentStatus: string
  fulfillmentStatus: string
  finalAmount: number
  synchronizationState: string
  errorState: string | null
}

const CHANNEL_ID = 'woocommerce:primary'
const CONNECTOR_TYPE = 'woocommerce'
const TOTAL_ORDERS = 248

const ORDERS: OrderFixture[] = [
  { internalId: 10482, orderNumber: '#10482', customerDisplay: 'Ava Thompson', normalizedStatus: 'new', paymentStatus: 'pending', fulfillmentStatus: 'unfulfilled', finalAmount: 184.50, synchronizationState: 'synced', errorState: null },
  { internalId: 10481, orderNumber: '#10481', customerDisplay: 'Noah Williams', normalizedStatus: 'processing', paymentStatus: 'paid', fulfillmentStatus: 'unfulfilled', finalAmount: 72.00, synchronizationState: 'synced', errorState: null },
  { internalId: 10480, orderNumber: '#10480', customerDisplay: 'Mia Johnson', normalizedStatus: 'fulfilled', paymentStatus: 'paid', fulfillmentStatus: 'fulfilled', finalAmount: 318.40, synchronizationState: 'synced', errorState: null },
  { internalId: 10479, orderNumber: '#10479', customerDisplay: 'Liam Brown', normalizedStatus: 'new', paymentStatus: 'pending', fulfillmentStatus: 'unfulfilled', finalAmount: 44.00, synchronizationState: 'synced', errorState: null },
  { internalId: 10478, orderNumber: '#10478', customerDisplay: 'Emma Davis', normalizedStatus: 'processing', paymentStatus: 'paid', fulfillmentStatus: 'unfulfilled', finalAmount: 126.90, synchronizationState: 'failed', errorState: 'timeout' },
  { internalId: 10477, orderNumber: '#10477', customerDisplay: 'Oliver Wilson', normalizedStatus: 'processing', paymentStatus: 'paid', fulfillmentStatus: 'unfulfilled', finalAmount: 89.00, synchronizationState: 'synced', errorState: null },
]

interface TrafficAudit {
  externalRequests: string[]
  unhandledApiRequests: string[]
}

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({ status, contentType: 'application/json; charset=utf-8', body: JSON.stringify(body) })
}

function ordersListResource() {
  return {
    items: ORDERS.map(order => ({
      internalId: order.internalId,
      channelId: CHANNEL_ID,
      connectorType: CONNECTOR_TYPE,
      providerOrderId: `provider-${order.internalId}`,
      orderNumber: order.orderNumber,
      providerStatus: order.normalizedStatus,
      normalizedStatus: order.normalizedStatus,
      createdAtProvider: '2026-07-23T09:42:00Z',
      updatedAtProvider: '2026-07-23T09:42:00Z',
      currency: 'USD',
      finalAmount: order.finalAmount,
      itemCount: 1,
      synchronizationState: order.synchronizationState,
      eventSource: 'poll',
      errorState: order.errorState,
      lastSeenAt: '2026-07-23T09:42:00Z',
      customerDisplay: order.customerDisplay,
      paymentStatus: order.paymentStatus,
      fulfillmentStatus: order.fulfillmentStatus,
    })),
    total: TOTAL_ORDERS,
    page: 1,
    pageSize: 25,
  }
}

function syncStatusResource() {
  return {
    items: [{
      channelId: CHANNEL_ID,
      connectorType: CONNECTOR_TYPE,
      displayName: 'WooCommerce',
      enabled: true,
      state: 'ready',
      lastRunAt: '2026-07-23T10:00:00Z',
      lastSuccessAt: '2026-07-23T10:00:00Z',
      lastFailureAt: null,
      failureCategory: null,
    }],
  }
}

async function installOrdersMocks(page: Page, audit: TrafficAudit) {
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
        username: 'orders-owner',
        role: 'admin',
        is_admin: true,
        is_super_admin: false,
        permissions: { can_access_site: true, can_fetch: true, can_view_logs: true, can_view_settings: true },
        maintenance: { enabled: false, message: '' },
      })
    }
    if (url.pathname === '/api/v2/setup/status' && method === 'GET') return json(route, { completed: true })
    if (url.pathname === '/api/health' && method === 'GET') return json(route, { status: 'ok', env: 'test', version: 'orders-visual-mock' })
    if (url.pathname === '/api/v2/exchange-rates/me' && method === 'GET') return json(route, { selections: [], rates: [] })
    if (url.pathname === '/api/v2/orders' && method === 'GET') return json(route, ordersListResource())
    if (url.pathname === '/api/v2/orders/sync-status' && method === 'GET') return json(route, syncStatusResource())
    if (/^\/api\/v2\/orders\/channels\/[^/]+\/sync$/.test(url.pathname) && method === 'POST') {
      return json(route, {
        channelId: CHANNEL_ID,
        source: 'reconciliation',
        processed: ORDERS.length,
        duplicates: 0,
        state: 'completed',
        canonicalInventoryMutated: false,
        productPricesWritten: false,
        providerMutationPerformed: false,
      })
    }
    if (/^\/api\/v2\/orders\/\d+$/.test(url.pathname) && method === 'GET') {
      const match = ORDERS.find(order => url.pathname.endsWith(String(order.internalId)))
      return json(route, {
        internalId: match?.internalId ?? 0,
        channelId: CHANNEL_ID,
        connectorType: CONNECTOR_TYPE,
        providerOrderId: `provider-${match?.internalId ?? 0}`,
        orderNumber: match?.orderNumber ?? '',
        providerStatus: match?.normalizedStatus ?? '',
        normalizedStatus: match?.normalizedStatus ?? '',
        createdAtProvider: '2026-07-23T09:42:00Z',
        updatedAtProvider: '2026-07-23T09:42:00Z',
        currency: 'USD',
        finalAmount: match?.finalAmount ?? 0,
        itemCount: 1,
        synchronizationState: match?.synchronizationState ?? 'synced',
        eventSource: 'poll',
        errorState: match?.errorState ?? null,
        lastSeenAt: '2026-07-23T09:42:00Z',
        customerDisplay: match?.customerDisplay ?? '',
        paymentStatus: match?.paymentStatus ?? '',
        fulfillmentStatus: match?.fulfillmentStatus ?? '',
        items: [],
        shipments: [],
        invoices: [],
        timeline: [],
      })
    }

    audit.unhandledApiRequests.push(`${method} ${url.pathname}${url.search}`)
    return json(route, { code: 'UNHANDLED_TEST_REQUEST' }, 500)
  })
}

async function seedSession(page: Page, locale: 'en' | 'fa', theme: 'light' | 'dark') {
  await page.addInitScript(([selectedLocale, selectedTheme]) => {
    localStorage.setItem('wp_token', 'orders-visual-isolated-token')
    localStorage.setItem('flowhub.locale', selectedLocale)
    localStorage.setItem('wp_theme', selectedTheme)
  }, [locale, theme])
}

async function assertFigmaOrdersHierarchy(page: Page, locale: 'en' | 'fa') {
  const heading = locale === 'en' ? 'Orders' : 'سفارش‌ها'
  await expect(page.getByRole('heading', { name: heading, level: 1 })).toBeVisible()

  if (locale === 'en') {
    await expect(page.getByText('Unified orders across every connected channel.')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Sync orders' })).toBeVisible()
    await expect(page.locator('[data-orders-sync-strip]').getByText('Synced')).toBeVisible()
    await expect(page.getByPlaceholder('Search orders')).toBeVisible()
    await expect(page.locator('.fh-chip-select .sr-only', { hasText: 'All order states' })).toBeAttached()
    await expect(page.locator('.fh-chip-select .sr-only', { hasText: 'All Channels' })).toBeAttached()
    await expect(page.getByRole('button', { name: 'Saved views' })).toBeVisible()
    await expect(page.getByRole('button', { name: /^Filters/ })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Columns' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Sort' })).toBeVisible()

    for (const label of ['Order', 'Channel', 'Customer', 'Status', 'Payment', 'Fulfillment', 'Total', 'Created', 'Sync']) {
      await expect(page.locator('[data-orders-table] thead th', { hasText: new RegExp(`^${label}$`) })).toBeVisible()
    }
    const table = page.locator('[data-orders-table]')
    for (const order of ORDERS) await expect(table.getByText(order.customerDisplay, { exact: true })).toBeVisible()
    await expect(table.getByText('#10482')).toBeVisible()
    await expect(table.locator('[data-sync-cell]', { hasText: 'Retry' })).toBeVisible()
    await expect(page.getByText(`1–${Math.min(25, TOTAL_ORDERS)} of ${TOTAL_ORDERS}`)).toBeVisible()
    await expect(page.locator('[data-orders-pager]').getByText('12')).toBeVisible()
    await expect(page.getByText('Order synchronization')).toBeVisible()
  } else {
    await expect(page.getByText('همه سفارش‌های کانال‌های متصل، یکجا.')).toBeVisible()
    await expect(page.getByRole('button', { name: 'همگام‌سازی سفارش‌ها' }).first()).toBeVisible()
    await expect(page.getByPlaceholder('جستجوی سفارش‌ها')).toBeVisible()
    await expect(page.locator('.fh-chip-select .sr-only', { hasText: 'همه وضعیت‌های سفارش' })).toBeAttached()
    await expect(page.getByRole('button', { name: 'نماهای ذخیره‌شده' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'ستون‌ها' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'مرتب‌سازی' })).toBeVisible()

    for (const label of ['سفارش', 'کانال', 'مشتری', 'وضعیت', 'ایجادشده']) {
      await expect(page.locator('[data-orders-table] thead th', { hasText: new RegExp(`^${label}$`) })).toBeVisible()
    }
    const table = page.locator('[data-orders-table]')
    for (const order of ORDERS) await expect(table.getByText(order.customerDisplay, { exact: true })).toBeVisible()
  }
}

test('orders matches the approved Figma hierarchy in Light/Dark and LTR/RTL at 1440x900', async ({ page }) => {
  test.setTimeout(180_000)
  const audit: TrafficAudit = { externalRequests: [], unhandledApiRequests: [] }
  await installOrdersMocks(page, audit)
  await page.setViewportSize({ width: 1440, height: 900 })

  const variants = [
    { locale: 'en', theme: 'light', dir: 'ltr' },
    { locale: 'en', theme: 'dark', dir: 'ltr' },
    { locale: 'fa', theme: 'light', dir: 'rtl' },
    { locale: 'fa', theme: 'dark', dir: 'rtl' },
  ] as const

  for (const variant of variants) {
    await seedSession(page, variant.locale, variant.theme)
    await page.goto('/orders')
    await expect(page.locator('html')).toHaveAttribute('lang', variant.locale)
    await expect(page.locator('html')).toHaveAttribute('dir', variant.dir)
    if (variant.theme === 'dark') {
      await expect(page.locator('html')).toHaveClass(/dark/)
    }
    await expect(page.locator('[data-orders-table]')).toBeVisible()
    await assertFigmaOrdersHierarchy(page, variant.locale)
    await page.evaluate(() => document.fonts.ready)
    await page.screenshot({
      path: path.join(screenshotRoot, `orders-${variant.theme}-${variant.dir}-1440x900.png`),
      animations: 'disabled',
    })
  }

  expect(audit.externalRequests, 'No request may leave the isolated local browser environment').toEqual([])
  expect(audit.unhandledApiRequests, 'Every Orders API request must be explicitly mocked').toEqual([])
})

test('orders View details opens a visible accessible dialog and closes cleanly', async ({ page }) => {
  const audit: TrafficAudit = { externalRequests: [], unhandledApiRequests: [] }
  await installOrdersMocks(page, audit)
  await seedSession(page, 'en', 'light')
  await page.goto('/orders')

  const firstRow = page.locator('[data-orders-row]').first()
  await firstRow.locator('[data-row-menu-trigger]').click()
  await page.getByRole('menuitem', { name: 'View details' }).click()

  const dialog = page.getByRole('dialog', { name: 'Order details' })
  await expect(dialog).toBeVisible()
  await expect(dialog.getByText(`provider-${ORDERS[0].internalId}`, { exact: true })).toBeVisible()
  await expect(dialog.getByText(ORDERS[0].customerDisplay, { exact: true })).toBeVisible()

  await dialog.getByRole('button', { name: 'Close order details' }).click()
  await expect(dialog).toBeHidden()
  expect(audit.externalRequests).toEqual([])
  expect(audit.unhandledApiRequests).toEqual([])
})
