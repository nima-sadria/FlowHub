import path from 'node:path'
import { mkdirSync, readFileSync } from 'node:fs'
import { expect, test, type Locator, type Page, type Route } from '@playwright/test'

const screenshotRoot = path.resolve('..', 'docs', 'screenshots', 'v1.3', 'source-channel-ordering')
mkdirSync(screenshotRoot, { recursive: true })

const mockLogo = readFileSync(path.resolve('public', 'flowhub-logo.png'))

const sourceOrder = [
  'source-csv',
  'source-google',
  'source-nextcloud',
  'source-disabled',
  'source-erp',
] as const

const channelOrder = [
  'snappshop:main',
  'tapsishop:main',
  'woocommerce:primary',
  'attention:main',
  'disabled:main',
  'digikala:future',
] as const

const sourceProfiles = [
  sourceProfile('source-erp', 'ERP / API', 'coming_soon', 'external'),
  sourceProfile('source-nextcloud', 'Nextcloud', 'error', 'external'),
  sourceProfile('source-disabled', 'Old CSV', 'disabled', 'imported_sheet'),
  sourceProfile('source-google', 'Google Sheets', 'active', 'external'),
  sourceProfile('source-csv', 'CSV', 'active', 'imported_sheet'),
]

const sourceChannels = [
  sourceChannel('digikala:future', 'Digikala', false, false, 'coming_soon'),
  sourceChannel('woocommerce:primary', 'WooCommerce', true, true, 'implemented'),
  sourceChannel('disabled:main', 'Disabled Store', false, true, 'implemented'),
  sourceChannel('attention:main', 'Alpha attention', true, true, 'warning'),
  sourceChannel('tapsishop:main', 'TapsiShop', true, true, 'implemented'),
  sourceChannel('snappshop:main', 'SnappShop', true, true, 'implemented'),
]

const commerceSources = [
  commerceSource('source-nextcloud', 'nextcloud', 'Nextcloud', 'warning', 'warning'),
  commerceSource('source-erp', 'erp', 'ERP / API', 'planned', 'unknown', false, true),
  commerceSource('source-google', 'google_sheets', 'Google Sheets', 'configured', 'healthy'),
  commerceSource('source-disabled', 'csv', 'Old CSV', 'disabled', 'unknown'),
  commerceSource('source-csv', 'csv', 'CSV', 'configured', 'healthy'),
]

const commerceChannels = [
  commerceChannel('attention:main', 'attention', 'Alpha attention', 'warning', 'warning'),
  commerceChannel('digikala:future', 'digikala', 'Digikala', 'planned', 'unknown', false, true),
  commerceChannel('woocommerce:primary', 'woocommerce', 'WooCommerce', 'operational', 'healthy'),
  commerceChannel('disabled:main', 'disabled', 'Disabled Store', 'disabled', 'unknown'),
  commerceChannel('snappshop:main', 'snappshop', 'SnappShop', 'operational', 'healthy'),
  commerceChannel('tapsishop:main', 'tapsishop', 'TapsiShop', 'operational', 'healthy'),
]

const workspaceChannels = [
  workspaceChannel('digikala:future', 'Digikala', 'coming_soon', false),
  workspaceChannel('woocommerce:primary', 'WooCommerce', 'healthy'),
  workspaceChannel('attention:main', 'Alpha attention', 'warning'),
  workspaceChannel('disabled:main', 'Disabled Store', 'disabled', false),
  workspaceChannel('tapsishop:main', 'TapsiShop', 'healthy'),
  workspaceChannel('snappshop:main', 'SnappShop', 'healthy'),
]

interface MockAudit {
  externalRequests: string[]
  unhandledApiRequests: string[]
  interceptedWrites: string[]
}

function sourceProfile(
  id: string,
  name: string,
  status: string,
  sourceKind: 'flowhub_sheet' | 'imported_sheet' | 'external',
) {
  return {
    id,
    name,
    sourceKind,
    externalSourceId: sourceKind === 'external' ? id : null,
    worksheetMode: 'selected',
    worksheetName: 'Prices',
    dataStartRow: 2,
    status,
    version: 4,
    mappingVersion: id === 'source-csv' ? 3 : 0,
    sheetId: sourceKind === 'external' ? null : `sheet-${id}`,
  }
}

