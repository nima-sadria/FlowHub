import { expect, test, type Page, type Route } from '@playwright/test'

interface TrafficAudit {
  externalRequests: string[]
  unhandledApiRequests: string[]
  writes: string[]
  configurationRequests: string[]
}

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({
    status,
    contentType: 'application/json; charset=utf-8',
    body: JSON.stringify(body),
  })
}

const healthyChannel = {
  id: 'woocommerce:primary',
  provider: 'woocommerce',
  name: 'WooCommerce',
  type: 'Channel',
  status: 'active',
  implemented: true,
  placeholder: false,
  enabled: true,
  read_only: false,
  write_blocked: false,
  runtime_write_blocked: false,
  credential_status: 'configured',
  configuration_state: 'configured',
  last_health_check: '2026-08-13T08:00:00Z',
  health: { status: 'healthy', message: '', latency_ms: 40, error_code: null },
  capabilities: {},
  capabilities_summary: [],
  settings_available: true,
  cached_products: 12,
  cached_variations: 0,
  last_cache_refresh: '2026-08-13T07:58:00Z',
  cache_refresh_status: 'completed',
}

const disabledChannel = {
  ...healthyChannel,
  id: 'technolife:disabled',
  provider: 'technolife',
  name: 'Technolife Disabled',
  status: 'disabled',
  enabled: false,
}

const comingSoonChannel = {
  ...healthyChannel,
  id: 'digikala:main',
  provider: 'digikala',
  name: 'Digikala',
  status: 'coming_soon',
  implemented: true,
  placeholder: true,
  enabled: false,
  read_only: true,
  write_blocked: true,
  runtime_write_blocked: true,
  credential_status: 'not_configured',
  configuration_state: 'coming_soon',
  health: { status: 'unknown', message: '', latency_ms: null, error_code: null },
  settings_available: false,
  cached_products: 0,
  last_cache_refresh: null,
  cache_refresh_status: 'not_available',
}

async function installChannelsMocks(page: Page, audit: TrafficAudit) {
  await page.addInitScript(() => {
    localStorage.setItem('wp_token', 'channels-semantics-isolated-token')
    localStorage.setItem('flowhub.locale', 'en')
  })

  await page.route('**/*', async route => {
    const request = route.request()
    const url = new URL(request.url())
    const method = request.method().toUpperCase()

    if (!['127.0.0.1', 'localhost'].includes(url.hostname)) {
      audit.externalRequests.push(`${method} ${url.href}`)
      return route.abort('blockedbyclient')
    }
    if (url.pathname.startsWith('/static/logos/')) return route.fulfill({ status: 204 })
    if (!url.pathname.startsWith('/api/')) return route.continue()

    if (url.pathname.includes('/configuration')) audit.configurationRequests.push(`${method} ${url.pathname}`)
    if (method !== 'GET') {
      audit.writes.push(`${method} ${url.pathname}`)
      return json(route, { code: 'MOCK_WRITE_BLOCKED' }, 405)
    }

    if (url.pathname === '/api/auth/me') {
      return json(route, {
        username: 'channels-owner',
        role: 'admin',
        is_admin: true,
        is_super_admin: false,
        permissions: { can_access_site: true, can_fetch: true, can_view_logs: true, can_view_settings: true },
        maintenance: { enabled: false, message: '' },
      })
    }
    if (url.pathname === '/api/v2/setup/status') return json(route, { completed: true })
    if (url.pathname === '/api/health') return json(route, { status: 'ok', env: 'test', version: 'channels-semantics-mock' })
    if (url.pathname === '/api/v2/exchange-rates/me') return json(route, { selections: [], rates: [] })
    if (url.pathname === '/api/v2/commerce/channels') {
      return json(route, { items: [healthyChannel, disabledChannel, comingSoonChannel] })
    }
    if (url.pathname === '/api/v2/orders') return json(route, { items: [], total: 0, page: 1, pageSize: 1 })
    if (url.pathname === '/api/v2/commerce/channel-types') {
      return json(route, {
        items: [
          { ...healthyChannel, settings_schema: [] },
          { ...disabledChannel, settings_schema: [] },
          { ...comingSoonChannel, availability: 'coming_soon', settings_schema: [] },
        ],
      })
    }

    audit.unhandledApiRequests.push(`${method} ${url.pathname}${url.search}`)
    return json(route, { code: 'UNHANDLED_TEST_REQUEST' }, 500)
  })
}

test('Channels keeps Digikala visible as non-actionable Coming Soon and labels disabled channels truthfully', async ({ page }) => {
  const audit: TrafficAudit = {
    externalRequests: [],
    unhandledApiRequests: [],
    writes: [],
    configurationRequests: [],
  }
  await installChannelsMocks(page, audit)

  await page.goto('/channels')
  await expect(page.locator('.fh-channels-grid').first()).toBeVisible()

  const disabledCard = page.locator('[data-channel-card="technolife:disabled"]')
  await expect(disabledCard).toHaveAttribute('data-resource-state', 'disabled')
  await expect(disabledCard.getByText('Disabled', { exact: true })).toBeVisible()
  await expect(disabledCard.getByText('Setup required', { exact: true })).toHaveCount(0)
  await expect(disabledCard.getByRole('button', { name: 'Test Connection' })).toHaveCount(0)
  await expect(disabledCard.getByRole('button', { name: 'Refresh cache' })).toHaveCount(0)

  const digikalaCard = page.locator('[data-channel-card="digikala:main"]')
  await expect(digikalaCard).toHaveAttribute('data-resource-state', 'comingSoon')
  await expect(digikalaCard).toHaveAttribute('aria-disabled', 'true')
  await expect(digikalaCard.getByText('Coming Soon', { exact: true })).toBeVisible()
  await expect(digikalaCard.getByRole('button')).toHaveCount(0)

  await page.goto('/channels?setup=digikala%3Amain')
  const notice = page.getByTestId('channel-coming-soon-notice')
  await expect(notice).toBeVisible()
  await expect(notice.getByRole('heading', { name: 'Coming Soon' })).toBeVisible()
  await expect(notice.getByRole('button', { name: 'Channel API documentation' })).toBeVisible()
  await expect(page.getByTestId('channel-configuration-dialog').locator('input')).toHaveCount(0)

  expect(audit.configurationRequests).toEqual([])
  expect(audit.writes).toEqual([])
  expect(audit.externalRequests).toEqual([])
  expect(audit.unhandledApiRequests).toEqual([])
})
