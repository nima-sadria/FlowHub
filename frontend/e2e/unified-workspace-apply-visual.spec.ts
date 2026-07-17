import { expect, test, type Page, type Route } from '@playwright/test'

const channel = {
  channelId: 'woocommerce:primary',
  displayName: 'WooCommerce',
  readPrice: true, writePrice: true, readStock: true, writeStock: true,
  readStatus: true, writeStatus: false, supportsMultipleListings: false,
  maximumBatchSize: 100, rateLimitPerMinute: null, healthState: 'configured',
  primaryIdentifierType: 'woocommerce_product_id', supportedStatuses: ['active'],
  currency: 'EUR', unit: 'EUR', writeAvailable: true, version: 'visual-fixture-v1',
}
const visibleChannels = [channel, ...['snappshop:main', 'woocommerce:store_eu', 'snappshop:tehran', 'tapsishop:main'].map((channelId, index) => ({
  ...channel,
  channelId,
  displayName: undefined,
  instanceLabel: index === 0 ? 'Main' : undefined,
}))]

function resultFor(scenario: string) {
  const status = scenario === 'reconciliation' ? 'reconciliation_required' : scenario === 'partial' ? 'partially_applied' : 'applied'
  const itemStatus = scenario === 'reconciliation' ? 'reconciliation_required' : scenario === 'partial' ? 'failed' : 'applied'
  return {
    id: `mock-apply-${scenario}`, workspaceId: 'visual-apply', status,
    correlationId: `mock-correlation-${scenario}`,
    items: [{ id: 'review-item-1', listingId: 'listing-1', channelId: channel.channelId, field: 'price', status: itemStatus, errorMessage: scenario === 'partial' ? 'Mock provider rejection' : scenario === 'reconciliation' ? 'Provider outcome is uncertain' : null, cacheSyncStatus: scenario === 'success' ? 'verified' : null }],
  }
}

const resultPresentation = {
  success: { job: 'Applied', item: 'Applied' },
  partial: { job: 'Partially Applied', item: 'Failed' },
  reconciliation: { job: 'Reconciliation Required', item: 'Reconciliation Required' },
} as const

const groupedListings = visibleChannels.map((item, index) => {
  const isApplyTarget = item.channelId === channel.channelId
  const currentPrice = String(100 + index * 10)
  return {
    listingId: isApplyTarget ? 'listing-1' : `listing-${index + 1}`,
    channelId: item.channelId,
    listingLabel: isApplyTarget ? 'Synthetic Listing' : `Synthetic Listing ${index + 1}`,
    externalId: `external-${index + 1}`,
    externalIdType: 'product_id',
    sku: `SYN-${index + 1}`,
    mappingState: 'resolved',
    cacheFreshness: 'fresh',
    state: isApplyTarget ? 'ready' : 'unchanged',
    changedFields: isApplyTarget ? ['price'] : [],
    selected: false,
    reviewItemIds: [],
    fields: {
      price: { current: currentPrice, target: isApplyTarget ? '125' : currentPrice, changed: isApplyTarget, readOnly: false, status: isApplyTarget ? 'ready' : 'unchanged', currency: 'EUR', unit: 'EUR' },
      stock: { current: '5', target: '5', changed: false, readOnly: false, status: 'unchanged', currency: null, unit: null },
      status: { current: 'active', target: 'active', changed: false, readOnly: true, status: 'unchanged', currency: null, unit: null },
    },
  }
})