function sourceChannel(
  channelId: string,
  name: string,
  enabled: boolean,
  available: boolean,
  implementationState: string,
) {
  const writeAvailable = enabled && available && implementationState === 'implemented'
  return {
    channelId,
    name,
    connectorType: channelId.split(':')[0],
    capabilityVersion: 'ordering-v1',
    // Match the production WorkspaceChannel capability document. The dense
    // pricing grid intentionally fails closed when this evidence is absent.
    capabilities: {
      writePrice: writeAvailable,
      writeStock: false,
      writeStatus: false,
      writeAvailable,
      supportedStatuses: ['active', 'inactive'],
      currency: 'IRR',
      unit: 'IRR',
    },
    enabled,
    implementationState,
    available,
  }
}

function commerceSource(
  id: string,
  provider: string,
  name: string,
  status: string,
  healthStatus: string,
  implemented = true,
  placeholder = false,
) {
  return {
    id,
    provider,
    name,
    type: 'Source',
    status,
    implemented,
    placeholder,
    credential_status: implemented && !placeholder ? 'configured' : 'not_configured',
    last_health_check: implemented ? '2026-07-15T08:00:00Z' : null,
    data_role: 'Synthetic ordering fixture',
    action_label: 'Configure',
    action_href: '',
    health: { status: healthStatus, message: 'Synthetic local status', latency_ms: 12, error_code: null },
    read_policy: {
      enabled: implemented,
      max_reads_per_24h: 10,
      manual_read_allowed: implemented,
      reads_used_last_24h: 1,
      reads_remaining: 9,
      reset_at: null,
      last_read_at: implemented ? '2026-07-15T07:30:00Z' : null,
    },
    read_status: {
      enabled: implemented,
      max_reads_per_24h: 10,
      manual_read_allowed: implemented,
      reads_used_last_24h: 1,
      reads_remaining: 9,
      reset_at: null,
      last_read_at: implemented ? '2026-07-15T07:30:00Z' : null,
      last_read_status: status === 'warning' ? 'completed_with_warnings' : implemented ? 'completed' : null,
      last_row_count: implemented ? 30 : null,
      last_warning_count: status === 'warning' ? 1 : 0,
      last_error_count: 0,
    },
    read_only: true,
    runtime_write_blocked: true,
    settings_available: implemented,
  }
}

function commerceChannel(
  id: string,
  provider: string,
  name: string,
  status: string,
  healthStatus: string,
  implemented = true,
  placeholder = false,
) {
  return {
    id,
    provider,
    name,
    type: 'Channel',
    status,
    implemented,
    placeholder,
    read_only: true,
    write_blocked: true,
    runtime_write_blocked: true,
    credential_status: implemented && !placeholder ? 'configured' : 'not_configured',
    configuration_state: implemented ? 'configured' : 'not_configured',
    credentials_configured: implemented,
    credentials_verified: implemented,
    vendor_selected: implemented,
    vendor_accessible: implemented,
    token_configured: implemented,
    webhook_token_configured: false,
    last_health_check: implemented ? '2026-07-15T08:00:00Z' : null,
    health: { status: healthStatus, message: 'Synthetic local status', latency_ms: 15, error_code: null },
    capabilities: { products_read: implemented, price_write: false },
    capabilities_summary: implemented ? ['Product read'] : [],
    settings_available: implemented,
    cached_products: implemented ? 30 : 0,
    cached_variations: 0,
    last_cache_refresh: implemented ? '2026-07-15T07:45:00Z' : null,
    cache_refresh_status: status === 'warning' ? 'completed_with_warnings' : implemented ? 'completed' : 'not_run',
  }
}

function workspaceChannel(
  channelId: string,
  displayName: string,
  healthState: string,
  writeAvailable = true,
) {
  return {
    channelId,
    displayName,
    instanceLabel: null,
    readPrice: true,
    writePrice: writeAvailable,
    readStock: true,
    writeStock: false,
    readStatus: true,
    writeStatus: false,
    supportsMultipleListings: true,
    maximumBatchSize: 50,
    rateLimitPerMinute: 30,
    healthState,
    primaryIdentifierType: 'external_id',
    supportedStatuses: ['active', 'inactive'],
    currency: 'IRR',
    unit: 'IRR',
    writeAvailable,
    version: 'ordering-v1',
  }
}

