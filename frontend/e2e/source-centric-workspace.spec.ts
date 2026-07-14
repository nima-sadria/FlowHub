import path from 'node:path'
import { readFileSync } from 'node:fs'
import { expect, test, type Page, type Route } from '@playwright/test'

const screenshotRoot = path.resolve('..', 'docs', 'screenshots', 'v1.3')
const mockLogo = readFileSync(path.resolve('public', 'flowhub-logo.png'))
const viewports = [
  { width: 1280, height: 720 },
  { width: 1366, height: 768 },
  { width: 1440, height: 900 },
  { width: 1920, height: 1080 },
]

function fields(current: string, target: string, status: 'ready' | 'blocked' | 'unchanged' = 'ready', unit: string | null = null) {
  return { current, target, changed: current !== target, readOnly: status === 'blocked', status, currency: unit ? 'IRR' : null, unit }
}

async function installMockApi(page: Page) {
  await page.addInitScript(() => localStorage.setItem('wp_token', 'source-centric-isolated-token'))
  await page.route('**/*', async (route: Route) => {
    const url = new URL(route.request().url())
    if (url.pathname.startsWith('/static/logos/')) return route.fulfill({ status: 200, contentType: 'image/png', body: mockLogo })
    if (!url.pathname.startsWith('/api/')) return route.continue()
    const json = (body: unknown, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
    if (url.pathname === '/api/v2/setup/status') return json({ completed: true })
    if (url.pathname === '/api/auth/me') return json({ username: 'visual-owner', role: 'admin', is_admin: true, is_super_admin: false, permissions: { can_access_site: true, can_fetch: true, can_view_logs: true, can_view_settings: true }, maintenance: { enabled: false, message: '' } })
    if (url.pathname === '/api/health') return json({ status: 'ok' })
    if (url.pathname === '/api/v2/source-profiles') return json({ items: [{ id: 'source-visual', name: 'Daily multi-channel prices', sourceKind: 'flowhub_sheet', externalSourceId: null, worksheetMode: 'selected', worksheetName: 'Sheet1', dataStartRow: 2, status: 'active', version: 2, mappingVersion: 1, sheetId: 'sheet-visual' }] })
    if (url.pathname === '/api/v2/source-profiles/channels') return json({ items: [{ channelId: 'woocommerce:primary', name: 'WooCommerce', connectorType: 'woocommerce', capabilityVersion: '1', capabilities: {} }, { channelId: 'snappshop:main', name: 'SnappShop', connectorType: 'snappshop', capabilityVersion: '1', capabilities: {} }, { channelId: 'tapsishop:main', name: 'TapsiShop', connectorType: 'tapsishop', capabilityVersion: '1', capabilities: {} }] })
    if (url.pathname === '/api/v2/sources/source-visual/configuration') return json({ id: 'source-visual', name: 'Daily multi-channel prices', sourceKind: 'flowhub_sheet', externalSourceId: null, worksheetMode: 'selected', worksheetName: 'Sheet1', dataStartRow: 2, status: 'active', version: 2, mappingVersion: 1, sheetId: 'sheet-visual', mapping: { id: 'mapping-1', version: 1, checksum: 'a'.repeat(64), worksheetMode: 'selected', worksheetName: 'Sheet1', dataStartRow: 2, valuePolicy: { blank: 'no_change', x: 'unavailable', zero: 'explicit_zero' }, sourceFields: [{ field: 'name', referenceType: 'column_id', referenceValue: 'name', required: true }, { field: 'source_key', referenceType: 'column_id', referenceValue: 'key', required: false }], channels: [{ channelId: 'woocommerce:primary', worksheetName: null, enabled: true, fields: [{ field: 'external_id', referenceType: 'column_id', referenceValue: 'wc-id' }, { field: 'price', referenceType: 'column_id', referenceValue: 'wc-price' }] }, { channelId: 'snappshop:main', worksheetName: null, enabled: true, fields: [{ field: 'external_id', referenceType: 'column_id', referenceValue: 'snap-id' }, { field: 'price', referenceType: 'column_id', referenceValue: 'snap-price' }] }] } })
    if (url.pathname === '/api/v2/sheets/sheet-visual') {
      const pageNumber = Number(url.searchParams.get('page') ?? 1)
      return json({ id: 'sheet-visual', sourceId: 'source-visual', name: 'Daily multi-channel prices', version: 4, revisionId: 'sheet-revision-4', revisionChecksum: 'b'.repeat(64), formulaEngineVersion: 'flowhub-formula-1', columns: [{ columnKey: 'name', name: 'Product Name', position: 1, dataType: 'text' }, { columnKey: 'key', name: 'Source Key', position: 2, dataType: 'text' }, { columnKey: 'cost', name: 'Cost', position: 3, dataType: 'number' }, { columnKey: 'target', name: 'Target Formula', position: 4, dataType: 'number' }], rows: Array.from({ length: 200 }, (_, index) => { const position = (pageNumber - 1) * 200 + index + 1; return { rowKey: `row-${position}`, position, cells: { name: { raw: `Product ${position}`, value: `Product ${position}`, formula: null, error: null }, key: { raw: `SRC-${position}`, value: `SRC-${position}`, formula: null, error: null }, cost: { raw: String(1000 + position), value: String(1000 + position), formula: null, error: null }, target: { raw: '=C1*1.2', value: String((1000 + position) * 1.2), formula: '=C1*1.2', error: null } } } }), total: 10_000, page: pageNumber, pageSize: 200 })
    }
    if (url.pathname === '/api/v2/unified-workspaces/source-visual-workspace') return json({ id: 'source-visual-workspace', name: 'Daily pricing', entryPoint: 'source', sourceType: 'flowhub_sheet', ownerUserId: 1, status: 'active', version: 1, snapshot: { id: 'snapshot-source-visual', checksum: 'c'.repeat(64), schemaVersion: 'uw-snapshot-1', createdAt: new Date().toISOString() }, draft: { id: 'draft-source', version: 1, currentRevisionId: 'revision-source', status: 'reviewed' }, createdAt: new Date().toISOString() })
    if (url.pathname === '/api/v2/unified-workspaces/source-visual-workspace/grid') return json({ items: [], total: 0, page: 1, pageSize: 500, channels: [], draftVersion: 1, revisionId: 'revision-source' })
    if (url.pathname === '/api/v2/unified-workspaces/preferences/me') return json({ visibleChannelIds: ['woocommerce:primary', 'snappshop:main', 'tapsishop:main'], channelOrder: ['woocommerce:primary', 'snappshop:main', 'tapsishop:main'], visibleFields: { price: true, stock: true, status: true, sku: true }, displayNameSource: 'canonical', version: 1 })
    if (url.pathname === '/api/v2/unified-workspaces/source-visual-workspace/reviews/review-source') return json({
      id: 'review-source',
      workspaceId: 'source-visual-workspace',
      snapshotId: 'snapshot-source-visual',
      draftRevisionId: 'revision-source',
      status: 'ready',
      checksum: 'e'.repeat(64),
      summary: { total: 3, eligible: 2, blocked: 1, warnings: 0 },
      items: [
        { id: 'review-wc', canonicalProductId: 'product-cable', listingId: 'wc-cable', channelId: 'woocommerce:primary', field: 'price', current: '12000', target: '12500', validationState: 'ready', warnings: [], errors: [], eligible: true, selected: true },
        { id: 'review-snap', canonicalProductId: 'product-cable', listingId: 'snap-white', channelId: 'snappshop:main', field: 'price', current: '12600', target: '12900', validationState: 'ready', warnings: [], errors: [], eligible: true, selected: true },
        { id: 'review-snap-blocked', canonicalProductId: 'product-cable', listingId: 'snap-black', channelId: 'snappshop:main', field: 'price', current: '12600', target: '12900', validationState: 'blocked', warnings: [], errors: ['CHANNEL_CACHE_STALE'], eligible: false, selected: false },
      ],
      staleReason: null,
    })
    if (url.pathname === '/api/v2/unified-workspaces/source-visual-workspace/reviews/review-source/selection' && route.request().method() === 'PUT') return json({ reviewId: 'review-source', selectedItemIds: ['review-wc'], selectionChecksum: 'f'.repeat(64), selectionVersion: 2 })
    if (url.pathname === '/api/v2/unified-workspaces/source-visual-workspace/grouped-grid') {
      const requestedView = url.searchParams.get('view') ?? 'changed'
      const products = [{ sourceProductId: 'product-cable', name: 'iPhone Cable', sourceKey: 'CABLE-01', cost: '11000', category: 'Accessories', brand: null, productType: 'simple', mappedChannelCount: 3, listingCount: 4, changedListingCount: 3, selectedListingCount: 2, state: 'ready', children: [{ listingId: 'wc-cable', channelId: 'woocommerce:primary', listingLabel: 'Main Listing', externalId: '101', externalIdType: 'product_id', sku: 'CABLE', mappingState: 'resolved', cacheFreshness: 'fresh', state: 'ready', changedFields: ['price'], selected: true, reviewItemIds: ['review-wc'], fields: { price: fields('12000', '12500', 'ready', 'TOMAN'), stock: fields('8', '8', 'unchanged'), status: fields('publish', 'publish', 'unchanged') } }, { listingId: 'snap-white', channelId: 'snappshop:main', listingLabel: 'White Listing', externalId: 'SN-11', externalIdType: 'product_number', sku: 'CABLE-W', mappingState: 'resolved', cacheFreshness: 'fresh', state: 'ready', changedFields: ['price'], selected: true, reviewItemIds: ['review-snap'], fields: { price: fields('12600', '12900', 'ready', 'TOMAN'), stock: fields('5', '5', 'unchanged'), status: fields('active', 'active', 'unchanged') } }, { listingId: 'snap-black', channelId: 'snappshop:main', listingLabel: 'Black Listing', externalId: 'SN-12', externalIdType: 'product_number', sku: 'CABLE-B', mappingState: 'resolved', cacheFreshness: 'stale', state: 'blocked', changedFields: ['price'], selected: false, reviewItemIds: [], fields: { price: fields('12600', '12900', 'blocked', 'TOMAN'), stock: fields('0', '0', 'unchanged'), status: fields('inactive', 'inactive', 'unchanged') } }, { listingId: 'tapsi-main', channelId: 'tapsishop:main', listingLabel: 'Main Listing', externalId: 'TP-22', externalIdType: 'seller_sku', sku: 'CABLE', mappingState: 'resolved', cacheFreshness: 'fresh', state: 'unchanged', changedFields: [], selected: false, reviewItemIds: [], fields: { price: fields('12700', '12700', 'unchanged', 'TOMAN'), stock: fields('4', '4', 'unchanged'), status: fields('active', 'active', 'unchanged') } }] }]
      return json({ items: requestedView === 'unchanged' ? [] : products, total: 10_000, page: 1, pageSize: 100, view: requestedView, summary: { ready: 28, blocked: 12, unchanged: 1376, selected: 26 }, draftVersion: 1, revisionId: 'revision-source', reviewId: 'review-source', reviewStatus: 'ready', selectionChecksum: 'd'.repeat(64) })
    }
    if (url.pathname === '/api/v2/data-quality') return json({ items: [{ id: 'issue-1', channelId: 'snappshop:main', category: 'stale_cache', severity: 'blocked', code: 'CHANNEL_CACHE_STALE', summary: 'SnappShop cache is too old for a safe Review.', recommendedAction: 'Refresh the isolated Channel cache, then generate a new Review.', technicalDetails: { cacheVersion: 4, maximumAge: '15m' } }, { id: 'issue-2', channelId: 'woocommerce:primary', category: 'invalid_price', severity: 'error', code: 'INVALID_NUMERIC_VALUE', summary: 'Source row 42 contains text in the Price field.', recommendedAction: 'Enter a numeric price or leave the mapped cell blank.', technicalDetails: { row: 42 } }], counts: { stale_cache: 1, invalid_price: 1 }, total: 2 })
    if (url.pathname.includes('/apply')) return json({ id: 'mock-apply', workspaceId: 'source-visual-workspace', status: 'applied', correlationId: 'mock-only', items: [] })
    return json({}, 404)
  })
}

test('source-centric daily Workspace is understandable and responsive with isolated mock APIs', async ({ page }) => {
  await installMockApi(page)
  for (const viewport of viewports) {
    await page.setViewportSize(viewport)
    await page.goto('/workspace/source-visual-workspace')
    await expect(page.getByText('iPhone Cable')).toBeVisible()
    await expect(page.getByText('28', { exact: true })).toBeVisible()
    await expect(page.getByText('12', { exact: true })).toBeVisible()
    await expect(page.getByText('White Listing')).toBeVisible()
    await expect(page.getByText('Black Listing')).toBeVisible()
    await page.screenshot({ path: path.join(screenshotRoot, `workspace-${viewport.width}x${viewport.height}.png`), fullPage: true })
  }
  const selectionRequest = page.waitForRequest(request => request.method() === 'PUT' && new URL(request.url()).pathname.endsWith('/reviews/review-source/selection'))
  await page.getByRole('checkbox', { name: 'Select SnappShop White Listing' }).click()
  const selectionPayload = JSON.parse((await selectionRequest).postData() ?? '{}') as { review_item_ids?: string[] }
  expect(selectionPayload.review_item_ids).toEqual(['review-wc'])
  await page.getByRole('button', { name: /Apply 26 selected/ }).click()
  await expect(page.getByRole('dialog', { name: 'Apply confirmation' })).toBeVisible()
  await page.screenshot({ path: path.join(screenshotRoot, 'apply-confirmation.png'), fullPage: true })
})

test('Source configuration, FlowHub Sheet, import, and Data Quality render from synthetic data', async ({ page }) => {
  await installMockApi(page)
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/sources/source-visual')
  await expect(page.getByText('Source Product fields')).toBeVisible()
  await expect(page.getByRole('heading', { name: 'WooCommerce' })).toBeVisible()
  await page.screenshot({ path: path.join(screenshotRoot, 'source-configuration.png'), fullPage: true })
  await page.goto('/sheets/sheet-visual')
  await expect(page.getByText('10,000 rows')).toBeVisible()
  expect(await page.locator('[data-row-key]').count()).toBeLessThan(40)
  await page.screenshot({ path: path.join(screenshotRoot, 'flowhub-sheet.png'), fullPage: true })
  await page.goto('/sources/import')
  await expect(page.getByText('Choose XLSX or CSV')).toBeVisible()
  await page.screenshot({ path: path.join(screenshotRoot, 'import-wizard.png'), fullPage: true })
  await page.goto('/data-quality')
  await page.getByText('stale cache', { exact: true }).click()
  await expect(page.getByText('SnappShop cache is too old for a safe Review.')).toBeVisible()
  await page.screenshot({ path: path.join(screenshotRoot, 'data-quality.png'), fullPage: true })
})
