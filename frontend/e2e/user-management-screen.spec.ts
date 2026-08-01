import path from 'node:path'
import { mkdirSync } from 'node:fs'
import { expect, test, type Page, type Route } from '@playwright/test'

// Visual + structural audit of the Figma Screen/UserManagement (Users tab)
// hierarchy: the shared Settings sub-navigation (General / Exchange Rates /
// Users / Rate Limits / Advanced Settings) alongside a single "Users and roles" card listing
// accounts as borderless rows (name + created date, role, status dot, a
// single Edit action) — no table headers, no always-visible per-row
// controls. Edit consolidates role/status/password/activity/delete behind
// one dialog, since Figma shows no dedicated destination for that action
// and the underlying capabilities are all real, already-shipped endpoints.
// Captures 1440x900 evidence for Light/Dark and LTR/RTL. All network
// traffic is mocked inside this spec; nothing leaves the isolated browser.

const screenshotRoot = path.resolve('..', 'docs', 'screenshots', 'v1.3', 'user-management-screen')
mkdirSync(screenshotRoot, { recursive: true })

interface TrafficAudit {
  externalRequests: string[]
  unhandledApiRequests: string[]
}

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({ status, contentType: 'application/json; charset=utf-8', body: JSON.stringify(body) })
}

const USERS = [
  { id: 1, username: 'nima', role: 'owner', is_active: true, created_at: '2025-11-03T00:00:00Z', is_admin: true, is_super_admin: true },
  { id: 2, username: 'sara', role: 'admin', is_active: true, created_at: '2025-12-10T00:00:00Z', is_admin: true, is_super_admin: false },
  { id: 3, username: 'omid', role: 'operator', is_active: false, created_at: '2026-01-15T00:00:00Z', is_admin: false, is_super_admin: false },
]

async function installUserManagementMocks(page: Page, audit: TrafficAudit) {
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
        username: 'nima',
        role: 'owner',
        is_admin: true,
        is_super_admin: true,
        permissions: { can_access_site: true, can_fetch: true, can_view_logs: true, can_view_settings: true },
        maintenance: { enabled: false, message: '' },
      })
    }
    if (url.pathname === '/api/v2/setup/status' && method === 'GET') return json(route, { completed: true })
    if (url.pathname === '/api/health' && method === 'GET') return json(route, { status: 'ok', env: 'test', version: 'user-management-visual-mock' })
    if (url.pathname === '/api/v2/exchange-rates/me' && method === 'GET') return json(route, { selections: [], rates: [] })
    if (url.pathname === '/api/v2/users' && method === 'GET') return json(route, { items: USERS, total: USERS.length })

    audit.unhandledApiRequests.push(`${method} ${url.pathname}${url.search}`)
    return json(route, { code: 'UNHANDLED_TEST_REQUEST' }, 500)
  })
}

async function seedSession(page: Page, locale: 'en' | 'fa', theme: 'light' | 'dark') {
  await page.addInitScript(([selectedLocale, selectedTheme]) => {
    localStorage.setItem('wp_token', 'user-management-visual-isolated-token')
    localStorage.setItem('flowhub.locale', selectedLocale)
    localStorage.setItem('wp_theme', selectedTheme)
  }, [locale, theme])
}

async function assertFigmaUserManagementHierarchy(page: Page, locale: 'en' | 'fa') {
  const heading = locale === 'en' ? 'User Management' : 'مدیریت کاربران'
  await expect(page.getByRole('heading', { name: heading, level: 1 })).toBeVisible()

  if (locale === 'en') {
    const nav = page.getByRole('navigation', { name: 'Settings' })
    await expect(nav.getByText('Users', { exact: true })).toBeVisible()
    await expect(nav.getByText('Rate Limits', { exact: true })).toBeVisible()

    await expect(page.getByText('Accounts, roles, and permissions.')).toBeVisible()
    await expect(page.getByText('Users and roles')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Create user' })).toBeVisible()

    await expect(page.getByText('sara')).toBeVisible()
    await expect(page.getByText('Admin', { exact: true })).toBeVisible()
    await expect(page.getByText('Operator', { exact: true })).toBeVisible()
    await expect(page.getByText('Active').first()).toBeVisible()
    await expect(page.getByText('Disabled')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Edit' }).first()).toBeVisible()

    // No column headers, no always-visible inline role/status controls.
    await expect(page.locator('table')).toHaveCount(0)
    await expect(page.getByRole('button', { name: /^Disable$/ })).toHaveCount(0)
  } else {
    await expect(page.getByText('کاربران و نقش‌ها')).toBeVisible()
    await expect(page.getByText('حساب‌ها، نقش‌ها و دسترسی‌ها.')).toBeVisible()
  }
}

test('user management matches the approved Figma hierarchy in Light/Dark and LTR/RTL at 1440x900', async ({ page }) => {
  test.setTimeout(180_000)
  const audit: TrafficAudit = { externalRequests: [], unhandledApiRequests: [] }
  await installUserManagementMocks(page, audit)
  await page.setViewportSize({ width: 1440, height: 900 })

  const variants = [
    { locale: 'en', theme: 'light', dir: 'ltr' },
    { locale: 'en', theme: 'dark', dir: 'ltr' },
    { locale: 'fa', theme: 'light', dir: 'rtl' },
    { locale: 'fa', theme: 'dark', dir: 'rtl' },
  ] as const

  for (const variant of variants) {
    await seedSession(page, variant.locale, variant.theme)
    await page.goto('/settings/users')
    await expect(page.locator('html')).toHaveAttribute('lang', variant.locale)
    await expect(page.locator('html')).toHaveAttribute('dir', variant.dir)
    if (variant.theme === 'dark') {
      await expect(page.locator('html')).toHaveClass(/dark/)
    }
    await assertFigmaUserManagementHierarchy(page, variant.locale)
    await page.evaluate(() => document.fonts.ready)
    await page.screenshot({
      path: path.join(screenshotRoot, `user-management-${variant.theme}-${variant.dir}-1440x900.png`),
      animations: 'disabled',
    })
  }

  expect(audit.externalRequests, 'No request may leave the isolated local browser environment').toEqual([])
  expect(audit.unhandledApiRequests, 'Every User Management API request must be explicitly mocked').toEqual([])
})
