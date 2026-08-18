import path from 'node:path'
import { expect, test, type Page, type Route } from '@playwright/test'

// Regression coverage for the shared z-index / stacking scale in globals.css
// (--fh-z-sticky / --fh-z-nav / --fh-z-dropdown / --fh-z-overlay / --fh-z-toast).
// The app header (.fh-topbar) previously used an arbitrary z-index of 99999,
// which could render above real overlays (modals, the mobile sidebar drawer)
// that use much lower, uncoordinated values. These specs prove overlays now
// stack correctly relative to the header on desktop and mobile, in LTR and
// RTL. All network traffic is mocked; nothing leaves the isolated browser.

const CHANNEL_ID = 'woocommerce:primary'
const CONNECTOR_TYPE = 'woocommerce'
const TOTAL_ORDERS = 1

const ORDER = {
  internalId: 10482,
  orderNumber: '#10482',
  customerDisplay: 'Ava Thompson',
  normalizedStatus: 'new',
  paymentStatus: 'pending',
  fulfillmentStatus: 'unfulfilled',
  finalAmount: 184.5,
  synchronizationState: 'synced',
  errorState: null as string | null,
}

interface TrafficAudit {
  externalRequests: string[]
  unhandledApiRequests: string[]
}

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({ status, contentType: 'application/json; charset=utf-8', body: JSON.stringify(body) })
}

