import path from 'node:path'
import { mkdirSync } from 'node:fs'
import { expect, test, type Page, type Route } from '@playwright/test'

// Visual + structural audit of the Figma Screen/DataQuality hierarchy: header
// with Run check, a compact KPI row (Blocking issues / Warnings / Products
// checked / Last check), a search + severity toolbar, and a flat issue
// table (Issue / Record / Severity / Updated / action). Captures 1440x900
// evidence for Light/Dark and LTR/RTL. All network traffic is mocked inside
// this spec; nothing leaves the isolated browser.

const screenshotRoot = path.resolve('..', 'docs', 'screenshots', 'v1.3', 'data-quality-screen')
mkdirSync(screenshotRoot, { recursive: true })

interface TrafficAudit {
  externalRequests: string[]
  unhandledApiRequests: string[]
}

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({ status, contentType: 'application/json; charset=utf-8', body: JSON.stringify(body) })
}

const NOW = new Date().toISOString()

const ISSUES = [
  { id: 'issue-1', sourceId: 'source-1', sourceProductName: 'Classic T-Shirt', category: 'missing_source_identity', severity: 'blocked', code: 'MISSING_SOURCE_IDENTITY', summary: 'The product name is required before this row can be used.', recommendedAction: 'Fill the Source Product name in this row.', technicalDetails: {} },
  { id: 'issue-2', sourceId: 'source-1', sourceProductName: 'Running Shoes', category: 'invalid_value', severity: 'blocked', code: 'INVALID_NUMERIC_VALUE', summary: 'Price must be a valid numeric value.', recommendedAction: 'Correct the mapped value or change the explicit value policy.', technicalDetails: { field: 'price' } },
  { id: 'issue-3', sourceId: 'source-1', sourceProductName: 'Warehouse inventory', category: 'unavailable_cache', severity: 'warning', code: 'LISTING_CACHE_UNAVAILABLE', summary: 'The mapped Listing or its Channel Cache is unavailable.', recommendedAction: 'Refresh the Channel Cache before creating a Workspace.', technicalDetails: {} },
  { id: 'issue-4', sourceId: 'source-1', sourceProductName: 'Ceramic Mug', category: 'duplicate_rows', severity: 'warning', code: 'DUPLICATE_SOURCE_PRODUCT', summary: 'The same Source Product appears in more than one worksheet.', recommendedAction: 'Keep the product in one worksheet, or explicitly choose which worksheet takes priority.', technicalDetails: {} },
  { id: 'issue-5', sourceId: 'source-1', sourceProductName: 'Seasonal products', category: 'mapping_not_configured', severity: 'warning', code: 'SOURCE_MAPPING_REQUIRED', summary: 'The Source columns have not been configured.', recommendedAction: 'Choose the Source Product and Channel columns, then run the check again.', technicalDetails: {} },
]

async function installDataQualityMocks(page: Page, audit: TrafficAudit) {
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
        username: 'dq-owner',
        role: 'admin',
        is_admin: true,
        is_super_admin: false,
        permissions: { can_access_site: true, can_fetch: true, can_view_logs: true, can_view_settings: true },
        maintenance: { enabled: false, message: '' },
      })
    }
    if (url.pathname === '/api/v2/setup/status' && method === 'GET') return json(route, { completed: true })
    if (url.pathname === '/api/health' && method === 'GET') return json(route, { status: 'ok', env: 'test', version: 'data-quality-visual-mock' })
    if (url.pathname === '/api/v2/source-profiles' && method === 'GET') return json(route, { items: [] })
    if (url.pathname === '/api/v2/source-profiles/channels' && method === 'GET') return json(route, { items: [] })
    if (url.pathname === '/api/v2/products' && method === 'GET') return json(route, { items: [], total: 2418, page: 1, pageSize: 1 })

    if (url.pathname === '/api/v2/data-quality' && method === 'GET') {
      return json(route, {
        items: ISSUES,
        counts: { blocked: 2, warning: 3 },
        total: 5,
        summary: {
          state: 'issues_found', totalIssues: 5, blockingIssues: 4, warnings: 11,
          affectedProducts: 5, affectedChannels: 1, affectedSources: 1,
          resolvedSinceLastRead: 0, trendSinceLastRead: -2,
          productsChecked: 2418, sourcesChecked: 1, checkedAt: NOW, scanId: 'scan-1',
          errorCode: null, categories: [],
        },
      })
    }

    audit.unhandledApiRequests.push(`${method} ${url.pathname}${url.search}`)
    return json(route, { code: 'UNHANDLED_TEST_REQUEST' }, 500)
  })
}

