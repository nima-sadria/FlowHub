import path from 'node:path'
import { mkdirSync } from 'node:fs'
import { expect, test, type Page, type Route } from '@playwright/test'

const screenshotRoot = path.resolve('test-results', 'settings-navigation-conformance')
mkdirSync(screenshotRoot, { recursive: true })

interface TrafficAudit {
  consoleErrors: string[]
  failedRequests: string[]
  unhandledApiRequests: string[]
}

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({ status, contentType: 'application/json; charset=utf-8', body: JSON.stringify(body) })
}

async function installMocks(page: Page, audit: TrafficAudit) {
  page.on('console', message => {
    if (message.type() === 'error') audit.consoleErrors.push(message.text())
  })
  page.on('requestfailed', request => {
    const reason = request.failure()?.errorText ?? ''
    if (reason !== 'net::ERR_ABORTED') {
      audit.failedRequests.push(`${request.method()} ${request.url()} ${reason}`)
    }
  })

  await page.addInitScript(() => {
    const query = new URLSearchParams(window.location.search)
    const locale = query.get('qaLocale')
    const theme = query.get('qaTheme')
    localStorage.setItem('wp_token', 'settings-navigation-conformance-token')
    if (locale) localStorage.setItem('flowhub.locale', locale)
    if (theme) localStorage.setItem('wp_theme', theme)
  })

  await page.route('**/*', async route => {
    const request = route.request()
    const url = new URL(request.url())
    const method = request.method().toUpperCase()

    if (url.hostname !== '127.0.0.1' && url.hostname !== 'localhost') {
      return route.abort('blockedbyclient')
    }
    if (!url.pathname.startsWith('/api/')) return route.continue()

    if (url.pathname === '/api/auth/me' && method === 'GET') {
      return json(route, {
        username: 'nima',
        role: 'owner',
        is_admin: true,
        is_super_admin: true,
        permissions: {
          can_access_site: true,
          can_fetch: true,
          can_view_logs: true,
          can_view_settings: true,
          can_manage_sources: true,
          can_read_audit: true,
        },
        maintenance: { enabled: false, message: '' },
      })
    }
    if (url.pathname === '/api/v2/setup/status' && method === 'GET') return json(route, { completed: true })
    if (url.pathname === '/api/health' && method === 'GET') return json(route, { status: 'ok' })
    if (url.pathname === '/api/v2/exchange-rates/me' && method === 'GET') {
      return json(route, {
        selections: ['usd_sell', 'eur', 'aed_sell'],
        rates: [
          { provider: 'navasan', external_symbol: 'usd_sell', canonical_code: 'USD_TEHRAN_SELL', display_name: 'USD Sell', display_name_fa: 'دلار', classification: 'market', side: 'sell', unit: 'IRR', position: 0, value: '935000', change: '1', provider_timestamp: null, fetched_at: null, status: 'fresh', snapshot_id: '1' },
          { provider: 'navasan', external_symbol: 'eur', canonical_code: 'EUR_MARKET', display_name: 'EUR', display_name_fa: 'یورو', classification: 'market', side: null, unit: 'IRR', position: 1, value: '1080000', change: '-1', provider_timestamp: null, fetched_at: null, status: 'fresh', snapshot_id: '2' },
          { provider: 'navasan', external_symbol: 'aed_sell', canonical_code: 'AED_DUBAI_SELL', display_name: 'AED', display_name_fa: 'درهم', classification: 'market', side: 'sell', unit: 'IRR', position: 2, value: '255000', change: null, provider_timestamp: null, fetched_at: null, status: 'fresh', snapshot_id: '3' },
        ],
      })
    }
    if (url.pathname === '/api/v2/settings/rate-limits' && method === 'GET') {
      return json(route, {
        read_requests_per_minute: 60,
        write_requests_per_minute: 30,
        read_delay_ms: 1000,
        write_delay_ms: 2000,
        inherits_to_all_connectors: true,
        per_connector_override_available: false,
        scheduler_started: false,
        automatic_sync: false,
        runtime_write_blocked: true,
      })
    }
    if (url.pathname === '/api/v2/diagnostics/status' && method === 'GET') {
      return json(route, { rateLimiter: { requests_completed: 12, requests_delayed: 0, queue_length: 0 } })
    }

    audit.unhandledApiRequests.push(`${method} ${url.pathname}${url.search}`)
    return json(route, { code: 'UNHANDLED_TEST_REQUEST' }, 500)
  })
}

