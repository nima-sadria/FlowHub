import path from 'node:path'
import { mkdirSync, readFileSync } from 'node:fs'
import { expect, test, type Page, type Route } from '@playwright/test'

// Visual + structural audit of the Figma Screen/Products hierarchy: header
// with Save Changes/Bulk Edit, search + filter chip toolbar, one product-
// grouped channel table with inline price/stock/availability editing, and a
// footer product count. Captures 1440x900 evidence for Light/Dark and
// LTR/RTL. All network traffic is mocked inside this spec; nothing leaves
// the isolated browser.

const screenshotRoot = path.resolve('..', 'docs', 'screenshots', 'v1.3', 'products-screen')
mkdirSync(screenshotRoot, { recursive: true })
const mockLogo = readFileSync(path.resolve('public', 'flowhub-logo.png'))

const WORKSPACE_ID = 'products-catalog-workspace'
const CHANNELS = [
  { channelId: 'woocommerce:primary', name: 'WooCommerce' },
  { channelId: 'snappshop:main', name: 'SnappShop' },
  { channelId: 'digikala:main', name: 'Digikala' },
  { channelId: 'technolife:main', name: 'Technolife' },
]

type Field = 'price' | 'stock' | 'status'
interface ListingFixture {
  listingId: string
  channelId: string
  price: number
  stock: number
  status: 'in_stock' | 'low_stock'
}
interface ProductFixture {
  productId: string
  name: string
  listings: ListingFixture[]
}

const PRODUCTS: ProductFixture[] = [
  { productId: 'p1', name: 'Classic T-Shirt', listings: [
    { listingId: 'p1-woo', channelId: 'woocommerce:primary', price: 129, stock: 84, status: 'in_stock' },
    { listingId: 'p1-snap', channelId: 'snappshop:main', price: 135, stock: 80, status: 'in_stock' },
    { listingId: 'p1-digi', channelId: 'digikala:main', price: 125, stock: 79, status: 'in_stock' },
  ] },
  { productId: 'p2', name: 'Canvas Backpack', listings: [
    { listingId: 'p2-woo', channelId: 'woocommerce:primary', price: 350, stock: 31, status: 'in_stock' },
    { listingId: 'p2-snap', channelId: 'snappshop:main', price: 380, stock: 28, status: 'in_stock' },
  ] },
  { productId: 'p3', name: 'Running Shoes', listings: [
    { listingId: 'p3-woo', channelId: 'woocommerce:primary', price: 599, stock: 12, status: 'in_stock' },
    { listingId: 'p3-digi', channelId: 'digikala:main', price: 575, stock: 10, status: 'in_stock' },
  ] },
  { productId: 'p4', name: 'Ceramic Mug', listings: [
    { listingId: 'p4-woo', channelId: 'woocommerce:primary', price: 89, stock: 126, status: 'in_stock' },
    { listingId: 'p4-snap', channelId: 'snappshop:main', price: 92, stock: 120, status: 'in_stock' },
    { listingId: 'p4-tech', channelId: 'technolife:main', price: 85, stock: 115, status: 'in_stock' },
  ] },
  { productId: 'p5', name: 'Linen Shirt', listings: [
    { listingId: 'p5-woo', channelId: 'woocommerce:primary', price: 320, stock: 45, status: 'low_stock' },
    { listingId: 'p5-snap', channelId: 'snappshop:main', price: 335, stock: 40, status: 'in_stock' },
  ] },
  { productId: 'p6', name: 'Desk Lamp', listings: [
    { listingId: 'p6-woo', channelId: 'woocommerce:primary', price: 445, stock: 8, status: 'in_stock' },
    { listingId: 'p6-digi', channelId: 'digikala:main', price: 425, stock: 6, status: 'in_stock' },
    { listingId: 'p6-tech', channelId: 'technolife:main', price: 435, stock: 7, status: 'in_stock' },
  ] },
]
const TOTAL_PRODUCTS = 248

interface TrafficAudit {
  externalRequests: string[]
  unhandledApiRequests: string[]
}

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({ status, contentType: 'application/json; charset=utf-8', body: JSON.stringify(body) })
}

