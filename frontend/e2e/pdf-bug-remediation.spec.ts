import path from 'node:path'
import { mkdirSync, readFileSync } from 'node:fs'
import { expect, test, type Page, type Route } from '@playwright/test'

const screenshotRoot = path.resolve('..', 'docs', 'screenshots', 'v1.3', 'pdf-bug-remediation', 'after')
mkdirSync(screenshotRoot, { recursive: true })

const mockLogo = readFileSync(path.resolve('public', 'flowhub-logo.png'))
const viewports = [
  { width: 1280, height: 720 },
  { width: 1366, height: 768 },
  { width: 1440, height: 900 },
  { width: 1920, height: 1080 },
] as const

type DataQualityMode = 'never_checked' | 'healthy' | 'issues_found' | 'failed'

interface MockState {
  dataQualityMode: DataQualityMode
  lifecycleAction: 'delete' | 'archive' | 'blocked'
  deletePayloads: unknown[]
  unhandledApiRequests: string[]
  externalRequests: string[]
}

function sourceProfile() {
  return {
    id: 'source-pdf-audit',
    name: 'Synthetic Daily Prices',
    sourceKind: 'flowhub_sheet',
    externalSourceId: null,
    worksheetMode: 'selected',
    worksheetName: 'Main',
    dataStartRow: 3,
    status: 'active',
    version: 7,
    mappingVersion: 3,
    sheetId: 'sheet-pdf-audit',
  }
}

const channelItems = [
  { channelId: 'woocommerce:primary', name: 'WooCommerce Primary', connectorType: 'woocommerce', capabilityVersion: 'wc-v4', capabilities: {}, enabled: true, implementationState: 'implemented', available: true },
  { channelId: 'snappshop:main', name: 'SnappShop Main', connectorType: 'snappshop', capabilityVersion: 'snap-v2', capabilities: {}, enabled: true, implementationState: 'implemented', available: true },
  { channelId: 'tapsishop:main', name: 'TapsiShop Main', connectorType: 'tapsishop', capabilityVersion: 'tapsi-v1', capabilities: {}, enabled: true, implementationState: 'implemented', available: true },
  { channelId: 'digikala:future', name: 'Digikala', connectorType: 'digikala', capabilityVersion: 'none', capabilities: {}, enabled: false, implementationState: 'coming_soon', available: false },
]

const sharedMapping = {
  id: 'mapping-pdf-audit-v3',
  version: 3,
  checksum: 'a'.repeat(64),
  worksheetMode: 'selected',
  worksheetName: 'Main',
  dataStartRow: 3,
  worksheetRuleMode: 'shared',
  duplicateProductPolicy: 'block',
  worksheetRules: [],
  valuePolicy: {
    blank: 'no_change', x: 'unavailable', dash: 'no_change', zero: 'explicit_zero',
    formula: 'calculated_value', invalid: 'blocked',
  },
  sourceFields: [
    { field: 'name', referenceType: 'column_letter', referenceValue: 'A', required: true },
    { field: 'source_key', referenceType: 'column_letter', referenceValue: 'B', required: false },
  ],
  channels: [
    {
      channelId: 'woocommerce:primary', worksheetName: null, enabled: true,
      fields: [
        { field: 'external_id', referenceType: 'column_letter', referenceValue: 'C' },
        { field: 'price', referenceType: 'column_letter', referenceValue: 'D' },
        { field: 'stock', referenceType: 'column_letter', referenceValue: 'E' },
        { field: 'status', referenceType: 'disabled', referenceValue: null },
      ],
    },
    {
      channelId: 'snappshop:main', worksheetName: null, enabled: true,
      fields: [
        { field: 'external_id', referenceType: 'column_letter', referenceValue: 'F' },
        { field: 'price', referenceType: 'header_name', referenceValue: 'قیمت اسنپ' },
        { field: 'stock', referenceType: 'disabled', referenceValue: null },
        { field: 'status', referenceType: 'disabled', referenceValue: null },
      ],
    },
    {
      channelId: 'tapsishop:main', worksheetName: null, enabled: true,
      fields: [
        { field: 'external_id', referenceType: 'column_letter', referenceValue: 'H' },
        { field: 'price', referenceType: 'column_letter', referenceValue: 'J' },
        { field: 'stock', referenceType: 'disabled', referenceValue: null },
        { field: 'status', referenceType: 'disabled', referenceValue: null },
      ],
    },
  ],
}