function commerceTypes(kind: 'Source' | 'Channel') {
  const candidates = kind === 'Source'
    ? [
        ['source-type-erp', 'erp', 'ERP / API', false, true],
        ['source-type-nextcloud', 'nextcloud', 'Nextcloud', true, false],
        ['source-type-google', 'google_sheets', 'Google Sheets', true, false],
        ['source-type-csv', 'csv', 'CSV', true, false],
      ] as const
    : [
        ['channel-type-woocommerce', 'woocommerce', 'WooCommerce', true, false],
        ['channel-type-digikala', 'digikala', 'Digikala', false, true],
        ['channel-type-snappshop', 'snappshop', 'SnappShop', true, false],
      ] as const
  return candidates.map(([id, provider, name, implemented, placeholder]) => ({
    id,
    provider,
    name,
    type: kind,
    implemented,
    placeholder,
    read_only: true,
    write_blocked: true,
    runtime_write_blocked: true,
    settings_schema: [],
  }))
}

function sourceConfiguration() {
  const mappedIds = channelOrder.filter(id => id !== 'digikala:future')
  return {
    ...sourceProfiles.find(item => item.id === 'source-csv'),
    mapping: {
      id: 'mapping-ordering-v3',
      version: 3,
      checksum: 'a'.repeat(64),
      worksheetMode: 'selected',
      worksheetName: 'Prices',
      selectedWorksheetNames: ['Prices'],
      dataStartRow: 2,
      worksheetRuleMode: 'shared',
      duplicateProductPolicy: 'block',
      worksheetRules: [],
      valuePolicy: {
        blank: 'no_change',
        x: 'unavailable',
        dash: 'no_change',
        zero: 'explicit_zero',
        formula: 'calculated_value',
        invalid: 'blocked',
      },
      sourceFields: [{ field: 'name', referenceType: 'column_letter', referenceValue: 'A', required: true }],
      channels: mappedIds.map((channelId, index) => ({
        channelId,
        worksheetName: null,
        enabled: !channelId.startsWith('disabled:'),
        fields: [
          { field: 'external_id', referenceType: 'column_letter', referenceValue: String.fromCharCode(66 + index) },
          { field: 'price', referenceType: 'column_letter', referenceValue: String.fromCharCode(72 + index) },
          { field: 'stock', referenceType: 'disabled', referenceValue: null },
          { field: 'status', referenceType: 'disabled', referenceValue: null },
        ],
      })),
    },
    legacyMapping: null,
  }
}

function workspaceGroupedGrid() {
  return {
    items: [{
      sourceProductId: 'product-ordering-1',
      name: 'Synthetic Cable',
      sourceKey: 'SYN-1',
      cost: null,
      category: null,
      brand: null,
      productType: 'simple',
      mappedChannelCount: 1,
      listingCount: 1,
      changedListingCount: 1,
      selectedListingCount: 0,
      state: 'ready',
      children: [{
        listingId: 'listing-ordering-1',
        channelId: 'snappshop:main',
        listingLabel: 'Synthetic Listing',
        externalId: 'SYN-1',
        externalIdType: 'product_number',
        sku: 'SYN-1',
        mappingState: 'resolved',
        cacheFreshness: 'fresh',
        state: 'ready',
        changedFields: ['price'],
        selected: false,
        reviewItemIds: [],
        fields: {
          price: { current: '100', target: '110', changed: true, readOnly: false, status: 'ready', currency: 'IRR', unit: 'IRR' },
          stock: { current: '5', target: '5', changed: false, readOnly: true, status: 'unchanged', currency: null, unit: null },
          status: { current: 'active', target: 'active', changed: false, readOnly: true, status: 'unchanged', currency: null, unit: null },
        },
      }],
    }],
    total: 1,
    page: 1,
    pageSize: 100,
    view: 'all',
    summary: {
      ready: 1,
      blocked: 0,
      unchanged: 0,
      selected: 0,
    },
    draftVersion: 1,
    revisionId: 'revision-ordering',
    reviewId: null,
    reviewStatus: null,
    selectionChecksum: null,
  }
}

