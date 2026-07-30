import path from 'node:path'
import { mkdirSync } from 'node:fs'
import { expect, test, type Page, type Route } from '@playwright/test'

// Visual + structural audit of the Figma Screen/RateLimits hierarchy: the
// shared Settings sub-navigation (General / Users / Rate Limits / Advanced)
// alongside a 3-card capacity summary row and an "Operational limits" card
// with paired read/write RPM steppers and a disabled "Rolling window"
// reset-policy select. Figma's own illustrative card labels ("API requests",
// "Order sync jobs", "Source refreshes") and its "Concurrent jobs" field
// have no corresponding real, frontend-reachable backend data or endpoint
// (confirmed by reading RateLimitService.diagnostics(), the /rate-limits
// route contract, and every runtime_config key -- none expose a job
// concurrency limit via any API) and are intentionally not reproduced;
// this spec asserts the real Requests completed/delayed and Queue length
// metrics plus the real read/write RPM fields instead. Captures 1440x900
// evidence for Light/Dark and LTR/RTL. All network traffic is mocked
// inside this spec; nothing leaves the isolated browser.

const screenshotRoot = path.resolve('..', 'docs', 'screenshots', 'v1.3', 'rate-limits-screen')
mkdirSync(screenshotRoot, { recursive: true })

interface TrafficAudit {
  externalRequests: string[]
  unhandledApiRequests: string[]
}

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({ status, contentType: 'application/json; charset=utf-8', body: JSON.stringify(body) })
}

async function installRateLimitsMocks(page: Page, audit: TrafficAudit) {
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
    if (url.pathname === '/api/health' && method === 'GET') return json(route, { status: 'ok', env: 'test', version: 'rate-limits-visual-mock' })
    if (url.pathname === '/api/v2/exchange-rates/me' && method === 'GET') return json(route, { selections: [], rates: [] })
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
      return json(route, { rateLimiter: { requests_completed: 542, requests_delayed: 6, queue_length: 3 } })
    }

    audit.unhandledApiRequests.push(`${method} ${url.pathname}${url.search}`)
    return json(route, { code: 'UNHANDLED_TEST_REQUEST' }, 500)
  })
}

async function seedSession(page: Page, locale: 'en' | 'fa', theme: 'light' | 'dark') {
  await page.addInitScript(([selectedLocale, selectedTheme]) => {
    localStorage.setItem('wp_token', 'rate-limits-visual-isolated-token')
    localStorage.setItem('flowhub.locale', selectedLocale)
    localStorage.setItem('wp_theme', selectedTheme)
  }, [locale, theme])
}

async function assertFigmaRateLimitsHierarchy(page: Page, locale: 'en' | 'fa') {
  const heading = locale === 'en' ? 'Rate Limits' : 'محدودیت نرخ'
  await expect(page.getByRole('heading', { name: heading, level: 1 })).toBeVisible()

  if (locale === 'en') {
    const nav = page.getByRole('navigation', { name: 'Settings' })
    await expect(nav.getByText('Rate Limits', { exact: true })).toBeVisible()

    await expect(page.getByText('Monitor and adjust operational capacity.')).toBeVisible()
    await expect(page.getByText('Requests completed')).toBeVisible()
    await expect(page.getByText('Requests delayed')).toBeVisible()
    await expect(page.getByText('Queue length')).toBeVisible()
    await expect(page.getByText('542')).toBeVisible()

    await expect(page.getByText('Operational limits')).toBeVisible()
    await expect(page.getByText('Adjust only when sustained usage requires more capacity.')).toBeVisible()
    await expect(page.getByText('Read requests per minute')).toBeVisible()
    await expect(page.getByText('Write requests per minute')).toBeVisible()
    await expect(page.getByText('Limit reset policy')).toBeVisible()
    await expect(page.locator('select[disabled] option[value="rolling"]')).toHaveText('Rolling window')
    await expect(page.getByRole('button', { name: 'Save limits' })).toBeVisible()

    // No fabricated "Concurrent jobs" field -- no real backing exists for it.
    await expect(page.getByText('Concurrent jobs')).toHaveCount(0)
  } else {
    await expect(page.getByText('ظرفیت عملیاتی را پایش و تنظیم کنید.')).toBeVisible()
    await expect(page.getByText('محدودیت‌های عملیاتی')).toBeVisible()
  }
}

test('rate limits matches the approved Figma hierarchy in Light/Dark and LTR/RTL at 1440x900', async ({ page }) => {
  test.setTimeout(180_000)
  const audit: TrafficAudit = { externalRequests: [], unhandledApiRequests: [] }
  await installRateLimitsMocks(page, audit)
  await page.setViewportSize({ width: 1440, height: 900 })

  const variants = [
    { locale: 'en', theme: 'light', dir: 'ltr' },
    { locale: 'en', theme: 'dark', dir: 'ltr' },
    { locale: 'fa', theme: 'light', dir: 'rtl' },
    { locale: 'fa', theme: 'dark', dir: 'rtl' },
  ] as const

  for (const variant of variants) {
    await seedSession(page, variant.locale, variant.theme)
    await page.goto('/rate-limits')
    await expect(page.locator('html')).toHaveAttribute('lang', variant.locale)
    await expect(page.locator('html')).toHaveAttribute('dir', variant.dir)
    if (variant.theme === 'dark') {
      await expect(page.locator('html')).toHaveClass(/dark/)
    }
    await assertFigmaRateLimitsHierarchy(page, variant.locale)
    await page.evaluate(() => document.fonts.ready)
    await page.screenshot({
      path: path.join(screenshotRoot, `rate-limits-${variant.theme}-${variant.dir}-1440x900.png`),
      animations: 'disabled',
    })
  }

  expect(audit.externalRequests, 'No request may leave the isolated local browser environment').toEqual([])
  expect(audit.unhandledApiRequests, 'Every Rate Limits API request must be explicitly mocked').toEqual([])
})