function dataQualityResponse(mode: Exclude<DataQualityMode, 'failed'>) {
  const checked = mode !== 'never_checked'
  const hasIssues = mode === 'issues_found'
  return {
    items: hasIssues ? [
      {
        id: 'issue-price-42', sourceId: 'source-pdf-audit', worksheet: 'Marketplace',
        sourceProductName: 'Synthetic Cable', channelId: 'snappshop:main', mappingState: 'resolved',
        category: 'invalid_value', severity: 'blocked', code: 'INVALID_NUMERIC_VALUE',
        summary: 'Raw backend diagnostic text is intentionally not the primary presentation.',
        recommendedAction: 'Raw backend action is intentionally not the primary presentation.',
        technicalDetails: { field: 'price', row: 42, rawValue: 'not-a-price' },
      },
      {
        id: 'issue-id-7', sourceId: 'source-pdf-audit', worksheet: 'فروش تهران',
        sourceProductName: 'Synthetic Mouse', channelId: 'woocommerce:primary', mappingState: 'unmapped',
        category: 'missing_mapping', severity: 'warning', code: 'LISTING_NOT_MAPPED',
        summary: 'Raw backend diagnostic text is intentionally not the primary presentation.',
        recommendedAction: 'Raw backend action is intentionally not the primary presentation.',
        technicalDetails: { row: 7 },
      },
    ] : [],
    counts: hasIssues ? { invalid_value: 1, missing_mapping: 1 } : {},
    total: hasIssues ? 2 : 0,
    summary: {
      state: mode,
      totalIssues: hasIssues ? 2 : 0,
      blockingIssues: hasIssues ? 1 : 0,
      warnings: hasIssues ? 1 : 0,
      affectedProducts: hasIssues ? 2 : 0,
      affectedChannels: hasIssues ? 2 : 0,
      affectedSources: checked ? 1 : 0,
      resolvedSinceLastRead: checked ? 3 : 0,
      trendSinceLastRead: checked ? -2 : null,
      productsChecked: checked ? 125 : 0,
      sourcesChecked: checked ? 1 : 0,
      checkedAt: checked ? '2026-07-15T09:30:00Z' : null,
      scanId: checked ? `scan-${mode}` : null,
      errorCode: null,
      categories: hasIssues
        ? [{ category: 'invalid_value', count: 1 }, { category: 'missing_mapping', count: 1 }]
        : [],
    },
  }
}

function channelHealthPayload() {
  return {
    checkedAt: '2026-07-15T09:40:00Z',
    summary: { overall: 'Warning', counts: { Operational: 1, Warning: 1, Error: 0, 'Unable to check': 0, Disabled: 0 } },
    external_call_performed: false,
    orderSyncRunner: { state: 'running', lastHeartbeat: '2026-07-15T09:39:30Z' },
    items: [
      {
        channelId: 'woocommerce:primary', channelType: 'woocommerce', enabled: true,
        accessMode: 'read_write', status: 'Operational', summary: 'WooCommerce is operational.',
        lastChecked: '2026-07-15T09:39:00Z', latency: 18,
        lastSuccessfulOperation: '2026-07-15T09:35:00Z', lastErrorCategory: null,
        capabilityState: { read_products: true, write_prices: true, write_stock: true },
        nextRecommendedAction: 'No immediate action required.',
        dimensions: {
          credentials: { status: 'Operational', message: 'Credential validation passed.' },
          productCache: { status: 'Operational', message: 'The local product cache was refreshed successfully.' },
        },
        lastProductRead: '2026-07-15T09:35:00Z', lastProductWrite: null,
        lastOrderSync: '2026-07-15T09:20:00Z', polling: { cursor: 'synthetic-cursor', lastRunAt: '2026-07-15T09:20:00Z' },
        webhooks: { supported: true, received: 4, queued: 0, processed: 4, deadLetter: 0, lastReceivedAt: '2026-07-15T09:10:00Z', lastProcessedAt: '2026-07-15T09:11:00Z' },
      },
      {
        channelId: 'snappshop:main', channelType: 'snappshop', enabled: true,
        accessMode: 'read_only', status: 'Warning', summary: 'Configured, but no recent product synchronization has been recorded.',
        lastChecked: '2026-07-15T09:38:00Z', latency: 27,
        lastSuccessfulOperation: null, lastErrorCategory: 'stale_sync',
        capabilityState: { read_products: true, write_prices: false },
        nextRecommendedAction: 'Update credentials and run an explicit health refresh.',
        dimensions: {
          credentials: { status: 'Operational', message: 'Credential validation passed.' },
          productCache: { status: 'Warning', message: 'Configured, but no recent product or order synchronization has been recorded.' },
        },
        lastProductRead: null, lastProductWrite: null, lastOrderSync: null,
        polling: { cursor: null, lastRunAt: null },
        webhooks: { supported: false, received: 0, queued: 0, processed: 0, deadLetter: 0, lastReceivedAt: null, lastProcessedAt: null },
      },
    ],
  }
}