async function installApplyFixture(page: Page, scenario = 'success') {
  await page.addInitScript(() => localStorage.setItem('wp_token', 'visual-isolated-token'))
  await page.route('**/*', async (route: Route) => {
    const url = new URL(route.request().url())
    if (!url.pathname.startsWith('/api/')) return route.continue()
    const json = (body: unknown) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
    if (url.pathname === '/api/v2/setup/status') return json({ completed: true })
    if (url.pathname === '/api/auth/me') return json({ username: 'visual-admin', role: 'admin', is_admin: true, is_super_admin: false, permissions: { can_access_site: true, can_fetch: true, can_view_logs: true, can_view_settings: true }, maintenance: { enabled: false, message: '' } })
    if (url.pathname === '/api/v2/products/categories') return json({ items: [] })
    if (url.pathname === '/api/v2/source-profiles/channels') return json({ items: visibleChannels.map(item => ({ channelId: item.channelId, name: item.displayName ?? item.channelId, connectorType: item.channelId.split(':')[0], capabilityVersion: item.version, capabilities: { writePrice: item.writePrice, writeStock: item.writeStock, writeStatus: item.writeStatus, writeAvailable: item.writeAvailable, supportedStatuses: item.supportedStatuses, currency: item.currency, unit: item.unit }, enabled: true, implementationState: 'implemented', available: true })) })
    if (url.pathname === '/api/v2/unified-workspaces/preferences/me') return json({ visibleChannelIds: visibleChannels.map(item => item.channelId), channelOrder: visibleChannels.map(item => item.channelId), visibleFields: { price: true, stock: true, status: true, sku: true }, displayNameSource: 'canonical', version: 1 })
    if (url.pathname === '/api/v2/unified-workspaces/visual-apply') return json({ id: 'visual-apply', name: 'Visual Apply Fixture', entryPoint: 'manual', ownerUserId: 1, status: 'active', version: 1, snapshot: { id: 'visual-snapshot', checksum: 's'.repeat(64), schemaVersion: '1', createdAt: new Date().toISOString() }, draft: { id: 'visual-draft', version: 1, currentRevisionId: 'revision-1', status: 'draft' }, createdAt: new Date().toISOString() })
    if (url.pathname === '/api/v2/unified-workspaces/visual-apply/grid') return json({ total: 1, page: 1, pageSize: 500, draftVersion: 1, revisionId: 'revision-1', channels: visibleChannels, items: [{ rowId: 'visual-row-1', canonicalProductId: 'product-1', canonicalName: 'Synthetic Product', displayName: 'Synthetic Product', productType: 'simple', listingId: 'listing-1', listingLabel: 'Synthetic Listing', channelId: channel.channelId, externalPrimaryId: 'external-1', externalIdType: 'product_id', sku: 'SYN-1', mappingState: 'resolved', mappingVersion: 1, cacheVersion: 1, cacheFreshness: 'fresh', fields: { price: { current: '100', target: '125', status: 'ready', readOnly: false, currency: 'EUR', unit: 'EUR' }, stock: { current: '5', target: '5', status: 'unchanged', readOnly: false, currency: null, unit: null }, status: { current: 'active', target: 'active', status: 'read_only', readOnly: true, currency: null, unit: null } } }] })
    if (url.pathname === '/api/v2/unified-workspaces/visual-apply/grouped-grid') return json({
      items: [{ sourceProductId: 'product-1', name: 'Synthetic Product', sourceKey: 'SYN-1', cost: null, category: null, brand: null, productType: 'simple', mappedChannelCount: visibleChannels.length, listingCount: groupedListings.length, changedListingCount: 1, selectedListingCount: 0, state: 'ready', children: groupedListings }],
      total: 1, page: 1, pageSize: 100, view: 'all', summary: { ready: 1, blocked: 0, unchanged: 0, selected: 0 }, draftVersion: 1, revisionId: 'revision-1', reviewId: null, reviewStatus: null, selectionChecksum: null,
    })
    if (url.pathname === '/api/v2/unified-workspaces/visual-apply/draft/revisions') return json({ id: 'revision-2', revisionNumber: 2, checksum: 'd'.repeat(64), draftVersion: 2 })
    if (url.pathname === '/api/v2/unified-workspaces/visual-apply/reviews') return json({ id: 'review-1', workspaceId: 'visual-apply', snapshotId: 'visual-snapshot', draftRevisionId: 'revision-1', status: 'ready', checksum: 'r'.repeat(64), summary: { total: 1, eligible: 1, blocked: 0, warnings: 0 }, items: [{ id: 'review-item-1', canonicalProductId: 'product-1', listingId: 'listing-1', channelId: channel.channelId, field: 'price', current: '100', target: '125', validationState: 'ready', warnings: [], errors: [], eligible: true, selected: false }], staleReason: null })
    if (url.pathname.endsWith('/selection')) return json({ reviewId: 'review-1', selectedItemIds: ['review-item-1'], selectionChecksum: 'c'.repeat(64), selectionVersion: 1 })
    if (url.pathname === '/api/v2/unified-workspaces/visual-apply/apply') return json(resultFor(scenario))
    return route.fulfill({ status: 404, contentType: 'application/json', body: '{}' })
  })
}