function workspaceGrid() {
  return {
    total: 1,
    page: 1,
    pageSize: 500,
    draftVersion: 1,
    revisionId: 'revision-ordering',
    channels: workspaceChannels,
    items: [{
      rowId: 'row-ordering-1',
      canonicalProductId: 'product-ordering-1',
      canonicalName: 'Synthetic Cable',
      displayName: 'Synthetic Cable',
      productType: 'simple',
      listingId: 'listing-ordering-1',
      listingLabel: 'Synthetic Listing',
      channelId: 'snappshop:main',
      externalPrimaryId: 'SYN-1',
      externalIdType: 'product_number',
      sku: 'SYN-1',
      mappingState: 'resolved',
      mappingVersion: 1,
      cacheVersion: 1,
      cacheFreshness: 'fresh',
      fields: {
        price: { current: '100', target: '110', status: 'ready', readOnly: false, currency: 'IRR', unit: 'IRR' },
        stock: { current: '5', target: '5', status: 'unchanged', readOnly: true, currency: null, unit: null },
        status: { current: 'active', target: 'active', status: 'read_only', readOnly: true, currency: null, unit: null },
      },
    }],
  }
}

function dataQualityResponse() {
  return {
    items: [{
      id: 'issue-ordering-1',
      sourceId: 'source-nextcloud',
      worksheet: 'Prices',
      sourceProductName: 'Synthetic Cable',
      channelId: 'attention:main',
      mappingState: 'resolved',
      category: 'invalid_value',
      severity: 'warning',
      code: 'INVALID_NUMERIC_VALUE',
      summary: 'Synthetic fixture issue.',
      recommendedAction: 'Use a numeric value.',
      technicalDetails: { row: 2 },
    }],
    counts: { invalid_value: 1 },
    total: 1,
    summary: {
      state: 'issues_found',
      totalIssues: 1,
      blockingIssues: 0,
      warnings: 1,
      affectedProducts: 1,
      affectedChannels: 1,
      affectedSources: 1,
      resolvedSinceLastRead: 0,
      trendSinceLastRead: 0,
      productsChecked: 1,
      sourcesChecked: 5,
      checkedAt: '2026-07-15T08:00:00Z',
      scanId: 'scan-ordering',
      errorCode: null,
      categories: [{ category: 'invalid_value', count: 1 }],
    },
  }
}