async function installIsolatedMockApi(page: Page, state: MockState) {
  await page.addInitScript(() => {
    localStorage.setItem('wp_token', 'pdf-remediation-isolated-token')
    if (!localStorage.getItem('flowhub.locale')) localStorage.setItem('flowhub.locale', 'en')
  })

  await page.route('**/*', async (route: Route) => {
    const request = route.request()
    const url = new URL(request.url())

    if (!['127.0.0.1', 'localhost'].includes(url.hostname)) {
      state.externalRequests.push(`${request.method()} ${request.url()}`)
      await route.abort('blockedbyclient')
      return
    }
    if (url.pathname.startsWith('/static/logos/')) {
      await route.fulfill({ status: 200, contentType: 'image/png', body: mockLogo })
      return
    }
    if (!url.pathname.startsWith('/api/')) {
      await route.continue()
      return
    }

    const json = async (body: unknown, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
    const pathname = url.pathname
    const method = request.method()

    if (pathname === '/api/v2/setup/status' && method === 'GET') return json({ completed: true })
    if (pathname === '/api/auth/me' && method === 'GET') return json({
      username: 'visual-owner', role: 'admin', is_admin: true, is_super_admin: false,
      permissions: { can_access_site: true, can_fetch: true, can_view_logs: true, can_view_settings: true, 'workspace.admin': true },
      maintenance: { enabled: false, message: '' },
    })
    if (pathname === '/api/health' && method === 'GET') return json({ status: 'ok', version: 'pdf-remediation-mock' })

    if (pathname === '/api/v2/commerce/sources' && method === 'GET') return json({
      items: [],
      relationship_map: { nodes: [], example: [], runtime_write_blocked: true, read_only: true },
    })
    if (pathname === '/api/v2/source-profiles' && method === 'GET') return json({ items: [sourceProfile()] })
    if (pathname === '/api/v2/source-profiles/channels' && method === 'GET') return json({ items: channelItems })
    if (pathname === '/api/v2/sources/source-pdf-audit/configuration' && method === 'GET') {
      return json({ ...sourceProfile(), mapping: sharedMapping, legacyMapping: null })
    }
    if (pathname === '/api/v2/sources/source-pdf-audit/worksheets' && method === 'GET') {
      return json({
        sourceId: 'source-pdf-audit', sourceRevisionId: 'sheet-revision-isolated',
        items: [{ name: 'Main', rowCount: 125 }, { name: 'فروش تهران', rowCount: 80 }, { name: 'Marketplace', rowCount: 45 }],
      })
    }
    if (pathname === '/api/v2/sources/source-pdf-audit/preview' && method === 'GET') {
      return json({
        items: [{
          rowKey: 'Main:3', rowNumber: 3, worksheetName: 'Main', recognized: true, hasIssues: false, ready: true,
          sourceProduct: { name: 'Synthetic Cable', source_key: 'SYN-CABLE-1' },
          channels: [
            { channelId: 'woocommerce:primary', fields: { external_id: '51550', price: '12500000', stock: '8', status: null } },
            { channelId: 'snappshop:main', fields: { external_id: '1826345203', price: '12900000', stock: null, status: null } },
            { channelId: 'tapsishop:main', fields: { external_id: '7785746738', price: '12700000', stock: null, status: null } },
          ],
          valuePolicy: {}, issues: [],
        }],
        total: 1, recognized: 1, ignored: 0,
        issues: [], sheetRevisionId: 'sheet-revision-isolated', mappingRevisionId: 'mapping-pdf-audit-v3',
        businessSummary: { productsFound: 125, productsReady: 119, priceChanges: 28, stockChanges: 7, unchanged: 91, needsAttention: 6, channelsReady: 3, channelsNotConfigured: 1 },
      })
    }
    if (pathname === '/api/v2/sources/source-pdf-audit/lifecycle' && method === 'GET') {
      return json({
        sourceId: 'source-pdf-audit', sourceName: 'Synthetic Daily Prices', sourceVersion: 7,
        sourceStatus: 'active', action: state.lifecycleAction,
        blockers: state.lifecycleAction === 'blocked' ? { activeWorkspaces: 1 } : {},
        protectedHistory: state.lifecycleAction === 'delete' ? {} : { snapshots: 4, draftRevisions: 2, applyJobs: 1, auditEvents: 8 },
      })
    }
    if (pathname === '/api/v2/sources/source-pdf-audit' && method === 'DELETE') {
      state.deletePayloads.push(JSON.parse(request.postData() ?? '{}'))
      return json({
        outcome: 'archived', sourceId: 'source-pdf-audit', sourceName: 'Synthetic Daily Prices',
        source: { ...sourceProfile(), status: 'disabled', version: 8 },
        impact: {
          sourceId: 'source-pdf-audit', sourceName: 'Synthetic Daily Prices', sourceVersion: 7,
          sourceStatus: 'active', action: 'archive', blockers: {},
          protectedHistory: { snapshots: 4, draftRevisions: 2, applyJobs: 1, auditEvents: 8 },
        },
      })
    }

    if (pathname === '/api/v2/data-quality' && method === 'GET') {
      if (state.dataQualityMode === 'failed') return json({ code: 'SOURCE_SCAN_FAILED', message: 'Synthetic check failure.' }, 500)
      return json(dataQualityResponse(state.dataQualityMode))
    }
    if (pathname === '/api/v2/data-quality/scans' && method === 'POST') {
      state.dataQualityMode = 'healthy'
      return json({ summary: dataQualityResponse('healthy').summary })
    }

    if (pathname === '/api/v2/diagnostics/status' && method === 'GET') {
      return json({
        overall_status: 'warning', checkedAt: '2026-07-15T09:40:00Z', external_call_performed: false,
        checks: [{ category: 'database', target: 'isolated-test-db', status: 'pass', severity: 'info' }],
        connectors: [
          { id: 'nextcloud:isolated', name: 'Nextcloud synthetic Source', connector_type: 'nextcloud', enabled: true, status: 'operational', health: 'healthy', last_checked_at: '2026-07-15T09:39:00Z', last_successful_operation: '2026-07-15T09:30:00Z' },
          { id: 'woocommerce:duplicate', name: 'Must not render as Source', connector_type: 'woocommerce', enabled: true, status: 'operational', health: 'healthy', last_checked_at: '2026-07-15T09:39:00Z' },
        ],
        channelHealth: channelHealthPayload(),
        rateLimiter: {
          settings: { read_requests_per_minute: 60, write_requests_per_minute: 30, read_delay_ms: 250, write_delay_ms: 500 },
          queue_length: 0, average_request_duration_ms: 120, average_latency_ms: 80,
          throttle_count: 0, last_throttle: null, last_connector_delay_ms: 250,
          last_limiter_delay_ms: 500, requests_completed: 42, requests_delayed: 2,
          estimated_completion_seconds: null,
        },
      })
    }
    if (pathname === '/api/v2/diagnostics/channels/health/refresh' && method === 'POST') return json(channelHealthPayload())

    state.unhandledApiRequests.push(`${method} ${pathname}${url.search}`)
    return json({ code: 'UNHANDLED_TEST_API', message: 'The isolated E2E fixture did not register this request.' }, 418)
  })
}

async function screenshot(page: Page, name: string) {
  await page.screenshot({ path: path.join(screenshotRoot, `${name}.png`), fullPage: true })
}

test.describe.serial('PDF usability remediation with a fully isolated synthetic backend', () => {
  let state: MockState

  test.beforeEach(async ({ page }) => {
    state = { dataQualityMode: 'never_checked', lifecycleAction: 'archive', deletePayloads: [], unhandledApiRequests: [], externalRequests: [] }
    await installIsolatedMockApi(page, state)
  })

  test.afterEach(async () => {
    expect(state.externalRequests, 'No browser request may leave the isolated localhost fixture').toEqual([])
    expect(state.unhandledApiRequests, 'Every application API request must be explicitly mocked').toEqual([])
  })

  test('Sources list exposes a confirmation-first protected delete/archive flow', async ({ page }) => {
    for (const viewport of viewports) {
      await page.setViewportSize(viewport)
      await page.goto('/sources')
      await expect(page.getByRole('heading', { name: 'Sources', exact: true })).toBeVisible()
      await expect(page.getByText('Synthetic Daily Prices', { exact: true })).toBeVisible()
      await screenshot(page, `sources-list-en-${viewport.width}x${viewport.height}`)
    }

    await page.setViewportSize({ width: 1280, height: 720 })
    await page.goto('/sources')
    const menuTrigger = page.getByRole('button', { name: 'Delete or archive safely' })
    const openDeleteDialog = async () => {
      await menuTrigger.click()
      await page.getByRole('menuitem', { name: 'Delete Source' }).click()
    }
    await openDeleteDialog()
    const dialog = page.getByRole('dialog', { name: 'Delete Source' })
    await expect(dialog).toBeVisible()
    await expect(dialog).toContainText('Synthetic Daily Prices')
    await expect(dialog).toContainText('Archive Source')
    const cancelButton = dialog.getByRole('button', { name: 'Cancel' })
    const archiveButton = dialog.getByRole('button', { name: 'Archive Source' })
    await expect(cancelButton).toBeFocused()
    await page.keyboard.press('Tab')
    await expect(archiveButton).toBeFocused()
    await page.keyboard.press('Tab')
    await expect(cancelButton).toBeFocused()
    await screenshot(page, 'source-delete-confirmation-en-1280x720')

    await page.keyboard.press('Escape')
    await expect(dialog).toBeHidden()
    await expect(menuTrigger).toBeFocused()
    expect(state.deletePayloads).toHaveLength(0)

    state.lifecycleAction = 'blocked'
    await openDeleteDialog()
    await expect(dialog).toContainText('Cannot delete — active Workspace exists')
    await expect(dialog.getByRole('button', { name: 'Delete Source' })).toBeDisabled()
    await screenshot(page, 'source-delete-blocked-en-1280x720')
    await page.keyboard.press('Escape')

    state.lifecycleAction = 'delete'
    await openDeleteDialog()
    await expect(dialog).toContainText('Delete unused Source')
    await screenshot(page, 'source-delete-unused-en-1280x720')
    await page.keyboard.press('Escape')

    state.lifecycleAction = 'archive'
    await openDeleteDialog()
    await page.getByRole('button', { name: 'Archive Source' }).click()
    await expect(page.getByRole('heading', { name: 'Disabled' })).toBeVisible()
    await expect(page.locator('.fh-badge').filter({ hasText: /^Disabled$/ })).toBeVisible()
    expect(state.deletePayloads).toEqual([{ expected_source_version: 7, confirmation_name: 'Synthetic Daily Prices' }])
    await screenshot(page, 'source-archived-result-en-1280x720')
  })

  test('Source configuration presents shared and independent worksheet rules with per-Channel columns', async ({ page }) => {
    for (const viewport of viewports) {
      await page.setViewportSize(viewport)
      await page.goto('/sources/source-pdf-audit')
      await expect(page.getByRole('heading', { name: 'Worksheet rules' })).toBeVisible()
      await page.getByText('Worksheet rules', { exact: true }).click()
      await page.getByText('Workbook', { exact: true }).click()
      await page.getByText('Channel columns', { exact: true }).click()
      await expect(page.getByRole('heading', { name: 'WooCommerce Primary' })).toBeVisible()
      await expect(page.getByRole('heading', { name: 'SnappShop Main' })).toBeVisible()
      await expect(page.getByRole('heading', { name: 'TapsiShop Main' })).toBeVisible()
      await expect(page.getByRole('heading', { name: 'Digikala' })).toBeVisible()
      const wooColumns = page.locator('[data-channel-id="woocommerce:primary"]')
      const snapColumns = page.locator('[data-channel-id="snappshop:main"]')
      const tapsiColumns = page.locator('[data-channel-id="tapsishop:main"]')
      await expect(wooColumns.getByLabel('price column reference')).toHaveValue('D')
      await expect(snapColumns.getByLabel('price column reference')).toHaveValue('قیمت اسنپ')
      await expect(tapsiColumns.getByLabel('price column reference')).toHaveValue('J')
      await page.getByRole('button', { name: 'Detect worksheets' }).click()
      const mainWorksheet = page.getByRole('checkbox', { name: /Main/ })
      const tehranWorksheet = page.getByRole('checkbox', { name: /فروش تهران/ })
      const marketplaceWorksheet = page.getByRole('checkbox', { name: /Marketplace/ })
      await expect(mainWorksheet).toBeChecked()
      await tehranWorksheet.check()
      await expect(tehranWorksheet).toBeChecked()
      await expect(marketplaceWorksheet).not.toBeChecked()
      await screenshot(page, `source-configuration-shared-en-${viewport.width}x${viewport.height}`)

      await page.getByRole('radio', { name: /Configure each worksheet separately/ }).check()
      await page.getByText('Worksheet columns', { exact: true }).click()
      const tehranRule = page.getByText('فروش تهران', { exact: true }).last().locator('xpath=ancestor::details[1]')
      const marketplaceRule = page.getByText('Marketplace', { exact: true }).last().locator('xpath=ancestor::details[1]')
      await expect(tehranRule).toBeVisible()
      await expect(marketplaceRule).toBeVisible()
      await tehranRule.locator(':scope > summary').click()
      await tehranRule.locator(':scope > summary').getByRole('checkbox').check()
      await expect(tehranRule.getByText('Product fields shared by all Channels', { exact: true })).toBeVisible()
      await expect(marketplaceRule.locator(':scope > summary').getByRole('checkbox')).not.toBeChecked()
      await screenshot(page, `source-configuration-per-worksheet-en-${viewport.width}x${viewport.height}`)
    }

    await page.setViewportSize({ width: 1440, height: 900 })
    await page.goto('/sources/source-pdf-audit')
    await page.getByRole('button', { name: 'Preview recognized rows' }).click()
    const productsFound = page.getByText('Products found')
    await expect(productsFound).toBeVisible()
    await productsFound.scrollIntoViewIfNeeded()
    await expect(page.getByText('28', { exact: true })).toBeVisible()
    await expect(page.getByText('12500000', { exact: true })).toBeVisible()
    await expect(page.getByText('12900000', { exact: true })).toBeVisible()
    await expect(page.getByText('12700000', { exact: true })).toBeVisible()
    await screenshot(page, 'source-preview-business-summary-en-1440x900')
  })

  test('Data Quality distinguishes never checked, healthy, issues, and failed states', async ({ page }) => {
    state.dataQualityMode = 'never_checked'
    await page.goto('/data-quality')
    await expect(page.getByRole('heading', { name: 'No check has been run yet' })).toBeVisible()
    await screenshot(page, 'data-quality-never-checked-en-1440x900')

    state.dataQualityMode = 'healthy'
    await page.reload()
    await expect(page.getByRole('heading', { name: 'No data problems found' })).toBeVisible()
    await page.getByText('View last scan details', { exact: true }).click()
    await expect(page.getByText('125', { exact: true })).toBeVisible()
    await screenshot(page, 'data-quality-healthy-en-1440x900')

    state.dataQualityMode = 'issues_found'
    for (const viewport of viewports) {
      await page.setViewportSize(viewport)
      await page.reload()
      await expect(page.getByRole('heading', { name: 'Data Quality Summary' })).toBeVisible()
      await expect(page.getByText('Total issues')).toBeVisible()
      await expect(page.getByText('Most common problems')).toBeVisible()
      await expect(page.getByRole('heading', { name: 'Issue list' })).toBeVisible()
      await screenshot(page, `data-quality-issues-en-${viewport.width}x${viewport.height}`)
    }

    state.dataQualityMode = 'failed'
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.reload()
    await expect(page.getByRole('heading', { name: 'The data check failed' })).toBeVisible()
    await screenshot(page, 'data-quality-failed-en-1440x900')
  })

  test('Diagnostics is summary-first and keeps technical details collapsed until requested', async ({ page }) => {
    for (const viewport of viewports) {
      await page.setViewportSize(viewport)
      await page.goto('/diagnostics')
      await expect(page.getByRole('heading', { name: 'System status' })).toBeVisible()
      await expect(page.getByText('Requests available now')).toBeVisible()
      await expect(page.getByText('No wait expected')).toBeVisible()
      await expect(page.getByText('WooCommerce', { exact: true })).toBeVisible()
      await expect(page.getByText('SnappShop', { exact: true })).toBeVisible()
      await expect(page.getByText('Nextcloud synthetic Source', { exact: true })).toBeVisible()
      await expect(page.getByText('Must not render as Source')).toHaveCount(0)
      await screenshot(page, `diagnostics-summary-en-${viewport.width}x${viewport.height}`)
    }

    await page.setViewportSize({ width: 1440, height: 900 })
    const details = page.locator('[data-testid="diagnostics-details-woocommerce:primary"]')
    await expect(details).not.toHaveAttribute('open', '')
    await details.locator('summary').click()
    await expect(details).toHaveAttribute('open', '')
    await expect(details.getByText('Product cache', { exact: true })).toBeVisible()
    await screenshot(page, 'diagnostics-expanded-en-1440x900')
  })

  test('affected workflows remain usable in Persian RTL and English LTR', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 })
    state.dataQualityMode = 'issues_found'
    const routes = [
      ['sources', '/sources'],
      ['source-configuration', '/sources/source-pdf-audit'],
      ['data-quality', '/data-quality'],
      ['diagnostics', '/diagnostics'],
    ] as const

    for (const [name, route] of routes) {
      await page.goto(route)
      await expect(page.locator('html')).toHaveAttribute('lang', 'en')
      await expect(page.locator('html')).toHaveAttribute('dir', 'ltr')
      await screenshot(page, `locale-en-${name}-1440x900`)
    }

    await page.evaluate(() => localStorage.setItem('flowhub.locale', 'fa'))
    for (const [name, route] of routes) {
      await page.goto(route)
      await expect(page.locator('html')).toHaveAttribute('lang', 'fa')
      await expect(page.locator('html')).toHaveAttribute('dir', 'rtl')
      await expect(page.locator('main')).toBeVisible()
      await screenshot(page, `locale-fa-${name}-1440x900`)
      if (name === 'sources') {
        await page.getByRole('button', { name: 'حذف یا بایگانی امن' }).click()
        await page.getByRole('menuitem', { name: 'حذف منبع' }).click()
        await expect(page.getByRole('dialog', { name: 'حذف منبع' })).toBeVisible()
        await screenshot(page, 'source-delete-confirmation-fa-1440x900')
        await page.keyboard.press('Escape')
      }
    }

    await page.evaluate(() => localStorage.setItem('flowhub.locale', 'en'))
    await page.goto('/sources')
    await expect(page.locator('html')).toHaveAttribute('dir', 'ltr')
  })
})
