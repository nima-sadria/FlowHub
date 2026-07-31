import path from 'node:path'
import { mkdirSync } from 'node:fs'
import { expect, test, type Page, type Route } from '@playwright/test'

// Visual + structural audit of the Figma Screen/Sources hierarchy: header with
// Add source, a KPI stat row (Connected Sources / Needs Attention / Products
// Imported), a condensed search + health-state toolbar, and a flat grid of
// source cards (icon, health badge, "Updated x ago", worksheets-enabled count,
// Configure link). Captures 1440x900 evidence for Light/Dark and LTR/RTL. All
// network traffic is mocked inside this spec; nothing leaves the isolated
// browser.

const screenshotRoot = path.resolve('..', 'docs', 'screenshots', 'v1.3', 'sources-screen')
mkdirSync(screenshotRoot, { recursive: true })

interface SourceFixture {
  id: string
  name: string
  status: string
  mappingVersion: number
  updatedAt: string
  worksheetCount: number
}

const NOW = new Date()
const SOURCES: SourceFixture[] = [
  { id: 'source-primary', name: 'Primary catalog', status: 'active', mappingVersion: 3, updatedAt: new Date(NOW.getTime() - 4 * 60_000).toISOString(), worksheetCount: 6 },
  { id: 'source-warehouse', name: 'Warehouse inventory', status: 'active', mappingVersion: 0, updatedAt: new Date(NOW.getTime() - 12 * 60_000).toISOString(), worksheetCount: 0 },
  { id: 'source-seasonal', name: 'Seasonal products', status: 'active', mappingVersion: 2, updatedAt: new Date(NOW.getTime() - 60 * 60_000).toISOString(), worksheetCount: 6 },
  { id: 'source-archive', name: 'Archive import', status: 'disabled', mappingVersion: 1, updatedAt: new Date(NOW.getTime() - 26 * 60 * 60_000).toISOString(), worksheetCount: 4 },
]
const TOTAL_PRODUCTS = 2418

interface TrafficAudit {
  externalRequests: string[]
  unhandledApiRequests: string[]
}

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({ status, contentType: 'application/json; charset=utf-8', body: JSON.stringify(body) })
}

function sourceProfileShape(fixture: SourceFixture) {
  return {
    id: fixture.id,
    name: fixture.name,
    sourceKind: 'flowhub_sheet',
    externalSourceId: null,
    worksheetMode: 'all',
    worksheetName: null,
    dataStartRow: 1,
    status: fixture.status,
    version: 1,
    mappingVersion: fixture.mappingVersion,
    sheetId: fixture.mappingVersion > 0 ? `${fixture.id}-sheet` : null,
    createdAt: fixture.updatedAt,
    updatedAt: fixture.updatedAt,
  }
}

async function installSourcesMocks(page: Page, audit: TrafficAudit) {
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
        username: 'sources-owner',
        role: 'admin',
        is_admin: true,
        is_super_admin: false,
        permissions: { can_access_site: true, can_fetch: true, can_view_logs: true, can_view_settings: true, 'workspace.admin': true },
        maintenance: { enabled: false, message: '' },
      })
    }
    if (url.pathname === '/api/v2/setup/status' && method === 'GET') return json(route, { completed: true })
    if (url.pathname === '/api/health' && method === 'GET') return json(route, { status: 'ok', env: 'test', version: 'sources-visual-mock' })
    if (url.pathname === '/api/v2/exchange-rates/me' && method === 'GET') return json(route, { selections: [], rates: [] })
    if (url.pathname === '/api/v2/source-profiles' && method === 'GET') {
      return json(route, { items: SOURCES.map(sourceProfileShape) })
    }
    if (url.pathname === '/api/v2/commerce/sources' && method === 'GET') {
      return json(route, { items: [], relationship_map: { nodes: [], example: [], runtime_write_blocked: true, read_only: true } })
    }
    if (url.pathname === '/api/v2/products' && method === 'GET') {
      return json(route, { items: [], total: TOTAL_PRODUCTS, page: 1, pageSize: 1, configured: true })
    }
    const configMatch = /^\/api\/v2\/sources\/([^/]+)\/configuration$/.exec(url.pathname)
    if (configMatch && method === 'GET') {
      const fixture = SOURCES.find(item => item.id === decodeURIComponent(configMatch[1]))
      if (!fixture) return json(route, { code: 'NOT_FOUND' }, 404)
      const worksheetRules = Array.from({ length: fixture.worksheetCount }, (_, index) => ({
        worksheetName: `Sheet${index + 1}`,
        enabled: true,
        dataStartRow: 2,
        sourceFields: [],
        channelMappings: [],
        valuePolicy: {},
      }))
      return json(route, {
        ...sourceProfileShape(fixture),
        mapping: fixture.mappingVersion > 0 ? {
          id: `${fixture.id}-mapping`,
          version: fixture.mappingVersion,
          checksum: 'checksum',
          worksheetMode: 'all',
          worksheetName: null,
          dataStartRow: 1,
          valuePolicy: {},
          worksheetRules,
          sourceFields: [],
          channels: [],
        } : null,
      })
    }

    audit.unhandledApiRequests.push(`${method} ${url.pathname}${url.search}`)
    return json(route, { code: 'UNHANDLED_TEST_REQUEST' }, 500)
  })
}