async function installStrictMockApi(page: Page, audit: MockAudit, locale: 'en' | 'fa') {
  await page.addInitScript(({ selectedLocale }) => {
    localStorage.setItem('wp_token', 'ordering-visual-isolated-token')
    localStorage.setItem('flowhub.locale', selectedLocale)
  }, { selectedLocale: locale })

  await page.route('**/*', async (route: Route) => {
    const request = route.request()
    const url = new URL(request.url())

    if (!['127.0.0.1', 'localhost'].includes(url.hostname)) {
      audit.externalRequests.push(`${request.method()} ${request.url()}`)
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

    if (
      request.method() === 'POST'
      && url.pathname === '/api/v2/unified-workspaces/manual'
      && request.postDataJSON()?.catalog_scope !== undefined
    ) {
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'ordering-workspace',
          name: 'Ordering Workspace',
          entryPoint: 'manual',
          ownerUserId: 1,
          status: 'active',
          version: 1,
          snapshot: { id: 'snapshot-ordering', checksum: 'b'.repeat(64), schemaVersion: '1', createdAt: '2026-07-15T08:00:00Z' },
          draft: { id: 'draft-ordering', version: 1, currentRevisionId: 'revision-ordering', status: 'draft' },
          createdAt: '2026-07-15T08:00:00Z',
        }),
      })
      return
    }
    if (request.method() !== 'GET') {
      audit.interceptedWrites.push(`${request.method()} ${url.pathname}`)
      await route.fulfill({
        status: 405,
        contentType: 'application/json',
        body: JSON.stringify({ code: 'MOCK_WRITE_BLOCKED', message: 'Writes are disabled in the ordering visual fixture.' }),
      })
      return
    }

    const json = (body: unknown, status = 200) => route.fulfill({
      status,
      contentType: 'application/json',
      body: JSON.stringify(body),
    })
    const pathname = url.pathname

    if (pathname === '/api/v2/setup/status') return json({ completed: true })
    if (pathname === '/api/auth/me') return json({
      username: 'ordering-owner',
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
    if (pathname === '/api/health') return json({ status: 'ok', version: 'ordering-isolated' })
    if (pathname === '/api/v2/source-profiles') return json({ items: sourceProfiles })
    if (pathname === '/api/v2/source-profiles/channels') return json({ items: sourceChannels })
    if (pathname === '/api/v2/sources/source-csv/configuration') return json(sourceConfiguration())
    if (pathname === '/api/v2/commerce/sources') return json({
      items: commerceSources,
      relationship_map: {
        nodes: ['Source', 'FlowHub / Data Layer', 'Channel'],
        example: ['CSV', 'Data Layer', 'WooCommerce'],
        runtime_write_blocked: true,
        read_only: true,
      },
    })
    if (pathname === '/api/v2/commerce/channels') return json({ items: commerceChannels })
    if (pathname === '/api/v2/commerce/source-types') return json({ items: commerceTypes('Source') })
    if (pathname === '/api/v2/commerce/channel-types') return json({ items: commerceTypes('Channel') })
    if (pathname === '/api/v2/unified-workspaces/ordering-workspace') return json({
      id: 'ordering-workspace',
      name: 'Ordering Workspace',
      entryPoint: 'manual',
      ownerUserId: 1,
      status: 'active',
      version: 1,
      snapshot: { id: 'snapshot-ordering', checksum: 'b'.repeat(64), schemaVersion: '1', createdAt: '2026-07-15T08:00:00Z' },
      draft: { id: 'draft-ordering', version: 1, currentRevisionId: 'revision-ordering', status: 'draft' },
      createdAt: '2026-07-15T08:00:00Z',
    })
    if (pathname === '/api/v2/unified-workspaces/ordering-workspace/grid') return json(workspaceGrid())
    if (pathname === '/api/v2/unified-workspaces/ordering-workspace/grouped-grid') return json(workspaceGroupedGrid())
    if (pathname === '/api/v2/unified-workspaces/preferences/me') return json({
      visibleChannelIds: ['snappshop:main'],
      channelOrder: [...channelOrder].reverse(),
      visibleFields: { price: true, stock: true, status: true, sku: true },
      displayNameSource: 'canonical',
      version: 1,
    })
    if (pathname === '/api/v2/products/categories') return json({ items: [] })
    if (pathname === '/api/v2/products') return json({
      items: [{
        id: 'product-row-ordering-1',
        productId: 'product-ordering-1',
        connectorId: 'snappshop:main',
        name: 'Synthetic Cable',
        sku: 'SYN-1',
        currentPrice: 100,
        sourcePrice: 110,
        currency: 'IRR',
        categoryNames: [],
        imageUrl: null,
        productType: 'simple',
        status: 'synced',
        lastSynced: '2026-07-15T08:00:00Z',
      }],
      total: 1,
      page: 1,
      pageSize: 20,
      configured: true,
    })
    if (pathname === '/api/v2/data-quality') return json(dataQualityResponse())

    audit.unhandledApiRequests.push(`${request.method()} ${request.url()}`)
    return json({ code: 'UNHANDLED_ISOLATED_MOCK', message: 'The isolated ordering fixture does not implement this request.' }, 501)
  })
}

async function expectGroupedOrder(page: Page, expectedIds: readonly string[]) {
  const resourceIds = page.locator('[data-resource-section] [data-resource-id]')
  await expect(resourceIds.first()).toBeVisible()
  expect(await resourceIds.evaluateAll(elements => elements.map(element => element.getAttribute('data-resource-id')))).toEqual(expectedIds)
  expect(await page.locator('[data-resource-section]').evaluateAll(elements => elements.map(element => element.getAttribute('data-resource-section')))).toEqual([
    'active',
    'disabled',
    'comingSoon',
  ])
}

async function openSourceConfigurationChannelColumns(page: Page) {
  const section = page.locator('details:has([data-resource-id="snappshop:main"])').first()
  if (await section.getAttribute('open') === null) await section.locator(':scope > summary').click()
}

async function expectGroupedChannelOptions(select: Locator) {
  expect(await select.locator('option').evaluateAll(options => options.map(option => (option as HTMLOptionElement).value))).toEqual([
    '',
    ...channelOrder,
  ])
  expect(await select.locator('optgroup').evaluateAll(groups => groups.map(group => (
    Array.from((group as HTMLOptGroupElement).querySelectorAll('option')).map(option => option.value)
  )))).toEqual([
    ['snappshop:main', 'tapsishop:main', 'woocommerce:primary', 'attention:main'],
    ['disabled:main'],
    ['digikala:future'],
  ])
}

