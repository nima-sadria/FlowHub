import path from 'node:path'
import { mkdirSync, copyFileSync } from 'node:fs'
import { expect, test, type Page, type Route } from '@playwright/test'

test.use({ video: 'on' })

const screenshotRoot = path.resolve('..', 'docs', 'screenshots', 'v1.3', 'pricing-workflow-redesign')
const videoRoot = path.resolve('..', 'docs', 'videos', 'v1.3', 'pricing-workflow-redesign')
mkdirSync(screenshotRoot, { recursive: true })
mkdirSync(videoRoot, { recursive: true })

interface Audit { external: string[]; writes: string[]; draftChanges: string[]; selected: string[] }

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({ status, contentType: 'application/json; charset=utf-8', body: JSON.stringify(body) })
}

function workspace() {
  return {
    id: 'pricing-workspace', name: 'Bulk Pricing Workspace', entryPoint: 'manual', ownerUserId: 1, status: 'active', version: 1,
    snapshot: { id: 'snapshot-pricing', checksum: 's'.repeat(64), schemaVersion: 'uw-snapshot-1', createdAt: '2026-07-16T08:00:00Z' },
    draft: { id: 'draft-pricing', version: 1, currentRevisionId: null, status: 'draft' }, createdAt: '2026-07-16T08:00:00Z',
  }
}

function groupedGrid(selectedCount: number, reviewId: string | null = null) {
  const items = Array.from({ length: 50 }, (_, index) => {
    const productId = `product-${index + 1}`
    const children = ['woocommerce:primary', 'snappshop:main', 'tapsishop:main'].map((channelId, channelIndex) => {
      const listingId = `listing-${index + 1}-${channelIndex + 1}`
      const current = String(1000 + index * 10 + channelIndex)
      return {
        listingId, channelId, listingLabel: channelIndex === 0 ? 'Primary' : 'Main', externalId: `${50000 + index * 10 + channelIndex}`, externalIdType: 'product_id', sku: `SKU-${index + 1}`,
        mappingState: 'resolved', cacheFreshness: 'fresh', state: 'ready', changedFields: ['price'], selected: index < selectedCount && channelIndex === 0,
        reviewItemIds: reviewId && index < 20 && channelIndex === 0 ? [`review-${index + 1}`] : [],
        fields: {
          price: { current, target: current, changed: false, readOnly: false, status: 'ready', currency: 'IRR', unit: 'IRR' },
          stock: { current: String(20 + index), target: String(20 + index), changed: false, readOnly: false, status: 'ready', currency: null, unit: null },
          status: { current: 'publish', target: 'publish', changed: false, readOnly: false, status: 'ready', currency: null, unit: null },
        },
      }
    })
    return { sourceProductId: productId, name: `Synthetic Product ${index + 1}`, sourceKey: `SRC-${index + 1}`, cost: null, category: 'Accessories', brand: 'FlowHub', productType: 'simple', mappedChannelCount: 3, listingCount: 3, changedListingCount: 3, selectedListingCount: index < selectedCount ? 1 : 0, state: 'ready', children }
  })
  return { items, total: 50, page: 1, pageSize: 100, view: 'all', summary: { ready: 20, blocked: 3, unchanged: 27, selected: selectedCount }, draftVersion: 1, revisionId: reviewId ? 'revision-pricing' : null, reviewId, reviewStatus: reviewId ? 'ready' : null, selectionChecksum: reviewId ? 'selection-checksum' : null }
}

