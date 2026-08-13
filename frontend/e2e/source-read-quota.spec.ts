import { expect, test, type Page, type Route } from '@playwright/test'

const sourceId = 'source-read-quota'

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({
    status,
    contentType: 'application/json; charset=utf-8',
    body: JSON.stringify(body),
  })
}

async function installQuotaMocks(page: Page) {
  let worksheetRequests = 0
  await page.addInitScript(() => {
    localStorage.setItem('wp_token', 'source-read-quota-isolated-token')
    localStorage.setItem('flowhub.locale', 'en')
  })
  await page.route('**/*', async route => {
    const request = route.request()
    const url = new URL(request.url())
    if (!['127.0.0.1', 'localhost'].includes(url.hostname)) return route.abort('blockedbyclient')
    if (url.pathname.startsWith('/static/logos/')) return route.fulfill({ status: 204 })
    if (!url.pathname.startsWith('/api/')) return route.continue()
    if (request.method() === 'POST' && url.pathname === `/api/v2/sources/${sourceId}/worksheets/refresh`) {
      worksheetRequests += 1
      return json(route, {
        detail: {
          code: 'SOURCE_DISCOVERY_LIMIT_REACHED',
          message: 'The worksheet discovery allowance has been used.',
          limit: 30,
          usage: 30,
          reset_at: '2030-08-14T00:00:00Z',
          retry_after_seconds: 60,
        },
      }, 429)
    }
    if (request.method() !== 'GET') return json(route, { code: 'MOCK_WRITE_BLOCKED' }, 405)
    if (url.pathname === '/api/auth/me') return json(route, {
      username: 'source-owner', role: 'admin', is_admin: true, is_super_admin: false,
      permissions: { can_access_site: true, 'workspace.read': true, 'workspace.create': true, 'workspace.edit': true },
      maintenance: { enabled: false, message: '' },
    })
    if (url.pathname === '/api/v2/setup/status') return json(route, { completed: true })
    if (url.pathname === '/api/health') return json(route, { status: 'ok' })
    if (url.pathname === '/api/v2/exchange-rates/me') return json(route, { selections: [], rates: [] })
    if (url.pathname === `/api/v2/sources/${sourceId}/configuration`) return json(route, {
      id: sourceId, name: 'Quota source', sourceKind: 'external', externalSourceId: 'nextcloud:primary',
      worksheetMode: 'selected', worksheetName: 'Prices', dataStartRow: 2, status: 'active', version: 1,
      mappingVersion: 0, sheetId: null, createdAt: null, updatedAt: null, mapping: null, legacyMapping: null,
      configuredWorksheets: [],
      readQuota: { enabled: true, limit: 10, usage: 9, remaining: 1, reset_at: '2030-08-14T00:00:00Z', exhausted: false },
      discoveryQuota: { enabled: true, limit: 30, usage: 29, remaining: 1, reset_at: '2030-08-14T00:00:00Z', exhausted: false },
      worksheetDiscovery: { requires_remote_read: true, metadata_source: 'remote', reason: 'snapshot_metadata_unavailable', snapshot_id: null, snapshot_version: null, snapshot_at: null, worksheet_names: [] },
    })
    if (url.pathname === '/api/v2/source-profiles/channels') return json(route, { items: [] })
    if (decodeURIComponent(url.pathname) === '/api/v2/commerce/sources/nextcloud:primary/configuration') return json(route, {
      source_id: 'nextcloud:primary', provider: 'nextcloud', display_name: 'Nextcloud', configured: true,
      connection_configured: true, configuration_state: 'configured', enabled: true, access_mode: 'read_only',
      settings: { source_read_policy: { enabled: true, max_reads_per_24h: 10, manual_read_allowed: true } },
      secrets: {}, settings_schema: [], credentials_returned: false,
    })
    if (url.pathname === `/api/v2/sources/${sourceId}/worksheets`) {
      return json(route, {
        sourceId, sourceRevisionId: 'external:snapshot-1:1', items: [{
          name: 'Prices', rowCount: null,
          columns: [
            { id: 'A', letter: 'A', header: 'Product Name' },
            { id: 'B', letter: 'B', header: 'Cost' },
            { id: 'C', letter: 'C', header: 'SKU' },
            { id: 'H', letter: 'H', header: 'Stock' },
          ],
        }],
        readQuota: { enabled: true, limit: 10, usage: 9, remaining: 1, resetAt: '2030-08-14T00:00:00Z', exhausted: false },
        discoveryQuota: { enabled: true, limit: 30, usage: 29, remaining: 1, resetAt: '2030-08-14T00:00:00Z', exhausted: false },
        worksheetDiscovery: { requiresRemoteRead: false, metadataSource: 'snapshot', remoteReadUsed: false, snapshotId: 1, snapshotVersion: 1, snapshotAt: '2030-08-13T00:00:00Z' },
      })
    }
    return json(route, { code: 'UNHANDLED_TEST_REQUEST' }, 501)
  })
  return { worksheetRequests: () => worksheetRequests }
}

test('remote metadata refresh has a separate allowance while local detection remains available', async ({ page }) => {
  const audit = await installQuotaMocks(page)

  await page.goto(`/sources/${sourceId}`)
  const detect = page.getByRole('button', { name: 'Detect worksheets' })
  const refresh = page.getByRole('button', { name: 'Refresh from Nextcloud' })
  await expect(detect).toBeEnabled()
  await expect(page.getByTestId('worksheet-detection-help')).toContainText(
    'Detection stays local',
  )
  await expect(page.getByTestId('worksheet-discovery-quota')).toContainText('29 of 30 used')
  await refresh.click()

  await expect(page.getByTestId('worksheet-discovery-feedback')).toContainText('Worksheet refresh allowance reached')
  await expect(page.getByTestId('worksheet-discovery-feedback')).toContainText('30 of 30 remote metadata refreshes were used')
  await expect(refresh).toBeDisabled()
  await expect(detect).toBeEnabled()
  expect(audit.worksheetRequests()).toBe(1)

  await detect.click()
  const productNamePicker = page.getByLabel('Source Product Name column reference')
  await expect(productNamePicker).toContainText('A — Product Name')
  await expect(productNamePicker).toContainText('H — Stock')
  expect(audit.worksheetRequests()).toBe(1)
})