async function expectNoUnsafeTraffic(audit: MockAudit) {
  expect(audit.externalRequests).toEqual([])
  expect(audit.unhandledApiRequests).toEqual([])
  expect(audit.interceptedWrites).toEqual([])
}

test('all Source and Channel workflow surfaces share the same grouped order and safe defaults', async ({ page }) => {
  const audit: MockAudit = { externalRequests: [], unhandledApiRequests: [], interceptedWrites: [] }
  await installStrictMockApi(page, audit, 'en')
  await page.setViewportSize({ width: 1440, height: 900 })

  await page.goto('/sources')
  await expectGroupedOrder(page, sourceOrder)
  await expect(page.locator('[data-resource-id="source-csv"]')).toContainText('Healthy')
  await expect(page.locator('[data-resource-id="source-nextcloud"]')).toContainText('Warning')
  await expect(page.locator('[data-resource-id="source-disabled"]')).toContainText('Disabled')
  await expect(page.locator('[data-resource-id="source-erp"]')).toContainText('Coming Soon')
  await page.screenshot({ path: path.join(screenshotRoot, 'en-sources.png'), fullPage: true })

  await page.goto('/commerce?tab=sources')
  await expectGroupedOrder(page, sourceOrder)
  await page.getByRole('button', { name: 'Add Source' }).click()
  const typeSelector = page.getByLabel('Source type')
  await expect(typeSelector).toHaveValue('source-type-csv')
  expect(await typeSelector.locator('option').evaluateAll(options => options.map(option => ({
    value: (option as HTMLOptionElement).value,
    selected: (option as HTMLOptionElement).selected,
  })))).toEqual([
    { value: 'source-type-csv', selected: true },
    { value: 'source-type-google', selected: false },
    { value: 'source-type-nextcloud', selected: false },
    { value: 'source-type-erp', selected: false },
  ])
  await page.screenshot({ path: path.join(screenshotRoot, 'en-commerce-source-selector.png'), fullPage: true })
  await page.getByRole('button', { name: 'Close' }).click()

  await page.getByRole('button', { name: 'Channels' }).click()
  await expectGroupedOrder(page, channelOrder)
  await expect(page.locator('[data-resource-id="snappshop:main"]')).toContainText('Healthy')
  await expect(page.locator('[data-resource-id="attention:main"]')).toContainText('Warning')
  await expect(page.locator('[data-resource-id="disabled:main"]')).toContainText('Disabled')
  await expect(page.locator('[data-resource-id="digikala:future"]')).toContainText('Coming Soon')
  await page.screenshot({ path: path.join(screenshotRoot, 'en-commerce-channels.png'), fullPage: true })

  await page.goto('/sources/source-csv')
  await openSourceConfigurationChannelColumns(page)
  await expectGroupedOrder(page, channelOrder)
  const copySelector = page.getByLabel('Copy columns from another Channel').first()
  await expect(copySelector).toHaveValue('')
  await page.screenshot({ path: path.join(screenshotRoot, 'en-source-configuration.png'), fullPage: true })

  await page.goto('/workspace/ordering-workspace')
  await expectGroupedOrder(page, channelOrder)
  // Resource chips expose availability; field-level checkboxes exist only for
  // Listings that actually participate in the dense pricing grid. Disabled
  // and Coming Soon Channels must never receive a selectable/editable cell.
  await expect(page.locator('[data-resource-id="disabled:main"]')).toContainText('Disabled')
  await expect(page.locator('[data-resource-id="digikala:future"]')).toContainText('Coming Soon')
  await expect(page.locator('.ht_master [data-channel-id="disabled:main"]')).toHaveCount(0)
  await expect(page.locator('.ht_master [data-channel-id="digikala:future"]')).toHaveCount(0)
  const activeSelection = page.locator('.ht_master input[data-channel-id="snappshop:main"][data-listing-id="listing-ordering-1"]')
  await expect(activeSelection).toHaveCount(3)
  await expect(page.locator('.ht_master input[data-channel-id="snappshop:main"][data-listing-id="listing-ordering-1"]:checked')).toHaveCount(1)
  const workspaceChannelFilter = page.locator('select[name="channelId"]')
  await expect(workspaceChannelFilter).toHaveValue('')
  await expectGroupedChannelOptions(workspaceChannelFilter)
  await page.screenshot({ path: path.join(screenshotRoot, 'en-workspace.png'), fullPage: true })

  const productChannelRequest = page.waitForRequest(request => (
    request.method() === 'GET' && new URL(request.url()).pathname === '/api/v2/source-profiles/channels'
  ))
  await page.goto('/products')
  await productChannelRequest
  const productChannelFilter = page.locator('select').filter({ has: page.locator('option[value="snappshop:main"]') }).first()
  await expect(productChannelFilter).toHaveValue('')
  await expectGroupedChannelOptions(productChannelFilter)
  expect(await productChannelFilter.locator('option').evaluateAll(options => options.map(option => option.textContent?.trim()))).toEqual([
    'All Channels',
    'SnappShop',
    'TapsiShop',
    'WooCommerce',
    'Alpha attention',
    'Disabled Store',
    'Digikala',
  ])
  await page.screenshot({ path: path.join(screenshotRoot, 'en-products.png'), fullPage: true })

  await page.goto('/data-quality')
  const filters = page.locator('details').filter({ hasText: 'Filters' })
  await filters.locator('summary').click()
  const sourceFilter = filters.getByLabel('Source')
  const channelFilter = filters.getByLabel('Channel')
  await expect(sourceFilter).toHaveValue('')
  await expect(channelFilter).toHaveValue('')
  expect(await sourceFilter.locator('option').evaluateAll(options => options.map(option => (option as HTMLOptionElement).value))).toEqual(['', ...sourceOrder])
  expect(await channelFilter.locator('option').evaluateAll(options => options.map(option => (option as HTMLOptionElement).value))).toEqual(['', ...channelOrder])

  await page.goto('/sources/import')
  await expect(page.getByText('Choose XLSX or CSV')).toBeVisible()
  await expect(page.locator('html')).toHaveAttribute('dir', 'ltr')
  await page.screenshot({ path: path.join(screenshotRoot, 'en-import-wizard.png'), fullPage: true })

  await expectNoUnsafeTraffic(audit)
})