async function installMocks(page: Page, audit: Audit) {
  await page.addInitScript(() => localStorage.setItem('wp_token', 'pricing-workflow-isolated-token'))
  await page.route('**/*', async route => {
    const request = route.request()
    const url = new URL(request.url())
    const method = request.method().toUpperCase()
    if (!['127.0.0.1', 'localhost'].includes(url.hostname)) { audit.external.push(`${method} ${url.href}`); return route.abort('blockedbyclient') }
    if (!url.pathname.startsWith('/api/')) return route.continue()
    if (method !== 'GET') audit.writes.push(`${method} ${url.pathname}`)
    if (url.pathname === '/api/v2/setup/status') return json(route, { completed: true })
    if (url.pathname === '/api/auth/me') return json(route, { username: 'pricing-owner', role: 'admin', is_admin: true, is_super_admin: false, permissions: { can_access_site: true, can_fetch: true, can_view_logs: true, can_view_settings: true }, maintenance: { enabled: false, message: '' } })
    if (url.pathname === '/api/health') return json(route, { status: 'ok', env: 'test' })
    if (url.pathname === '/api/v2/source-profiles/channels') return json(route, { items: [
      { channelId: 'woocommerce:primary', name: 'WooCommerce', connectorType: 'woocommerce', capabilityVersion: '1', capabilities: {}, enabled: true, implementationState: 'implemented', available: true },
      { channelId: 'snappshop:main', name: 'SnappShop', connectorType: 'snappshop', capabilityVersion: '1', capabilities: {}, enabled: true, implementationState: 'implemented', available: true },
      { channelId: 'tapsishop:main', name: 'TapsiShop', connectorType: 'tapsishop', capabilityVersion: '1', capabilities: {}, enabled: true, implementationState: 'implemented', available: true },
    ] })
    if (url.pathname === '/api/v2/products') return json(route, { items: Array.from({ length: 50 }, (_, index) => ({ id: String(index + 1), productId: String(index + 1), name: `Synthetic Product ${index + 1}`, sku: `SKU-${index + 1}`, connectorId: 'woocommerce:primary', currentPrice: 1000 + index * 10, currency: 'IRR', productType: 'simple', categoryNames: ['Accessories'], imageUrl: null })), total: 50, page: Number(url.searchParams.get('page') ?? 1), pageSize: 50, configured: true })
    if (url.pathname === '/api/v2/unified-workspaces/manual' && method === 'POST') return json(route, workspace())
    if (url.pathname === '/api/v2/unified-workspaces/pricing-workspace') return json(route, workspace())
    if (url.pathname === '/api/v2/unified-workspaces/pricing-workspace/grid') return json(route, { items: [], total: 0, page: 1, pageSize: 500, channels: [], draftVersion: 1, revisionId: null })
    if (url.pathname === '/api/v2/unified-workspaces/preferences/me') return json(route, { visibleChannelIds: ['woocommerce:primary', 'snappshop:main', 'tapsishop:main'], channelOrder: ['woocommerce:primary', 'snappshop:main', 'tapsishop:main'], visibleFields: {}, displayNameSource: 'canonical', version: 1 })
    if (url.pathname === '/api/v2/unified-workspaces/pricing-workspace/grouped-grid') { const selected = audit.selected.length ? 9 : audit.draftChanges.length; return json(route, groupedGrid(selected, audit.draftChanges.length ? 'review-pricing' : null)) }
    if (url.pathname === '/api/v2/unified-workspaces/pricing-workspace/draft/revisions' && method === 'POST') {
      const body = JSON.parse(request.postData() ?? '{}') as { changes?: Array<{ listing_id: string }> }
      audit.draftChanges = (body.changes ?? []).map(change => change.listing_id)
      return json(route, { id: 'revision-pricing', revisionNumber: 1, checksum: 'revision-checksum', draftVersion: 2 })
    }
    if (url.pathname === '/api/v2/unified-workspaces/pricing-workspace/reviews' && method === 'POST') {
      return json(route, { id: 'review-pricing', workspaceId: 'pricing-workspace', snapshotId: 'snapshot-pricing', draftRevisionId: 'revision-pricing', status: 'ready', checksum: 'review-checksum', summary: { total: audit.draftChanges.length, eligible: audit.draftChanges.length, blocked: 0, warnings: 0 }, items: audit.draftChanges.map((listingId, index) => ({ id: `review-${index + 1}`, canonicalProductId: `product-${index + 1}`, listingId, channelId: 'woocommerce:primary', field: 'price', current: '1000', target: String(1100 + index), validationState: 'ready', warnings: [], errors: [], eligible: true, selected: true })), staleReason: null })
    }
    if (url.pathname === '/api/v2/unified-workspaces/pricing-workspace/reviews/review-pricing') return json(route, { id: 'review-pricing', workspaceId: 'pricing-workspace', snapshotId: 'snapshot-pricing', draftRevisionId: 'revision-pricing', status: 'ready', checksum: 'review-checksum', summary: { total: audit.draftChanges.length, eligible: audit.draftChanges.length, blocked: 0, warnings: 0 }, items: audit.draftChanges.map((listingId, index) => ({ id: `review-${index + 1}`, canonicalProductId: `product-${index + 1}`, listingId, channelId: 'woocommerce:primary', field: 'price', current: '1000', target: String(1100 + index), validationState: 'ready', warnings: [], errors: [], eligible: true, selected: true })), staleReason: null })
    if (url.pathname === '/api/v2/unified-workspaces/pricing-workspace/reviews/review-pricing/selection' && method === 'PUT') { audit.selected = ['listing-1-1', ...audit.draftChanges.slice(1)]; return json(route, { reviewId: 'review-pricing', selectedItemIds: audit.selected, selectionChecksum: 'selection-checksum', selectionVersion: 2 }) }
    if (url.pathname === '/api/v2/unified-workspaces/pricing-workspace/apply' && method === 'POST') return json(route, { id: 'apply-pricing', workspaceId: 'pricing-workspace', status: 'partially_applied', correlationId: 'pricing-mock-correlation', items: [{ id: 'apply-1', listingId: audit.selected[0] ?? 'listing-1-1', channelId: 'woocommerce:primary', field: 'price', status: 'applied', errorMessage: null, cacheSyncStatus: 'verified' }, { id: 'apply-2', listingId: audit.selected[1] ?? 'listing-2-1', channelId: 'woocommerce:primary', field: 'price', status: 'reconciliation_required', errorMessage: 'Provider response uncertain', cacheSyncStatus: 'pending' }] })
    return json(route, { code: 'UNHANDLED_TEST_REQUEST' }, 500)
  })
}