function groupedGridResource() {
  return {
    items: PRODUCTS.map(product => ({
      sourceProductId: product.productId,
      name: product.name,
      sourceKey: product.productId.toUpperCase(),
      cost: null,
      category: null,
      brand: null,
      productType: 'simple',
      primaryImageUrl: product.productId === 'p1'
        ? 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="36" height="36"%3E%3Crect width="36" height="36" fill="%233b82f6"/%3E%3C/svg%3E'
        : null,
      media: product.productId === 'p1' ? [{
        type: 'image',
        url: 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="36" height="36"%3E%3Crect width="36" height="36" fill="%233b82f6"/%3E%3C/svg%3E',
        position: 0,
        source: 'woocommerce',
      }] : [],
      mappedChannelCount: product.listings.length,
      listingCount: product.listings.length,
      changedListingCount: 0,
      selectedListingCount: 0,
      state: 'unchanged',
      children: product.listings.map(listing => ({
        listingId: listing.listingId,
        channelId: listing.channelId,
        listingLabel: product.name,
        externalId: `${listing.listingId}-external`,
        externalIdType: 'external_id',
        sku: `${product.productId}-${listing.channelId.split(':')[0]}`,
        mappingState: 'resolved',
        cacheFreshness: 'fresh',
        state: 'unchanged',
        changedFields: [],
        selected: false,
        reviewItemIds: [],
        fields: {
          price: field(String(listing.price), String(listing.price), 'USD', 'USD'),
          stock: field(String(listing.stock), String(listing.stock), null, null),
          status: field(listing.status, listing.status, null, null),
        },
      })),
    })),
    total: TOTAL_PRODUCTS,
    page: 1,
    pageSize: 100,
    view: 'all',
    summary: { ready: 0, blocked: 0, unchanged: TOTAL_PRODUCTS, selected: 0 },
    draftVersion: 0,
    revisionId: null,
    reviewId: null,
    reviewStatus: null,
    selectionChecksum: null,
  }
}

function workspaceResource() {
  return {
    id: WORKSPACE_ID,
    name: 'Pricing workspace',
    entryPoint: 'manual',
    ownerUserId: 1,
    status: 'active',
    version: 1,
    snapshot: { id: 'snapshot-1', checksum: 'hash', schemaVersion: '1', createdAt: '2026-07-18T08:00:00Z' },
    draft: { id: 'draft-1', version: 0, currentRevisionId: null, status: 'draft' },
    createdAt: '2026-07-18T08:00:00Z',
  }
}

function field(current: string, target: string, currency: string | null, unit: string | null) {
  return { current, target, changed: false, readOnly: false, status: 'unchanged', currency, unit }
}

async function installProductsMocks(page: Page, audit: TrafficAudit) {
  await page.route('**/*', async route => {
    const request = route.request()
    const url = new URL(request.url())
    const method = request.method().toUpperCase()

    if (url.hostname !== '127.0.0.1' && url.hostname !== 'localhost') {
      audit.externalRequests.push(`${method} ${url.href}`)
      return route.abort('blockedbyclient')
    }
    if (url.pathname.startsWith('/static/logos/')) return route.fulfill({ status: 200, contentType: 'image/png', body: mockLogo })
    if (!url.pathname.startsWith('/api/')) return route.continue()

    if (url.pathname === '/api/auth/me' && method === 'GET') {
      return json(route, {
        username: 'products-owner',
        role: 'admin',
        is_admin: true,
        is_super_admin: false,
        permissions: { can_access_site: true, can_fetch: true, can_view_logs: true, can_view_settings: true },
        maintenance: { enabled: false, message: '' },
      })
    }
    if (url.pathname === '/api/v2/setup/status' && method === 'GET') return json(route, { completed: true })
    if (url.pathname === '/api/health' && method === 'GET') return json(route, { status: 'ok', env: 'test', version: 'products-visual-mock' })
    if (url.pathname === '/api/v2/exchange-rates/me' && method === 'GET') return json(route, { selections: [], rates: [] })
    if (url.pathname === '/api/v2/settings' && method === 'GET') return json(route, {
      woocommerceUrl: '', nextcloudUrl: '', syncIntervalMinutes: 15, timezone: 'UTC',
      currency: 'USD', currencyUnit: 'USD', environment: 'test', wcConfigured: true, ncConfigured: false,
    })
    if (url.pathname === '/api/v2/products/categories' && method === 'GET') return json(route, { items: [] })
    if (url.pathname === '/api/v2/source-profiles/channels' && method === 'GET') {
      return json(route, {
        items: CHANNELS.map(channel => ({
          channelId: channel.channelId,
          name: channel.name,
          connectorType: channel.channelId.split(':')[0],
          capabilityVersion: 'products-visual-v1',
          capabilities: {
            writePrice: true,
            writeStock: true,
            writeStatus: true,
            writeAvailable: true,
            supportedStatuses: ['in_stock', 'low_stock', 'out_of_stock'],
            currency: 'USD',
            unit: 'USD',
          },
          enabled: true,
          implementationState: 'implemented',
          available: true,
        })),
      })
    }
    if (url.pathname === '/api/v2/unified-workspaces/manual' && method === 'POST') {
      return json(route, workspaceResource())
    }
    if (url.pathname === `/api/v2/unified-workspaces/${WORKSPACE_ID}` && method === 'GET') {
      return json(route, workspaceResource())
    }
    if (url.pathname === `/api/v2/unified-workspaces/${WORKSPACE_ID}/grouped-grid` && method === 'GET') {
      return json(route, groupedGridResource())
    }

    audit.unhandledApiRequests.push(`${method} ${url.pathname}${url.search}`)
    return json(route, { code: 'UNHANDLED_TEST_REQUEST' }, 500)
  })
}