for (const scenario of ['success', 'partial', 'reconciliation']) {
  test(`renders mocked ${scenario} Apply result without external writes`, async ({ page }) => {
    await installApplyFixture(page, scenario)
    await page.goto(`/workspace/visual-apply?result=${scenario}`)
    await expect(page).toHaveURL('/products?workspace=visual-apply')
    await expect(page.locator('[data-pricing-grid]')).toBeVisible()
    const checkbox = page.locator('.ht_master td[data-listing-id="listing-1"][data-field-selection][data-field="price"] input').first()
    await expect(checkbox).toBeChecked()
    await page.locator('[data-pricing-review]').click()
    await expect(page.getByRole('heading', { name: 'Review Changes' })).toBeVisible()
    await expect(page.locator('[data-local-pricing-review]')).toBeVisible()
    await page.getByRole('button', { name: /Back to grid/i }).click()
    await page.locator('[data-pricing-dry-run]').click()
    await expect(page.getByRole('heading', { name: 'Review Changes' })).toBeVisible()
    await page.getByRole('button', { name: /Back to grid/i }).click()
    await page.locator('[data-pricing-apply]').click()
    await page.getByRole('button', { name: /Confirm Apply/i }).click()
    const results = page.getByRole('region', { name: 'Apply results' })
    const expected = resultPresentation[scenario as keyof typeof resultPresentation]
    await expect(results.getByRole('heading')).toContainText(expected.job)
    await expect(results.locator('strong')).toHaveText(expected.item)
    await page.screenshot({ path: `test-results/visual-remediation/apply-${scenario}.png`, fullPage: true })
  })
}

test('captures the mocked Workspace and Apply states at supported desktop viewports', async ({ page }) => {
  await installApplyFixture(page)
  for (const viewport of [{ width: 1280, height: 720 }, { width: 1366, height: 768 }, { width: 1440, height: 900 }, { width: 1920, height: 1080 }]) {
    await page.setViewportSize(viewport)
    await page.goto('/workspace/visual-apply?result=success')
    await expect(page).toHaveURL('/products?workspace=visual-apply')
    await expect(page.locator('[data-pricing-grid]')).toBeVisible()
    const suffix = `${viewport.width}x${viewport.height}`
    await expect.poll(() => gridOverflow(page)).toBe(true)
    await page.screenshot({ path: `test-results/visual-remediation/workspace-${suffix}.png`, fullPage: true })
    const grid = page.locator('.fh-grid-scroll')
    await grid.evaluate(element => { element.scrollLeft = element.scrollWidth })
    await page.screenshot({ path: `test-results/visual-remediation/grid-scrolled-${suffix}.png`, fullPage: true })
    await page.locator('[data-pricing-review]').click()
    await expect(page.locator('[data-local-pricing-review]')).toBeVisible()
    await page.getByRole('button', { name: /Back to grid/i }).click()
    await page.locator('[data-pricing-dry-run]').click()
    await expect(page.getByRole('heading', { name: 'Review Changes' })).toBeVisible()
    await page.getByRole('button', { name: /Back to grid/i }).click()
    await page.locator('[data-pricing-apply]').click()
    await page.getByRole('button', { name: /Confirm Apply/i }).click()
    const results = page.getByRole('region', { name: 'Apply results' })
    await expect(results.getByRole('heading')).toContainText(resultPresentation.success.job)
    await expect(results.locator('strong')).toHaveText(resultPresentation.success.item)
    await page.screenshot({ path: `test-results/visual-remediation/apply-success-${suffix}.png`, fullPage: true })
  }
})

async function gridOverflow(page: Page): Promise<boolean> {
  return page.locator('.fh-grid-scroll').evaluate(element => element.scrollWidth > element.clientWidth)
}

test('captures the primary application routes with isolated synthetic APIs', async ({ page }) => {
  await installApplyFixture(page)
  for (const route of ['home', 'products', 'workspace/visual-apply', 'activity', 'settings', 'diagnostics', 'commerce']) {
    await page.goto(`/${route}`)
    await page.waitForTimeout(250)
    await page.screenshot({ path: `test-results/visual-remediation/route-${route.replaceAll('/', '-')}-1280x720.png`, fullPage: true })
  }
})