test('seller can edit many products inline, review once, and run mocked Dry Run/Apply', async ({ page }, testInfo) => {
  test.setTimeout(120_000)
  const audit: Audit = { external: [], writes: [], draftChanges: [], selected: [] }
  await installMocks(page, audit)
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/products')
  await expect(page.getByRole('heading', { name: 'Pricing workspace' })).toBeVisible()
  await page.getByRole('button', { name: 'Select visible' }).click()
  await page.getByRole('button', { name: 'Open pricing workspace' }).click()
  await expect(page.getByText('Synthetic Product 1', { exact: true })).toBeVisible()
  const parents = page.locator('article')
  for (let index = 0; index < 10; index += 1) {
    const parent = parents.nth(index).locator('button[aria-expanded]').first()
    if (await parent.getAttribute('aria-expanded') === 'false') {
      await parent.click()
      await expect(parent).toHaveAttribute('aria-expanded', 'true')
    }
  }
  const priceInputs = page.locator('input[data-target-field="price"]')
  await expect(priceInputs).toHaveCount(30)
  await page.screenshot({ path: path.join(screenshotRoot, 'pricing-grid-inline-edit.png'), fullPage: true })
  for (let index = 0; index < 10; index += 1) await priceInputs.nth(index).fill(String(2200 + index * 100))
  await page.evaluate(() => {
    const input = document.querySelector<HTMLInputElement>('input[data-target-field="price"]')
    if (!input) throw new Error('price input not found')
    const data = new DataTransfer(); data.setData('text/plain', ['2300', '2400', '2500', '2600', '2700'].join('\n'))
    input.dispatchEvent(new ClipboardEvent('paste', { bubbles: true, clipboardData: data }))
  })
  const stockInputs = page.locator('input[data-target-field="stock"]')
  await stockInputs.nth(0).fill('11')
  await stockInputs.nth(1).fill('12')
  await expect(page.getByText(/unsaved edits/)).toBeVisible()
  await page.getByRole('searchbox', { name: 'Search Source Products' }).fill('Synthetic Product 2')
  await page.getByRole('searchbox', { name: 'Search Source Products' }).fill('')
  await page.getByRole('button', { name: /Review & Dry Run/ }).click()
  await expect(page.getByRole('heading', { name: 'Review Changes' })).toBeVisible()
  expect(audit.draftChanges.length).toBeGreaterThanOrEqual(10)
  await page.screenshot({ path: path.join(screenshotRoot, 'review-and-dry-run.png'), fullPage: true })
  const listingCheckbox = page.getByRole('checkbox', { name: /Select WooCommerce/ }).first()
  if (await listingCheckbox.isChecked()) await listingCheckbox.click()
  await expect(page.getByRole('button', { name: /Apply 9 selected/ })).toBeVisible()
  await page.getByRole('button', { name: /Apply 9 selected/ }).click()
  await expect(page.getByRole('dialog', { name: 'Apply confirmation' })).toBeVisible()
  await page.screenshot({ path: path.join(screenshotRoot, 'apply-confirmation.png'), fullPage: true })
  await page.getByRole('button', { name: 'Confirm Apply' }).click()
  await expect(page.getByText(/partially applied/i)).toBeVisible()
  await expect(page.getByText(/Reconciliation Required/i)).toBeVisible()
  await page.screenshot({ path: path.join(screenshotRoot, 'apply-partial-reconciliation.png'), fullPage: true })
  expect(audit.external).toEqual([])
  expect(audit.writes.some(pathname => pathname.endsWith('/apply'))).toBe(true)
  expect(audit.draftChanges.length).toBeGreaterThanOrEqual(10)
  const video = testInfo.attachments.find(attachment => attachment.name === 'video' && attachment.path)
  if (video?.path) copyFileSync(video.path, path.join(videoRoot, 'pricing-workflow-redesign.webm'))
})
