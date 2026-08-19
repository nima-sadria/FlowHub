import path from 'node:path'
import { mkdirSync } from 'node:fs'
import { expect, test, type Page } from '@playwright/test'
import {
  CHANNELS,
  PRODUCTS,
  TOTAL_PRODUCTS,
  WORKSPACE_ID,
  installProductsMocks,
  json,
  seedSession,
  workspaceResource,
  type TrafficAudit,
} from './products-fixtures'

// Visual + structural audit of the Figma Screen/Products hierarchy: header
// with Save Changes/Bulk Edit, search + filter chip toolbar, one product-
// grouped channel table with inline price/stock/availability editing, and a
// footer product count. Captures 1440x900 evidence for Light/Dark and
// LTR/RTL. All network traffic is mocked inside this spec; nothing leaves
// the isolated browser.

const screenshotRoot = path.resolve('..', 'docs', 'screenshots', 'v1.3', 'products-screen')
mkdirSync(screenshotRoot, { recursive: true })

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
