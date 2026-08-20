import { expect, test } from '@playwright/test'

test('legacy Workspace Preview requires and uses an explicit active Source binding', async ({ page }) => {
  let boundSourceId: string | null = null

  await page.addInitScript(() => {
    localStorage.setItem('wp_token', 'workspace-binding-isolated-token')
  })
  await page.route('**/api/**', async route => {
    const request = route.request()
    const url = new URL(request.url())
    if (!url.pathname.startsWith('/api/')) return route.continue()
    const json = (body: unknown, status = 200) => route.fulfill({
      status,
      contentType: 'application/json',
      body: JSON.stringify(body),
    })

    if (url.pathname === '/api/v2/setup/status') return json({ completed: true })
    if (url.pathname === '/api/auth/me') return json({
      username: 'workspace-owner',
      role: 'admin',
      is_admin: true,
      is_super_admin: false,
      permissions: { can_access_site: true, can_fetch: true, can_view_logs: true, can_view_settings: true },
      maintenance: { enabled: false, message: '' },
    })
    if (url.pathname === '/api/health') return json({ status: 'ok' })
    if (url.pathname === '/api/v2/settings') return json({
      woocommerceUrl: 'https://store.example.test',
      nextcloudUrl: 'https://cloud.example.test',
      syncIntervalMinutes: 15,
      timezone: 'UTC',
      currency: 'EUR',
      currencyUnit: 'EUR',
      environment: 'test',
      wcConfigured: true,
      ncConfigured: true,
    })
    if (url.pathname === '/api/v2/workspace/source-binding' && request.method() === 'GET') {
      return json({
        boundSource: boundSourceId
          ? { sourceId: boundSourceId, sourceName: 'Current Nextcloud', status: 'active' }
          : null,
        candidates: [{ sourceId: 'source-active', sourceName: 'Current Nextcloud', status: 'active' }],
      })
    }
    if (url.pathname === '/api/v2/workspace/source-binding' && request.method() === 'PUT') {
      const body = JSON.parse(request.postData() ?? '{}') as { source_id?: string }
      boundSourceId = body.source_id ?? null
      return json({ sourceId: boundSourceId, sourceName: 'Current Nextcloud', status: 'active' })
    }
    if (url.pathname === '/api/v2/workspace/preview' && request.method() === 'POST') {
      return json({
        id: 'preview-active-source',
        sourceId: boundSourceId,
        sourceName: 'Current Nextcloud',
        state: 'preview_ready',
        totalChanges: 1,
        changes: [],
        rows: [{
          id: 'preview-active-source:Sheet1:2',
          source: {
            previewId: 'preview-active-source',
            sourceId: boundSourceId,
            sourceType: 'nextcloud_spreadsheet',
            sourceSnapshotId: 1,
            sourceSnapshotVersion: 1,
            sourceFilePath: '/prices.xlsx',
            worksheet: 'Sheet1',
            rowNumber: 2,
            productId: 'product-1',
            sku: 'SKU-1',
            productName: 'Active Product',
          },
          matchedProduct: null,
          currentPrice: 100,
          proposedPrice: 110,
          currentStock: 1,
          sourceStock: 1,
          stockDifference: 0,
          difference: 10,
          changePct: 10,
          status: 'valid_change',
          errors: [],
          warnings: [],
          eligible_for_dry_run: true,
        }],
        summary: {
          total_rows: 1,
          valid_changes: 1,
          unchanged_rows: 0,
          warning_rows: 0,
          error_rows: 0,
          duplicate_rows: 0,
          missing_products: 0,
          large_changes: 0,
        },
        startedAt: '2026-08-20T00:00:00Z',
      })
    }
    return json({}, 404)
  })

  await page.goto('/workspace')
  await expect(page.getByRole('heading', { name: 'Workspace' })).toBeVisible()
  const sourceSelect = page.getByRole('combobox', { name: 'Workspace Source' })
  await expect(sourceSelect).toHaveValue('')
  await expect(page.getByRole('button', { name: 'Start Preview' })).toBeDisabled()

  await sourceSelect.selectOption('source-active')
  const bindRequest = page.waitForRequest(request => (
    request.method() === 'PUT'
      && new URL(request.url()).pathname === '/api/v2/workspace/source-binding'
  ))
  await page.getByRole('button', { name: 'Bind Source' }).click()
  expect(JSON.parse((await bindRequest).postData() ?? '{}')).toEqual({ source_id: 'source-active' })
  await expect(page.getByRole('button', { name: 'Start Preview' })).toBeEnabled()

  const previewRequest = page.waitForRequest(request => (
    request.method() === 'POST'
      && new URL(request.url()).pathname === '/api/v2/workspace/preview'
  ))
  await page.getByRole('button', { name: 'Start Preview' }).click()
  expect(JSON.parse((await previewRequest).postData() ?? '{}')).toEqual({ source_id: 'source-active' })
  await expect(page.getByText('Active Product', { exact: true })).toBeVisible()
})
