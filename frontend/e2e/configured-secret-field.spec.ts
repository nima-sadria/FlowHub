import { expect, test, type Page, type Route } from '@playwright/test'

const sourceId = 'nextcloud:primary'
const storedSecretSentinel = 'server-secret-must-never-reach-the-browser'
const settingsSchema = [
  { key: 'url', label: 'Nextcloud URL', required: true, secret: false },
  { key: 'username', label: 'Username', required: true, secret: false },
  { key: 'password', label: 'Password', required: true, secret: true },
  { key: 'spreadsheet_path', label: 'Spreadsheet path', required: true, secret: false },
]

interface TrafficAudit {
  externalRequests: string[]
  unhandledApiRequests: string[]
  writes: string[]
}

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({
    status,
    contentType: 'application/json; charset=utf-8',
    body: JSON.stringify(body),
  })
}

async function installConfiguredSourceMocks(page: Page, audit: TrafficAudit) {
  await page.addInitScript(() => {
    localStorage.setItem('wp_token', 'configured-secret-isolated-token')
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
    if (method !== 'GET') {
      audit.writes.push(`${method} ${url.pathname}`)
      return json(route, { code: 'MOCK_WRITE_BLOCKED' }, 405)
    }

    if (url.pathname === '/api/v2/setup/status') return json(route, { completed: true })
    if (url.pathname === '/api/auth/me') return json(route, {
      username: 'source-owner',
      role: 'admin',
      is_admin: true,
      is_super_admin: false,
      permissions: {
        can_access_site: true,
        can_fetch: true,
        can_view_logs: true,
        can_view_settings: true,
        'workspace.admin': true,
      },
      maintenance: { enabled: false, message: '' },
    })
    if (url.pathname === '/api/health') return json(route, { status: 'ok', env: 'test', version: 'configured-secret-mock' })
    if (url.pathname === '/api/v2/exchange-rates/me') return json(route, { selections: [], rates: [] })
    if (url.pathname === '/api/v2/commerce/sources') return json(route, {
      items: [{
        id: sourceId,
        provider: 'nextcloud',
        name: 'Nextcloud',
        type: 'Source',
        status: 'configured',
        implemented: true,
        placeholder: false,
        credential_status: 'configured',
        connection_configured: true,
        configuration_state: 'configured',
        last_health_check: '2026-08-11T16:00:00Z',
        data_role: 'Spreadsheet price input',
        action_label: 'Manage',
        action_href: '/commerce?tab=sources',
        health: { status: 'healthy', message: 'Connection successful.', latency_ms: 25, error_code: null },
        read_only: true,
        runtime_write_blocked: true,
        settings_available: true,
      }],
      relationship_map: {
        nodes: ['Source', 'FlowHub / Data Layer', 'Channel'],
        example: ['Nextcloud', 'Data Layer', 'WooCommerce'],
        runtime_write_blocked: true,
        read_only: true,
      },
    })
    if (url.pathname === '/api/v2/commerce/channels') return json(route, { items: [] })
    if (url.pathname === '/api/v2/commerce/source-types') return json(route, {
      items: [{
        id: sourceId,
        provider: 'nextcloud',
        name: 'Nextcloud',
        type: 'Source',
        implemented: true,
        placeholder: false,
        read_only: true,
        write_blocked: true,
        runtime_write_blocked: true,
        settings_schema: settingsSchema,
      }],
    })
    if (url.pathname === '/api/v2/commerce/channel-types') return json(route, { items: [] })
    if (decodeURIComponent(url.pathname) === `/api/v2/commerce/sources/${sourceId}/configuration`) {
      return json(route, {
        source_id: sourceId,
        provider: 'nextcloud',
        display_name: 'Nextcloud',
        description: 'Owner workbook',
        configured: true,
        connection_configured: true,
        configuration_state: 'configured',
        last_test: {
          status: 'healthy',
          message: 'Connection successful.',
          error_code: null,
          latency_ms: 25,
          checked_at: '2026-08-11T16:00:00Z',
        },
        enabled: true,
        access_mode: 'read_only',
        settings: {
          url: 'https://nextcloud.example.test',
          username: 'owner',
          spreadsheet_path: '/Reports/prices.xlsx',
          worksheet_mode: 'selected',
          worksheet_name: 'Prices',
        },
        secrets: { password: { status: 'configured', replaced_at: '2026-08-11T15:00:00Z' } },
        settings_schema: settingsSchema,
        credentials_returned: false,
        currency_profile: { status: 'resolved', currency: 'IRR', unit: 'RIAL' },
      })
    }

    audit.unhandledApiRequests.push(`${method} ${url.pathname}${url.search}`)
    return json(route, { code: 'UNHANDLED_TEST_REQUEST' }, 501)
  })
}

test('configured Source secret controls explain and enforce their local-draft-only behavior', async ({ page, context }) => {
  const audit: TrafficAudit = { externalRequests: [], unhandledApiRequests: [], writes: [] }
  await context.grantPermissions(['clipboard-read', 'clipboard-write'], { origin: 'http://127.0.0.1:4188' })
  await installConfiguredSourceMocks(page, audit)

  await page.goto(`/commerce?tab=sources&resource=${encodeURIComponent(sourceId)}`)

  const input = page.locator('input[autocomplete="new-password"]').first()
  const mask = page.getByTestId('configured-secret-mask')
  const reveal = page.getByRole('button', { name: 'Show entered secret' })
  const copy = page.getByRole('button', { name: 'Copy entered secret' })
  const emptyHint = 'Saved secret is hidden for security — type a new one to reveal or copy it.'

  await expect(input).toHaveValue('')
  await expect(mask).toHaveText('••••••••••••')
  await expect(reveal).toBeDisabled()
  await expect(copy).toBeDisabled()
  await expect(reveal).toHaveAttribute('title', emptyHint)
  await expect(copy).toHaveAttribute('title', emptyHint)
  await expect(reveal).toHaveCSS('opacity', '0.45')
  await expect(copy).toHaveCSS('cursor', 'not-allowed')
  await expect(page.getByText('Saved credential ✓ — leave blank to keep unchanged.')).toBeVisible()
  await expect(page.locator('body')).not.toContainText(storedSecretSentinel)

  await input.focus()
  await expect(mask).toBeHidden()
  await expect(input).toHaveAttribute('placeholder', 'Type your password')

  await input.fill('abc')
  await expect(reveal).toBeEnabled()
  await expect(copy).toBeEnabled()
  await expect(reveal).toHaveCSS('opacity', '1')
  await expect(reveal).toHaveAttribute('title', 'Show entered secret')
  await expect(copy).toHaveAttribute('title', 'Copy entered secret')

  await reveal.click()
  await expect(input).toHaveAttribute('type', 'text')
  await expect(page.getByRole('button', { name: 'Hide entered secret' })).toHaveAttribute('title', 'Hide entered secret')

  await copy.click()
  await expect(page.getByText('Entered secret copied.')).toBeVisible()
  await expect.poll(() => page.evaluate(() => navigator.clipboard.readText())).toBe('abc')

  await input.fill('')
  await expect(input).toHaveAttribute('type', 'password')
  await expect(page.getByRole('button', { name: 'Show entered secret' })).toBeDisabled()
  await expect(copy).toBeDisabled()
  await input.blur()
  await expect(mask).toBeVisible()

  expect(audit.externalRequests).toEqual([])
  expect(audit.unhandledApiRequests).toEqual([])
  expect(audit.writes).toEqual([])
})