async function seedSession(page: Page, locale: 'en' | 'fa', theme: 'light' | 'dark') {
  await page.addInitScript(([selectedLocale, selectedTheme]) => {
    localStorage.setItem('wp_token', 'sources-visual-isolated-token')
    localStorage.setItem('flowhub.locale', selectedLocale)
    localStorage.setItem('wp_theme', selectedTheme)
  }, [locale, theme])
}

async function assertFigmaSourcesHierarchy(page: Page, locale: 'en' | 'fa') {
  const heading = locale === 'en' ? 'Sources' : 'منابع'
  await expect(page.getByRole('heading', { name: heading, level: 1 })).toBeVisible()

  if (locale === 'en') {
    await expect(page.getByText('Manage business data sources that feed FlowHub.')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Add source' })).toBeVisible()
    await expect(page.getByText('Connected Sources')).toBeVisible()
    await expect(page.getByText('Needs Attention')).toBeVisible()
    await expect(page.getByText('Products Imported')).toBeVisible()
    await expect(page.getByText('2,418')).toBeVisible()
    await expect(page.getByPlaceholder('Search sources')).toBeVisible()
    await expect(page.locator('.fh-chip-select .sr-only', { hasText: 'All health states' })).toBeAttached()
    await expect(page.getByText('4 sources')).toBeVisible()

    const grid = page.locator('[data-testid="source-card-groups"]')
    for (const fixture of SOURCES) await expect(grid.getByText(fixture.name, { exact: true })).toBeVisible()
    await expect(grid.locator('[data-source-card]')).toHaveCount(4)
    await expect(grid.getByText('Connected', { exact: true }).first()).toBeVisible()
    await expect(grid.getByText('Setup required', { exact: true }).first()).toBeVisible()
    await expect(grid.getByText('6 worksheets enabled').first()).toBeVisible()
  } else {
    await expect(page.getByRole('button', { name: 'افزودن منبع' })).toBeVisible()
    await expect(page.getByText('منابع متصل')).toBeVisible()
    await expect(page.getByPlaceholder('جست‌وجوی منابع')).toBeVisible()
    const grid = page.locator('[data-testid="source-card-groups"]')
    for (const fixture of SOURCES) await expect(grid.getByText(fixture.name, { exact: true })).toBeVisible()
  }
}

test('sources matches the approved Figma hierarchy in Light/Dark and LTR/RTL at 1440x900', async ({ page }) => {
  test.setTimeout(180_000)
  const audit: TrafficAudit = { externalRequests: [], unhandledApiRequests: [] }
  await installSourcesMocks(page, audit)
  await page.setViewportSize({ width: 1440, height: 900 })

  const variants = [
    { locale: 'en', theme: 'light', dir: 'ltr' },
    { locale: 'en', theme: 'dark', dir: 'ltr' },
    { locale: 'fa', theme: 'light', dir: 'rtl' },
    { locale: 'fa', theme: 'dark', dir: 'rtl' },
  ] as const

  for (const variant of variants) {
    await seedSession(page, variant.locale, variant.theme)
    await page.goto('/sources')
    await expect(page.locator('html')).toHaveAttribute('lang', variant.locale)
    await expect(page.locator('html')).toHaveAttribute('dir', variant.dir)
    if (variant.theme === 'dark') {
      await expect(page.locator('html')).toHaveClass(/dark/)
    }
    await expect(page.locator('[data-testid="source-card-groups"]')).toBeVisible()
    await assertFigmaSourcesHierarchy(page, variant.locale)
    await page.evaluate(() => document.fonts.ready)
    await page.screenshot({
      path: path.join(screenshotRoot, `sources-${variant.theme}-${variant.dir}-1440x900.png`),
      animations: 'disabled',
    })
  }

  expect(audit.externalRequests, 'No request may leave the isolated local browser environment').toEqual([])
  expect(audit.unhandledApiRequests, 'Every Sources API request must be explicitly mocked').toEqual([])
})