test('the same ordering remains stable in Persian RTL without translating technical identities', async ({ page }) => {
  const audit: MockAudit = { externalRequests: [], unhandledApiRequests: [], interceptedWrites: [] }
  await installStrictMockApi(page, audit, 'fa')
  await page.setViewportSize({ width: 1440, height: 900 })

  const routes = [
    ['sources', '/sources', sourceOrder],
    ['commerce-channels', '/commerce?tab=channels', channelOrder],
    ['source-configuration', '/sources/source-csv', channelOrder],
    ['workspace', '/workspace/ordering-workspace', channelOrder],
  ] as const

  for (const [name, route, expectedOrder] of routes) {
    await page.goto(route)
    await expect(page.locator('html')).toHaveAttribute('lang', 'fa')
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl')
    if (name === 'source-configuration') await openSourceConfigurationChannelColumns(page)
    await expectGroupedOrder(page, expectedOrder)
    await expect(page.locator('[data-resource-section="active"]')).not.toHaveAttribute('aria-label', 'Active')
    await page.screenshot({ path: path.join(screenshotRoot, `fa-${name}.png`), fullPage: true })
  }

  await page.goto('/products')
  await expect(page.locator('html')).toHaveAttribute('lang', 'fa')
  await expect(page.locator('html')).toHaveAttribute('dir', 'rtl')
  const productChannelFilter = page.locator('select').filter({ has: page.locator('option[value="snappshop:main"]') }).first()
  await expect(productChannelFilter).toHaveValue('')
  await expectGroupedChannelOptions(productChannelFilter)
  await expect(productChannelFilter.locator('option[value="woocommerce:primary"]')).toHaveText('WooCommerce')
  await expect(productChannelFilter.locator('option[value="snappshop:main"]')).toHaveText('SnappShop')
  await page.screenshot({ path: path.join(screenshotRoot, 'fa-products.png'), fullPage: true })

  await expectNoUnsafeTraffic(audit)
})