test('Settings hierarchy, legacy route, responsive spacing, themes, and directions conform', async ({ page }) => {
  test.setTimeout(180_000)
  const audit: TrafficAudit = { consoleErrors: [], failedRequests: [], unhandledApiRequests: [] }
  await installMocks(page, audit)

  const variants = [
    { width: 1440, height: 900, locale: 'en', theme: 'light', dir: 'ltr', padding: 32 },
    { width: 1440, height: 900, locale: 'fa', theme: 'dark', dir: 'rtl', padding: 32 },
    { width: 767, height: 900, locale: 'en', theme: 'dark', dir: 'ltr', padding: 24 },
    { width: 767, height: 900, locale: 'fa', theme: 'light', dir: 'rtl', padding: 24 },
    { width: 390, height: 844, locale: 'en', theme: 'light', dir: 'ltr', padding: 20 },
    { width: 390, height: 844, locale: 'fa', theme: 'dark', dir: 'rtl', padding: 20 },
  ] as const

  for (const variant of variants) {
    await page.setViewportSize({ width: variant.width, height: variant.height })
    await page.goto(`/settings/rate-limits?qaLocale=${variant.locale}&qaTheme=${variant.theme}`)
    await expect(page.locator('html')).toHaveAttribute('lang', variant.locale)
    await expect(page.locator('html')).toHaveAttribute('dir', variant.dir)
    if (variant.theme === 'dark') await expect(page.locator('html')).toHaveClass(/dark/)
    else await expect(page.locator('html')).not.toHaveClass(/dark/)

    const topbar = page.locator('.fh-topbar-primary')
    const computedPadding = await topbar.evaluate(element => {
      const style = getComputedStyle(element)
      return { left: Number.parseFloat(style.paddingLeft), right: Number.parseFloat(style.paddingRight) }
    })
    expect(computedPadding.left).toBeGreaterThanOrEqual(variant.padding)
    expect(computedPadding.right).toBeGreaterThanOrEqual(variant.padding)
    const clippedControls = await topbar.evaluate(element => {
      const bounds = element.getBoundingClientRect()
      return Array.from(element.querySelectorAll('button, summary')).flatMap(control => {
        const rect = control.getBoundingClientRect()
        if (rect.width === 0 || rect.height === 0) return []
        return rect.left < bounds.left || rect.right > bounds.right
          ? [{ label: control.getAttribute('aria-label') ?? control.textContent, left: rect.left, right: rect.right, boundsLeft: bounds.left, boundsRight: bounds.right }]
          : []
      })
    })
    expect(clippedControls, `${variant.locale}/${variant.theme}/${variant.width}px controls stay within the header`).toEqual([])

    await page.screenshot({
      path: path.join(
        screenshotRoot,
        `header-${variant.locale}-${variant.theme}-${variant.width}x${variant.height}.png`,
      ),
      animations: 'disabled',
    })

    const parent = page.locator('[aria-controls="sidebar-settings-submenu"]')
    if (variant.width < 768) {
      await page.getByRole('button', { name: variant.locale === 'en' ? 'Open navigation' : 'بازکردن منو' }).click()
    }
    await expect(parent).toHaveAttribute('aria-expanded', 'true')
    await expect(parent).toHaveAttribute('data-active', 'true')
    await expect(page.locator('#sidebar-settings-submenu a')).toHaveCount(5)
    await expect(page.locator('#sidebar-settings-submenu a[aria-current="page"]')).toHaveCount(1)
    await expect(page.locator('#sidebar-settings-submenu a[href="/settings/rate-limits"]')).toHaveAttribute('aria-current', 'page')

    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    await page.screenshot({
      path: path.join(
        screenshotRoot,
        `settings-nav-${variant.locale}-${variant.theme}-${variant.width}x${variant.height}.png`,
      ),
      animations: 'disabled',
    })
  }

  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/rate-limits?view=capacity#limits')
  await expect(page).toHaveURL(/\/settings\/rate-limits\?view=capacity#limits$/)

  await page.goto('/settings/advanced')
  const settingsParent = page.locator('[aria-controls="sidebar-settings-submenu"]')
  await expect(settingsParent).toHaveAttribute('aria-expanded', 'true')
  await settingsParent.click()
  await expect(settingsParent).toHaveAttribute('aria-expanded', 'false')
  await settingsParent.press('Space')
  await expect(settingsParent).toHaveAttribute('aria-expanded', 'true')
  await page.locator('#sidebar-settings-submenu a[href="/settings/rate-limits"]').click()
  await expect(page).toHaveURL('/settings/rate-limits')
  await page.goBack()
  await expect(page).toHaveURL('/settings/advanced')
  await expect(page.locator('#sidebar-settings-submenu a[href="/settings/advanced"]')).toHaveAttribute('aria-current', 'page')
  await page.goForward()
  await expect(page).toHaveURL('/settings/rate-limits')
  await expect(page.locator('#sidebar-settings-submenu a[href="/settings/rate-limits"]')).toHaveAttribute('aria-current', 'page')

  expect(audit.consoleErrors).toEqual([])
  expect(audit.failedRequests).toEqual([])
  expect(audit.unhandledApiRequests).toEqual([])
})
