import path from 'node:path'
import { mkdirSync } from 'node:fs'
import { expect, test, type Page, type Route } from '@playwright/test'

// Visual + structural audit of the Figma Screen/Settings (General tab)
// hierarchy: the shared Settings sub-navigation (General / Users / Rate
// Limits / Advanced) alongside a single "Workspace preferences" card
// (Language / Timezone / Default currency) and a "Localization preview"
// card. No embedded User Management table or Rate Limits panel — those now
// live on their own dedicated pages reachable from the same sub-nav.
// Captures 1440x900 evidence for Light/Dark and LTR/RTL. All network
// traffic is mocked inside this spec; nothing leaves the isolated browser.

const screenshotRoot = path.resolve('..', 'docs', 'screenshots', 'v1.3', 'settings-screen')
mkdirSync(screenshotRoot, { recursive: true })

interface TrafficAudit {
  externalRequests: string[]
  unhandledApiRequests: string[]
}

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({ status, contentType: 'application/json; charset=utf-8', body: JSON.stringify(body) })
}

async function installSettingsMocks(page: Page, audit: TrafficAudit) {
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
        username: 'settings-owner',
        role: 'admin',
        is_admin: true,
        is_super_admin: false,
        permissions: { can_access_site: true, can_fetch: true, can_view_logs: true, can_view_settings: true },
        maintenance: { enabled: false, message: '' },
      })
    }
    if (url.pathname === '/api/v2/setup/status' && method === 'GET') return json(route, { completed: true })
    if (url.pathname === '/api/health' && method === 'GET') return json(route, { status: 'ok', env: 'test', version: 'settings-visual-mock' })
    if (url.pathname === '/api/v2/settings' && method === 'GET') {
      return json(route, {
        woocommerceUrl: '', nextcloudUrl: '', syncIntervalMinutes: 60,
        timezone: 'Asia/Tehran', currency: 'USD', currencyUnit: 'USD', environment: 'production',
      })
    }

    audit.unhandledApiRequests.push(`${method} ${url.pathname}${url.search}`)
    return json(route, { code: 'UNHANDLED_TEST_REQUEST' }, 500)
  })
}

async function seedSession(page: Page, locale: 'en' | 'fa', theme: 'light' | 'dark') {
  await page.addInitScript(([selectedLocale, selectedTheme]) => {
    localStorage.setItem('wp_token', 'settings-visual-isolated-token')
    localStorage.setItem('flowhub.locale', selectedLocale)
    localStorage.setItem('wp_theme', selectedTheme)
  }, [locale, theme])
}

async function assertFigmaSettingsHierarchy(page: Page, locale: 'en' | 'fa') {
  const heading = locale === 'en' ? 'General' : 'عمومی'
  await expect(page.getByRole('heading', { name: heading, level: 1 })).toBeVisible()

  if (locale === 'en') {
    const nav = page.getByRole('navigation', { name: 'Settings' })
    await expect(nav.getByText('General', { exact: true })).toBeVisible()
    await expect(nav.getByText('Users', { exact: true })).toBeVisible()
    await expect(nav.getByText('Rate Limits', { exact: true })).toBeVisible()
    await expect(nav.getByText('Advanced')).toBeVisible()

    await expect(page.getByText('Workspace preferences')).toBeVisible()
    await expect(page.getByText('Regional defaults used across seller workflows.')).toBeVisible()
    await expect(page.getByText('Language', { exact: true })).toBeVisible()
    await expect(page.getByText('Timezone', { exact: true })).toBeVisible()
    await expect(page.getByText('Default currency')).toBeVisible()
    const currencySelect = page.locator('select').filter({ has: page.locator('option[value="USD"]') })
    await expect(currencySelect.locator('option[value="USD"]')).toHaveText('USD — US Dollar')
    await expect(currencySelect).toHaveValue('USD')

    await expect(page.getByText('Localization preview')).toBeVisible()
    await expect(page.getByText('English · USD · Asia/Tehran')).toBeVisible()
    await expect(page.getByText('Ready')).toBeVisible()
  } else {
    await expect(page.getByText('تنظیمات فضای کاری')).toBeVisible()
    const currencySelect = page.locator('select').filter({ has: page.locator('option[value="USD"]') })
    await expect(currencySelect.locator('option[value="USD"]')).toHaveText('USD — دلار آمریکا')
  }
}

test('settings matches the approved Figma hierarchy in Light/Dark and LTR/RTL at 1440x900', async ({ page }) => {
  test.setTimeout(180_000)
  const audit: TrafficAudit = { externalRequests: [], unhandledApiRequests: [] }
  await installSettingsMocks(page, audit)
  await page.setViewportSize({ width: 1440, height: 900 })

  const variants = [
    { locale: 'en', theme: 'light', dir: 'ltr' },
    { locale: 'en', theme: 'dark', dir: 'ltr' },
    { locale: 'fa', theme: 'light', dir: 'rtl' },
    { locale: 'fa', theme: 'dark', dir: 'rtl' },
  ] as const

  for (const variant of variants) {
    await seedSession(page, variant.locale, variant.theme)
    await page.goto('/settings')
    await expect(page.locator('html')).toHaveAttribute('lang', variant.locale)
    await expect(page.locator('html')).toHaveAttribute('dir', variant.dir)
    if (variant.theme === 'dark') {
      await expect(page.locator('html')).toHaveClass(/dark/)
    }
    await expect(page.getByRole('navigation', { name: variant.locale === 'en' ? 'Settings' : 'تنظیمات' })).toBeVisible()
    await assertFigmaSettingsHierarchy(page, variant.locale)
    await page.evaluate(() => document.fonts.ready)
    await page.screenshot({
      path: path.join(screenshotRoot, `settings-${variant.theme}-${variant.dir}-1440x900.png`),
      animations: 'disabled',
    })
  }

  expect(audit.externalRequests, 'No request may leave the isolated local browser environment').toEqual([])
  expect(audit.unhandledApiRequests, 'Every Settings API request must be explicitly mocked').toEqual([])
})
