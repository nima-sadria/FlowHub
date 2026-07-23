import { expect, test, type Page, type Route } from '@playwright/test'

interface TrafficAudit {
  externalRequests: string[]
  unhandledApiRequests: string[]
}

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({
    status,
    contentType: 'application/json; charset=utf-8',
    body: JSON.stringify(body),
  })
}

async function installMocks(page: Page, audit: TrafficAudit) {
  await page.route('**/*', async route => {
    const request = route.request()
    const url = new URL(request.url())
    const method = request.method().toUpperCase()

    if (url.hostname !== '127.0.0.1' && url.hostname !== 'localhost') {
      audit.externalRequests.push(`${method} ${url.href}`)
      return route.abort('blockedbyclient')
    }
    if (url.pathname.startsWith('/static/logos/')) {
      return route.fulfill({ status: 200, contentType: 'image/png', body: '' })
    }
    if (!url.pathname.startsWith('/api/')) return route.continue()

    if (url.pathname === '/api/auth/me' && method === 'GET') {
      return json(route, {
        username: 'owner',
        role: 'owner',
        is_admin: true,
        is_super_admin: true,
        permissions: {
          can_access_site: true,
          can_fetch: true,
          can_view_logs: true,
          can_view_settings: true,
        },
        maintenance: { enabled: false, message: '' },
      })
    }
    if (url.pathname === '/api/v2/setup/status' && method === 'GET') {
      return json(route, { completed: true })
    }
    if (url.pathname === '/api/health' && method === 'GET') {
      return json(route, { status: 'ok', env: 'test', version: 'forward-port-e2e' })
    }
    if (url.pathname === '/api/v2/settings' && method === 'GET') {
      return json(route, {
        woocommerceUrl: '',
        nextcloudUrl: '',
        syncIntervalMinutes: 60,
        timezone: 'Asia/Tehran',
        currency: 'USD',
        currencyUnit: 'USD',
        environment: 'production',
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
      return json(route, {
        rateLimiter: {
          requests_completed: 542,
          requests_delayed: 6,
          queue_length: 3,
        },
      })
    }
    if (url.pathname === '/api/v2/users' && method === 'GET') {
      return json(route, {
        items: [{
          id: 1,
          username: 'owner',
          role: 'owner',
          is_active: true,
          created_at: '2026-07-23T00:00:00Z',
          is_admin: true,
          is_super_admin: true,
        }],
        total: 1,
      })
    }

    audit.unhandledApiRequests.push(`${method} ${url.pathname}${url.search}`)
    return json(route, { code: 'UNHANDLED_TEST_REQUEST' }, 500)
  })
}

async function setDisplay(page: Page, locale: 'en' | 'fa', theme: 'light' | 'dark') {
  await page.evaluate(([selectedLocale, selectedTheme]) => {
    localStorage.removeItem('wp_token')
    localStorage.setItem('flowhub.locale', selectedLocale)
    localStorage.setItem('wp_theme', selectedTheme)
  }, [locale, theme])
  await page.reload()
}

test('preserves the current Login contract across theme and direction variants', async ({ page }) => {
  const audit: TrafficAudit = { externalRequests: [], unhandledApiRequests: [] }
  await installMocks(page, audit)
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/login')

  const variants = [
    { locale: 'en', theme: 'light', dir: 'ltr' },
    { locale: 'en', theme: 'dark', dir: 'ltr' },
    { locale: 'fa', theme: 'light', dir: 'rtl' },
    { locale: 'fa', theme: 'dark', dir: 'rtl' },
  ] as const

  for (const variant of variants) {
    await setDisplay(page, variant.locale, variant.theme)
    await expect(page.locator('html')).toHaveAttribute('lang', variant.locale)
    await expect(page.locator('html')).toHaveAttribute('dir', variant.dir)
    await expect(page.locator('html')).toHaveClass(
      variant.theme === 'dark' ? /dark/ : /^(?!.*dark).*$/,
    )

    const heading = variant.locale === 'en' ? 'Sign in to FlowHub' : 'ورود به FlowHub'
    await expect(page.getByRole('heading', { name: heading, level: 1 })).toBeVisible()
    await expect(page.locator('label[for="login-identifier"]')).toHaveText(
      variant.locale === 'en' ? 'Username' : 'نام کاربری',
    )
    await expect(page.locator('label[for="login-password"]')).toBeVisible()
    await expect(page.locator('input[type="checkbox"]')).toHaveCount(0)
    await expect(page.getByText('Forgot password?')).toHaveCount(0)
    await expect(page.getByText('Continue with SSO')).toHaveCount(0)
  }

  expect(audit.externalRequests).toEqual([])
  expect(audit.unhandledApiRequests).toEqual([])
})

test('preserves remediated rate-limit delay labels in advanced settings', async ({ page }) => {
  const audit: TrafficAudit = { externalRequests: [], unhandledApiRequests: [] }
  await installMocks(page, audit)
  await page.addInitScript(() => {
    localStorage.setItem('wp_token', 'forward-port-isolated-token')
    localStorage.setItem('flowhub.locale', 'en')
    localStorage.setItem('wp_theme', 'light')
  })

  await page.goto('/settings')
  await expect(page.getByRole('heading', { name: 'Settings', level: 1 })).toBeVisible()
  await page.getByText('Advanced', { exact: true }).click()

  await expect(page.getByRole('heading', { name: 'Global API Rate Limits' })).toBeVisible()
  await expect(page.getByText('Read delay')).toBeVisible()
  await expect(page.getByText('1.00 seconds')).toBeVisible()
  await expect(page.getByText('Write delay')).toBeVisible()
  await expect(page.getByText('2.00 seconds')).toBeVisible()

  expect(audit.externalRequests).toEqual([])
  expect(audit.unhandledApiRequests).toEqual([])
})