async function seedSession(page: Page, locale: 'en' | 'fa', theme: 'light' | 'dark') {
  await page.addInitScript(([selectedLocale, selectedTheme]) => {
    localStorage.setItem('wp_token', 'products-visual-isolated-token')
    localStorage.setItem('flowhub.locale', selectedLocale)
    localStorage.setItem('wp_theme', selectedTheme)
  }, [locale, theme])
}

async function assertFigmaProductsHierarchy(page: Page, locale: 'en' | 'fa') {
  const heading = locale === 'en' ? 'Products' : 'محصولات'
  await expect(page.getByRole('heading', { name: heading, level: 1 })).toBeVisible()

  if (locale === 'en') {
    await expect(page.getByRole('button', { name: 'Save Changes' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Bulk Edit' })).toBeVisible()
    await expect(page.getByPlaceholder('Search products...')).toBeVisible()
    await expect(page.locator('.fh-chip-select .sr-only', { hasText: 'All statuses' })).toBeAttached()
    await expect(page.locator('.fh-chip-select .sr-only', { hasText: 'All channels' })).toBeAttached()
    await expect(page.locator('.fh-chip-select .sr-only', { hasText: 'Saved Views' })).toBeAttached()
    await expect(page.getByText('Filters')).toBeVisible()

    for (const label of ['Product', 'Channel', 'Stock', 'Availability', 'Last Sync', 'Actions']) {
      await expect(page.locator('.fh-products-table thead th', { hasText: label })).toBeVisible()
    }
    await expect(page.locator('.fh-products-table thead th', { hasText: /^Price/ })).toBeVisible()

    const table = page.locator('.fh-products-table')
    for (const product of PRODUCTS) await expect(table.getByText(product.name, { exact: true })).toBeVisible()
    for (const channel of CHANNELS) await expect(table.getByText(channel.name, { exact: true }).first()).toBeVisible()
    await expect(table.locator('.fh-availability[data-tone="success"]').first()).toBeVisible()
    await expect(table.locator('.fh-availability[data-tone="warning"]').first()).toBeVisible()
    await expect(page.getByText(`Showing ${TOTAL_PRODUCTS} products`)).toBeVisible()
  } else {
    await expect(page.getByRole('button', { name: 'ذخیره تغییرات' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'ویرایش گروهی' })).toBeVisible()
    await expect(page.getByPlaceholder('جست‌وجوی محصولات...')).toBeVisible()
    await expect(page.locator('.fh-chip-select .sr-only', { hasText: 'همه وضعیت‌ها' })).toBeAttached()
    await expect(page.locator('.fh-chip-select .sr-only', { hasText: 'همه کانال‌ها' })).toBeAttached()
    await expect(page.locator('.fh-chip-select .sr-only', { hasText: 'نماهای ذخیره‌شده' })).toBeAttached()
    await expect(page.getByText('فیلترها')).toBeVisible()

    for (const label of ['محصول', 'کانال', 'موجودی', 'وضعیت', 'عملیات']) {
      await expect(page.locator('.fh-products-table thead th', { hasText: label })).toBeVisible()
    }
    await expect(page.locator('.fh-products-table .fh-availability[data-tone="success"]').first()).toBeVisible()
    await expect(page.locator('.fh-products-table .fh-availability[data-tone="warning"]').first()).toBeVisible()
    await expect(page.getByText(`نمایش ${TOTAL_PRODUCTS} محصول`.replace(/[0-9]+/, () => toPersianDigits(TOTAL_PRODUCTS)))).toBeVisible()
  }
}

function toPersianDigits(value: number): string {
  const digits = ['۰', '۱', '۲', '۳', '۴', '۵', '۶', '۷', '۸', '۹']
  return String(value).replace(/[0-9]/g, digit => digits[Number(digit)])
}

test('products matches the approved Figma hierarchy in Light/Dark and LTR/RTL at 1440x900', async ({ page }) => {
  test.setTimeout(180_000)
  const audit: TrafficAudit = { externalRequests: [], unhandledApiRequests: [] }
  await installProductsMocks(page, audit)
  await page.setViewportSize({ width: 1440, height: 900 })

  const variants = [
    { locale: 'en', theme: 'light', dir: 'ltr' },
    { locale: 'en', theme: 'dark', dir: 'ltr' },
    { locale: 'fa', theme: 'light', dir: 'rtl' },
    { locale: 'fa', theme: 'dark', dir: 'rtl' },
  ] as const

  for (const variant of variants) {
    await seedSession(page, variant.locale, variant.theme)
    await page.goto('/products')
    await expect(page.locator('html')).toHaveAttribute('lang', variant.locale)
    await expect(page.locator('html')).toHaveAttribute('dir', variant.dir)
    if (variant.theme === 'dark') {
      await expect(page.locator('html')).toHaveClass(/dark/)
    }
    await expect(page.locator('.fh-products-table')).toBeVisible()
    await assertFigmaProductsHierarchy(page, variant.locale)
    await page.evaluate(() => document.fonts.ready)
    await page.screenshot({
      path: path.join(screenshotRoot, `products-${variant.theme}-${variant.dir}-1440x900.png`),
      animations: 'disabled',
    })
  }

  expect(audit.externalRequests, 'No request may leave the isolated local browser environment').toEqual([])
  expect(audit.unhandledApiRequests, 'Every Products API request must be explicitly mocked').toEqual([])
})

test('products renders canonical grid media without a metadata request per product', async ({ page }) => {
  const audit: TrafficAudit = { externalRequests: [], unhandledApiRequests: [] }
  await installProductsMocks(page, audit)
  await seedSession(page, 'en', 'light')

  await page.goto('/products')
  const firstProduct = page.locator('[data-product-group][data-product-id="p1"]')
  const image = firstProduct.locator('[data-product-thumbnail] img')
  await expect(image).toBeVisible()
  await expect(image).toHaveAttribute('src', /^data:image\/svg\+xml/)
  expect(await image.evaluate(element => (element as HTMLImageElement).naturalWidth)).toBeGreaterThan(0)

  expect(audit.externalRequests).toEqual([])
  expect(audit.unhandledApiRequests).toEqual([])
})

test('products first paint keeps its title and loading filters labeled', async ({ page }) => {
  const audit: TrafficAudit = { externalRequests: [], unhandledApiRequests: [] }
  await installProductsMocks(page, audit)
  let releaseWorkspace!: () => void
  const workspaceGate = new Promise<void>(resolve => { releaseWorkspace = resolve })
  await page.route('**/api/v2/unified-workspaces/manual', async route => {
    await workspaceGate
    await json(route, workspaceResource())
  })
  await seedSession(page, 'en', 'light')
  await page.goto('/products')

  await expect(page.getByRole('heading', { name: 'Products', level: 1 })).toBeVisible()
  await expect(page.locator('.fh-chip-select-skeleton')).toHaveCount(0)
  expect(await page.locator('.fh-chip-select select').evaluateAll(elements => elements.map(element => (element as HTMLSelectElement).value))).toEqual(['All statuses', 'All Channels', 'Saved Views'])
  await expect(page.locator('.animate-pulse')).toHaveCount(3)
  releaseWorkspace()
  await expect(page.locator('[data-products-table]')).toBeVisible()
  expect(audit.externalRequests).toEqual([])
  expect(audit.unhandledApiRequests).toEqual([])
})

test('products keeps table scrolling internal and channel identity stable across the required responsive matrix', async ({ page }) => {
  test.setTimeout(180_000)
  const audit: TrafficAudit = { externalRequests: [], unhandledApiRequests: [] }
  await installProductsMocks(page, audit)
  const matrix = [
    { width: 1280, height: 800, locale: 'en', theme: 'light', label: 'ltr-light-desktop-1280x800' },
    { width: 1024, height: 768, locale: 'en', theme: 'light', label: 'ltr-light-tablet-1024x768' },
    { width: 768, height: 1024, locale: 'fa', theme: 'dark', label: 'rtl-dark-tablet-768x1024' },
    { width: 390, height: 844, locale: 'en', theme: 'light', label: 'ltr-light-mobile-390x844' },
    { width: 390, height: 844, locale: 'fa', theme: 'dark', label: 'rtl-dark-mobile-390x844' },
    { width: 360, height: 800, locale: 'en', theme: 'light', label: 'ltr-light-mobile-360x800' },
  ] as const

  for (const cell of matrix) {
    await page.setViewportSize({ width: cell.width, height: cell.height })
    await seedSession(page, cell.locale, cell.theme)
    await page.goto('/products')
    await expect(page.locator('[data-products-table]')).toBeVisible()
    await expect(page.locator('[data-products-table] thead th').first()).toHaveCSS('position', cell.width < 1280 ? 'sticky' : 'static')
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true)

    const card = page.locator('[data-products-table]')
    const metrics = await card.evaluate(element => ({ clientWidth: element.clientWidth, scrollWidth: element.scrollWidth, overflowX: getComputedStyle(element).overflowX }))
    expect(metrics.overflowX).toBe('auto')
    if (cell.width <= 768) expect(metrics.scrollWidth).toBeGreaterThan(metrics.clientWidth)

    const headerBoxes = (await page.locator('[data-products-table] thead th').evaluateAll(elements => elements.map(element => {
      const box = element.getBoundingClientRect()
      return { left: box.left, right: box.right, width: box.width }
    }))).sort((left, right) => left.left - right.left)
    expect(headerBoxes.every(box => box.width > 0)).toBe(true)
    expect(headerBoxes.slice(1).every((box, index) => headerBoxes[index].right <= box.left + 1)).toBe(true)

    const optionLabels = await page.locator('select[name="channelId"] option:not([value=""])').allTextContents()
    const rowLabels = await page.locator('.fh-products-channel-cell').allTextContents()
    for (const label of new Set(rowLabels.map(value => value.trim()))) expect(optionLabels.map(value => value.trim())).toContain(label)
    if (cell.width < 1280) {
      const actionsTrigger = page.locator('[aria-controls="topbar-mobile-actions"]')
      const navigationTrigger = page.locator('[aria-controls="app-navigation"]')
      await actionsTrigger.click()
      await expect(actionsTrigger).toHaveAttribute('aria-expanded', 'true')
      await navigationTrigger.click()
      await expect(actionsTrigger).toHaveAttribute('aria-expanded', 'false')
      await expect(page.locator('#app-navigation')).toHaveAttribute('role', 'dialog')
      await page.keyboard.press('Escape')
      await expect(page.locator('#app-navigation')).not.toHaveAttribute('role', 'dialog')
      await expect(navigationTrigger).toBeFocused()
    }
    await page.screenshot({ path: path.join(screenshotRoot, `products-${cell.label}.png`), animations: 'disabled' })
  }

  expect(audit.externalRequests).toEqual([])
  expect(audit.unhandledApiRequests).toEqual([])
})
