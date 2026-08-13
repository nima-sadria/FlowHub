import { expect, test, type Page, type Route } from '@playwright/test'

const sourceId = 'nextcloud:primary'
const managedSourceId = 'managed-nextcloud-source'

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
  savedPayloads: unknown[]
}

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({
    status,
    contentType: 'application/json; charset=utf-8',
    body: JSON.stringify(body),
  })
}

async function installNextcloudSourceMocks(
  page: Page,
  audit: TrafficAudit,
  options: { enabled: boolean; allowSave?: boolean },
) {
  await page.addInitScript(() => {
    localStorage.setItem('wp_token', 'nextcloud-source-semantics-isolated-token')
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
    if (
      options.allowSave
      && method === 'PUT'
      && decodeURIComponent(url.pathname) === `/api/v2/commerce/sources/${sourceId}/settings`
    ) {
      audit.writes.push(`${method} ${decodeURIComponent(url.pathname)}`)
      audit.savedPayloads.push(request.postDataJSON())
      return json(route, {
        settings: {
          url: 'https://nextcloud.example.test', username: 'owner', spreadsheet_path: '/Reports/prices.xlsx',
          worksheet_mode: 'selected', worksheet_name: 'Prices',
        },
        secrets: { password: { status: 'configured', replaced_at: '2026-08-13T07:00:00Z' } },
        configured: true,
        connection_configured: true,
        configuration_state: 'configured',
        read_only: true,
        runtime_write_blocked: true,
        write_blocked: true,
      })
    }
    if (method !== 'GET') {
      audit.writes.push(`${method} ${url.pathname}`)
      return json(route, { code: 'MOCK_WRITE_BLOCKED' }, 405)
    }

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
    if (url.pathname === '/api/v2/setup/status') return json(route, { completed: true })
    if (url.pathname === '/api/health') return json(route, { status: 'ok', env: 'test', version: 'nextcloud-source-semantics-mock' })
    if (url.pathname === '/api/v2/exchange-rates/me') return json(route, { selections: [], rates: [] })
    if (url.pathname === '/api/v2/source-profiles') return json(route, { items: [{
      id: managedSourceId,
      name: 'Nextcloud Data Sheet',
      sourceKind: 'external',
      externalSourceId: sourceId,
      worksheetMode: 'selected',
      worksheetName: 'Prices',
      dataStartRow: 2,
      status: 'active',
      version: 3,
      mappingVersion: 0,
      sheetId: null,
      createdAt: null,
      updatedAt: null,
    }] })
    if (url.pathname === '/api/v2/source-profiles/channels') return json(route, { items: [] })
    if (url.pathname === `/api/v2/sources/${managedSourceId}/configuration`) return json(route, {
      id: managedSourceId,
      name: 'Nextcloud Data Sheet',
      sourceKind: 'external',
      externalSourceId: sourceId,
      worksheetMode: 'selected',
      worksheetName: 'Prices',
      dataStartRow: 2,
      status: 'active',
      version: 3,
      mappingVersion: 0,
      sheetId: null,
      createdAt: null,
      updatedAt: null,
      mapping: null,
      legacyMapping: null,
      configuredWorksheets: [],
      readQuota: { enabled: true, limit: 10, usage: 2, remaining: 8, reset_at: null, exhausted: false },
      worksheetDiscovery: { requires_remote_read: false, metadata_source: 'snapshot', reason: null, snapshot_id: 5, snapshot_version: 1, snapshot_at: '2026-08-13T08:00:00Z', worksheet_names: ['Prices'] },
    })
    if (url.pathname === '/api/v2/commerce/sources') return json(route, {
      items: [{
        id: sourceId,
        provider: 'nextcloud',
        name: 'Nextcloud',
        type: 'Source',
        status: options.enabled ? 'configured' : 'disabled',
        implemented: true,
        placeholder: false,
        enabled: options.enabled,
        credential_status: 'configured',
        connection_configured: true,
        configuration_state: 'configured',
        last_health_check: '2026-08-13T08:00:00Z',
        data_role: 'Spreadsheet price input',
        action_label: 'Manage',
        action_href: '/commerce?tab=sources',
        health: { status: 'healthy', message: 'Saved evidence only.', latency_ms: 12, error_code: null },
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
        configured: true,
        connection_configured: true,
        configuration_state: 'configured',
        last_test: {
          status: 'healthy',
          message: 'Connection successful.',
          error_code: null,
          latency_ms: 12,
          checked_at: '2026-08-13T08:00:00Z',
        },
        enabled: options.enabled,
        access_mode: 'read_only',
        settings: {
          url: 'https://nextcloud.example.test',
          username: 'owner',
          spreadsheet_path: '/Reports/prices.xlsx',
          worksheet_mode: 'selected',
          worksheet_name: 'Prices',
        },
        secrets: { password: { status: 'configured', replaced_at: '2026-08-13T07:00:00Z' } },
        settings_schema: settingsSchema,
        credentials_returned: false,
        currency_profile: { status: 'resolved', currency: 'IRR', unit: 'RIAL' },
      })
    }

    audit.unhandledApiRequests.push(`${method} ${url.pathname}${url.search}`)
    return json(route, { code: 'UNHANDLED_TEST_REQUEST' }, 501)
  })
}

test('disabled persisted Nextcloud Source is shown as disabled and blocks Test/Browse without an external or write request', async ({ page }) => {
  const audit: TrafficAudit = { externalRequests: [], unhandledApiRequests: [], writes: [], savedPayloads: [] }
  await installNextcloudSourceMocks(page, audit, { enabled: false })

  await page.goto('/commerce?tab=sources')

  const card = page.locator(`[data-source-id="${sourceId}"]`)
  await expect(card.getByText('Disabled', { exact: true }).first()).toBeVisible()
  await expect(card.getByRole('button', { name: 'Test connection' })).toHaveCount(0)
  await expect(card.getByRole('button', { name: 'Configure Data' })).toHaveCount(0)

  await card.getByRole('button', { name: 'Edit connection' }).click()
  await expect(page.getByTestId('nextcloud-connection-state')).toHaveText('Disabled')
  await expect(page.getByRole('button', { name: 'Test connection' })).toBeDisabled()
  await expect(page.getByRole('button', { name: 'Browse Nextcloud' })).toBeDisabled()
  await expect(page.getByTestId('nextcloud-source-enabled-state')).toContainText(
    'This Source is disabled. Enable and save it before testing the connection or browsing Nextcloud.',
  )

  expect(audit.externalRequests).toEqual([])
  expect(audit.unhandledApiRequests).toEqual([])
  expect(audit.writes).toEqual([])
})

test('existing configured Nextcloud Source uses edit-mode copy without wizard steps and separates Data Sheet mapping from worksheet policy', async ({ page }) => {
  const audit: TrafficAudit = { externalRequests: [], unhandledApiRequests: [], writes: [], savedPayloads: [] }
  await installNextcloudSourceMocks(page, audit, { enabled: true })

  await page.goto(`/commerce?tab=sources&resource=${encodeURIComponent(sourceId)}`)

  await expect(page.getByTestId('nextcloud-connection-state')).toHaveText('Healthy')
  await expect(page.getByText(/^Step \d+$/)).toHaveCount(0)
  await expect(page.locator('[data-setup-step="worksheet"]')).toContainText(
    'Choose which workbook worksheets FlowHub reads. This policy is independent of Data Sheet column mappings.',
  )
  await expect(page.locator('[data-setup-step="data-sheet"]')).toContainText(
    'Column mapping and read limits now live on the Data Sheet page. Configure Source and Channel columns for the selected workbook; this is separate from the worksheet read policy above.',
  )

  expect(audit.externalRequests).toEqual([])
  expect(audit.unhandledApiRequests).toEqual([])
  expect(audit.writes).toEqual([])
})

test('Manage Connection opens the canonical editor and a blank-secret Save returns to the same Data Sheet', async ({ page }) => {
  const audit: TrafficAudit = { externalRequests: [], unhandledApiRequests: [], writes: [], savedPayloads: [] }
  await installNextcloudSourceMocks(page, audit, { enabled: true, allowSave: true })

  await page.goto(`/sources/${managedSourceId}`)
  await page.getByRole('button', { name: 'Manage Connection' }).first().click()

  await expect(page).toHaveURL(new RegExp(`/commerce\\?tab=sources&resource=${encodeURIComponent(sourceId)}&returnTo=`))
  await expect(page.getByTestId('nextcloud-connection-state')).toHaveText('Healthy')
  await expect(page.getByText('Saved credential ✓ — leave blank to keep unchanged.')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Back to Data Sheet' })).toBeVisible()

  await page.getByRole('button', { name: 'Save configuration' }).click()
  await expect(page).toHaveURL(`/sources/${managedSourceId}`)
  await expect(page.getByRole('heading', { name: 'Nextcloud Data Sheet' })).toBeVisible()

  expect(audit.savedPayloads).toHaveLength(1)
  expect(audit.savedPayloads[0]).toMatchObject({ secrets: {} })
  expect(audit.writes).toEqual([`PUT /api/v2/commerce/sources/${sourceId}/settings`])
  expect(audit.externalRequests).toEqual([])
  expect(audit.unhandledApiRequests).toEqual([])
})