async function installMocks(page: Page, audit: TrafficAudit) {
  await page.route('**/*', async route => {
    const request = route.request()
    const url = new URL(request.url())
    const method = request.method().toUpperCase()

    if (url.hostname === 'static.userback.io') {
      return route.fulfill({ status: 200, contentType: 'application/javascript', body: 'window.Userback={identify:function(){}}' })
    }
    if (url.hostname !== '127.0.0.1' && url.hostname !== 'localhost') {
      audit.externalRequests.push(`${method} ${url.href}`)
      return route.abort('blockedbyclient')
    }
    if (url.pathname.startsWith('/static/logos/')) {
      return route.fulfill({ path: path.resolve('..', decodeURIComponent(url.pathname.slice(1))) })
    }
    if (!url.pathname.startsWith('/api/')) return route.continue()

    if (url.pathname === '/api/auth/me' && method === 'GET') {
      return json(route, {
        username: 'overlay-owner',
        role: 'admin',
        is_admin: true,
        is_super_admin: false,
        permissions: { can_access_site: true, can_fetch: true, can_view_logs: true, can_view_settings: true },
        maintenance: { enabled: false, message: '' },
      })
    }
    if (url.pathname === '/api/v2/setup/status' && method === 'GET') return json(route, { completed: true })
    if (url.pathname === '/api/health' && method === 'GET') return json(route, { status: 'ok', env: 'test', version: 'overlay-stacking-mock' })
    if (url.pathname === '/api/v2/exchange-rates/me' && method === 'GET') return json(route, { selections: [], rates: [] })
    if (url.pathname === '/api/v2/orders' && method === 'GET') {
      return json(route, {
        items: [{
          internalId: ORDER.internalId,
          channelId: CHANNEL_ID,
          connectorType: CONNECTOR_TYPE,
          providerOrderId: `provider-${ORDER.internalId}`,
          orderNumber: ORDER.orderNumber,
          providerStatus: ORDER.normalizedStatus,
          normalizedStatus: ORDER.normalizedStatus,
          createdAtProvider: '2026-07-23T09:42:00Z',
          updatedAtProvider: '2026-07-23T09:42:00Z',
          currency: 'USD',
          finalAmount: ORDER.finalAmount,
          itemCount: 1,
          synchronizationState: ORDER.synchronizationState,
          eventSource: 'poll',
          errorState: ORDER.errorState,
          lastSeenAt: '2026-07-23T09:42:00Z',
          customerDisplay: ORDER.customerDisplay,
          paymentStatus: ORDER.paymentStatus,
          fulfillmentStatus: ORDER.fulfillmentStatus,
        }],
        total: TOTAL_ORDERS,
        page: 1,
        pageSize: 25,
      })
    }
    if (url.pathname === '/api/v2/orders/sync-status' && method === 'GET') {
      return json(route, {
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
      })
    }
    if (/^\/api\/v2\/orders\/\d+$/.test(url.pathname) && method === 'GET') {
      return json(route, {
        internalId: ORDER.internalId,
        channelId: CHANNEL_ID,
        connectorType: CONNECTOR_TYPE,
        providerOrderId: `provider-${ORDER.internalId}`,
        orderNumber: ORDER.orderNumber,
        providerStatus: ORDER.normalizedStatus,
        normalizedStatus: ORDER.normalizedStatus,
        createdAtProvider: '2026-07-23T09:42:00Z',
        updatedAtProvider: '2026-07-23T09:42:00Z',
        currency: 'USD',
        finalAmount: ORDER.finalAmount,
        itemCount: 1,
        synchronizationState: ORDER.synchronizationState,
        eventSource: 'poll',
        errorState: ORDER.errorState,
        lastSeenAt: '2026-07-23T09:42:00Z',
        customerDisplay: ORDER.customerDisplay,
        paymentStatus: ORDER.paymentStatus,
        fulfillmentStatus: ORDER.fulfillmentStatus,
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

async function seedSession(page: Page, locale: 'en' | 'fa' = 'en', theme: 'light' | 'dark' = 'light') {
  await page.addInitScript(([selectedLocale, selectedTheme]) => {
    localStorage.setItem('wp_token', 'overlay-stacking-isolated-token')
    localStorage.setItem('flowhub.locale', selectedLocale)
    localStorage.setItem('wp_theme', selectedTheme)
  }, [locale, theme])
}

// Reads the effective z-index (resolving CSS custom properties) of the first
// element matching `selector`.
async function zIndexOf(page: Page, selector: string): Promise<number> {
  return page.locator(selector).first().evaluate(el => {
    const value = getComputedStyle(el).zIndex
    const parsed = Number(value)
    return Number.isNaN(parsed) ? -Infinity : parsed
  })
}

test.describe('overlay stacking vs the app header', () => {
  test('order detail modal renders above the header on desktop', async ({ page }) => {
    const audit: TrafficAudit = { externalRequests: [], unhandledApiRequests: [] }
    await installMocks(page, audit)
    await seedSession(page)
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.goto('/orders')

    const topbar = page.locator('.fh-topbar')
    await expect(topbar).toBeVisible()

    await page.locator('[data-orders-row]').first().locator('[data-row-menu-trigger]').click()
    await page.getByRole('menuitem', { name: 'View details' }).click()
    const dialog = page.getByRole('dialog', { name: 'Order details' })
    await expect(dialog).toBeVisible()

    // The dialog backdrop is a fixed inset-0 layer covering the header's own
    // screen position, so this is a genuine, guaranteed-overlap comparison.
    const dialogZ = await zIndexOf(page, '[data-order-details-dialog]')
    const topbarZ = await zIndexOf(page, '.fh-topbar')
    expect(dialogZ).toBeGreaterThan(topbarZ)

    const topbarBox = await topbar.boundingBox()
    expect(topbarBox).not.toBeNull()
    const point = { x: topbarBox!.x + topbarBox!.width / 2, y: topbarBox!.y + topbarBox!.height / 2 }
    const topmostIsInsideDialog = await page.evaluate(({ x, y }) => {
      const el = document.elementFromPoint(x, y)
      return el?.closest('[role="dialog"]') != null
    }, point)
    expect(topmostIsInsideDialog).toBe(true)

    await dialog.getByRole('button', { name: 'Close order details' }).click()
    await expect(dialog).toBeHidden()
    expect(audit.externalRequests).toEqual([])
    expect(audit.unhandledApiRequests).toEqual([])
  })

  test('order detail modal renders above the header on mobile', async ({ page }) => {
    const audit: TrafficAudit = { externalRequests: [], unhandledApiRequests: [] }
    await installMocks(page, audit)
    await seedSession(page)
    await page.setViewportSize({ width: 390, height: 844 })
    await page.goto('/orders')

    const topbar = page.locator('.fh-topbar')
    await expect(topbar).toBeVisible()

    await page.locator('[data-orders-row]').first().locator('[data-row-menu-trigger]').click()
    await page.getByRole('menuitem', { name: 'View details' }).click()
    const dialog = page.getByRole('dialog', { name: 'Order details' })
    await expect(dialog).toBeVisible()

    const dialogZ = await zIndexOf(page, '[data-order-details-dialog]')
    const topbarZ = await zIndexOf(page, '.fh-topbar')
    expect(dialogZ).toBeGreaterThan(topbarZ)

    const topbarBox = await topbar.boundingBox()
    expect(topbarBox).not.toBeNull()
    const point = { x: topbarBox!.x + topbarBox!.width / 2, y: topbarBox!.y + topbarBox!.height / 2 }
    const topmostIsInsideDialog = await page.evaluate(({ x, y }) => {
      const el = document.elementFromPoint(x, y)
      return el?.closest('[role="dialog"]') != null
    }, point)
    expect(topmostIsInsideDialog).toBe(true)

    expect(audit.externalRequests).toEqual([])
    expect(audit.unhandledApiRequests).toEqual([])
  })

  test('order detail modal renders above the header under RTL', async ({ page }) => {
    const audit: TrafficAudit = { externalRequests: [], unhandledApiRequests: [] }
    await installMocks(page, audit)
    await seedSession(page, 'fa')
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.goto('/orders')
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl')

    const topbar = page.locator('.fh-topbar')
    await expect(topbar).toBeVisible()

    await page.locator('[data-orders-row]').first().locator('[data-row-menu-trigger]').click()
    await page.getByRole('menuitem').first().click()
    const dialog = page.getByRole('dialog').first()
    await expect(dialog).toBeVisible()

    const dialogZ = await dialog.evaluate(el => Number(getComputedStyle(el).zIndex))
    const topbarZ = await zIndexOf(page, '.fh-topbar')
    expect(dialogZ).toBeGreaterThan(topbarZ)

    const topbarBox = await topbar.boundingBox()
    expect(topbarBox).not.toBeNull()
    const point = { x: topbarBox!.x + topbarBox!.width / 2, y: topbarBox!.y + topbarBox!.height / 2 }
    const topmostIsInsideDialog = await page.evaluate(({ x, y }) => {
      const el = document.elementFromPoint(x, y)
      return el?.closest('[role="dialog"]') != null
    }, point)
    expect(topmostIsInsideDialog).toBe(true)

    expect(audit.externalRequests).toEqual([])
    expect(audit.unhandledApiRequests).toEqual([])
  })

  test('mobile sidebar drawer renders above the header, backdrop stays below the drawer', async ({ page }) => {
    const audit: TrafficAudit = { externalRequests: [], unhandledApiRequests: [] }
    await installMocks(page, audit)
    await seedSession(page)
    await page.setViewportSize({ width: 390, height: 844 })
    await page.goto('/orders')

    const topbar = page.locator('.fh-topbar')
    await expect(topbar).toBeVisible()

    await page.getByRole('button', { name: 'Open navigation' }).click()
    const drawer = page.locator('#app-navigation')
    await expect(drawer).toBeVisible()

    const drawerZ = await zIndexOf(page, '#app-navigation')
    const backdropZ = await zIndexOf(page, '.fh-sidebar-backdrop')
    const topbarZ = await zIndexOf(page, '.fh-topbar')
    expect(drawerZ).toBeGreaterThan(topbarZ)
    expect(drawerZ).toBeGreaterThan(backdropZ)

    // The drawer overlays the left portion of the header's own screen region.
    const drawerBox = await drawer.boundingBox()
    const topbarBox = await topbar.boundingBox()
    expect(drawerBox).not.toBeNull()
    expect(topbarBox).not.toBeNull()
    const point = { x: Math.max(drawerBox!.x + 5, topbarBox!.x + 5), y: topbarBox!.y + topbarBox!.height / 2 }
    const topmostIsInsideDrawer = await page.evaluate(({ x, y }) => {
      const el = document.elementFromPoint(x, y)
      return el?.closest('#app-navigation') != null
    }, point)
    expect(topmostIsInsideDrawer).toBe(true)

    expect(audit.externalRequests).toEqual([])
    expect(audit.unhandledApiRequests).toEqual([])
  })

  test('topbar account menu and orders filters panel use the dropdown tier, above the nav tier', async ({ page }) => {
    const audit: TrafficAudit = { externalRequests: [], unhandledApiRequests: [] }
    await installMocks(page, audit)
    await seedSession(page)
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.goto('/orders')

    const topbarZ = await zIndexOf(page, '.fh-topbar')

    await page.getByRole('button', { name: 'User menu' }).click()
    const accountMenu = page.locator('.fh-topbar-account-menu')
    await expect(accountMenu).toBeVisible()
    const accountMenuZ = await zIndexOf(page, '.fh-topbar-account-menu')
    expect(accountMenuZ).toBeGreaterThan(topbarZ)
    await page.getByRole('button', { name: 'User menu' }).click()

    await page.getByRole('button', { name: /^Filters/ }).click()
    const filtersPanel = page.locator('.fh-orders-filters-panel')
    await expect(filtersPanel).toBeVisible()
    const filtersPanelZ = await zIndexOf(page, '.fh-orders-filters-panel')
    expect(filtersPanelZ).toBeGreaterThan(topbarZ)

    expect(audit.externalRequests).toEqual([])
    expect(audit.unhandledApiRequests).toEqual([])
  })

  test('scale ordering holds: sticky < nav < dropdown < overlay < toast', async ({ page }) => {
    const audit: TrafficAudit = { externalRequests: [], unhandledApiRequests: [] }
    await installMocks(page, audit)
    await seedSession(page)
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.goto('/orders')

    const tiers = await page.evaluate(() => {
      const root = getComputedStyle(document.documentElement)
      return {
        sticky: Number(root.getPropertyValue('--fh-z-sticky')),
        nav: Number(root.getPropertyValue('--fh-z-nav')),
        dropdown: Number(root.getPropertyValue('--fh-z-dropdown')),
        overlay: Number(root.getPropertyValue('--fh-z-overlay')),
        toast: Number(root.getPropertyValue('--fh-z-toast')),
      }
    })

    expect(tiers.sticky).toBeLessThan(tiers.nav)
    expect(tiers.nav).toBeLessThan(tiers.dropdown)
    expect(tiers.dropdown).toBeLessThan(tiers.overlay)
    expect(tiers.overlay).toBeLessThan(tiers.toast)

    expect(audit.externalRequests).toEqual([])
    expect(audit.unhandledApiRequests).toEqual([])
  })
})