async function seedSession(page: Page, locale: 'en' | 'fa', theme: 'light' | 'dark') {
  await page.addInitScript(([selectedLocale, selectedTheme]) => {
    localStorage.setItem('wp_token', 'data-quality-visual-isolated-token')
    localStorage.setItem('flowhub.locale', selectedLocale)
    localStorage.setItem('wp_theme', selectedTheme)
  }, [locale, theme])
}

async function assertFigmaDataQualityHierarchy(page: Page, locale: 'en' | 'fa') {
  const heading = locale === 'en' ? 'Data Quality' : 'کیفیت داده'
  await expect(page.getByRole('heading', { name: heading, level: 1 })).toBeVisible()

  if (locale === 'en') {
    await expect(page.getByRole('button', { name: /Run check/ })).toBeVisible()
    await expect(page.getByText('Blocking issues')).toBeVisible()
    await expect(page.getByText('Warnings', { exact: true })).toBeVisible()
    await expect(page.getByText('Products checked').first()).toBeVisible()
    await expect(page.getByText('Last check', { exact: true }).first()).toBeVisible()
    await expect(page.getByPlaceholder('Search issues')).toBeVisible()

    await expect(page.getByText('Classic T-Shirt')).toBeVisible()
    await expect(page.getByText('Running Shoes')).toBeVisible()
    await expect(page.locator('table').getByText('Blocked').first()).toBeVisible()
    await expect(page.locator('table').getByText('Warning', { exact: true }).first()).toBeVisible()
  } else {
    await expect(page.getByRole('button', { name: /بررسی/ })).toBeVisible()
    await expect(page.getByText('Classic T-Shirt')).toBeVisible()
  }
}

test('data quality matches the approved Figma hierarchy in Light/Dark and LTR/RTL at 1440x900', async ({ page }) => {
  test.setTimeout(180_000)
  const audit: TrafficAudit = { externalRequests: [], unhandledApiRequests: [] }
  await installDataQualityMocks(page, audit)
  await page.setViewportSize({ width: 1440, height: 900 })

  const variants = [
    { locale: 'en', theme: 'light', dir: 'ltr' },
    { locale: 'en', theme: 'dark', dir: 'ltr' },
    { locale: 'fa', theme: 'light', dir: 'rtl' },
    { locale: 'fa', theme: 'dark', dir: 'rtl' },
  ] as const

  for (const variant of variants) {
    await seedSession(page, variant.locale, variant.theme)
    await page.goto('/data-quality')
    await expect(page.locator('html')).toHaveAttribute('lang', variant.locale)
    await expect(page.locator('html')).toHaveAttribute('dir', variant.dir)
    if (variant.theme === 'dark') {
      await expect(page.locator('html')).toHaveClass(/dark/)
    }
    await expect(page.locator('table')).toBeVisible()
    await assertFigmaDataQualityHierarchy(page, variant.locale)
    await page.evaluate(() => document.fonts.ready)
    await page.screenshot({
      path: path.join(screenshotRoot, `data-quality-${variant.theme}-${variant.dir}-1440x900.png`),
      animations: 'disabled',
    })
  }

  expect(audit.externalRequests, 'No request may leave the isolated local browser environment').toEqual([])
  expect(audit.unhandledApiRequests, 'Every Data Quality API request must be explicitly mocked').toEqual([])
})
