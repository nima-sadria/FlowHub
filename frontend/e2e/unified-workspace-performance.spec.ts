import os from 'node:os'
import { expect, test, type Page, type Route } from '@playwright/test'

const TOTAL_PRODUCTS = 10_000
const PAGE_SIZE = 500
const channels = Array.from({ length: 5 }, (_, index) => ({
  channelId: `configured-channel-${index + 1}`,
  readPrice: true,
  writePrice: true,
  readStock: true,
  writeStock: true,
  readStatus: true,
  writeStatus: false,
  supportsMultipleListings: index > 0,
  maximumBatchSize: index === 1 ? 50 : 100,
  rateLimitPerMinute: null,
  healthState: 'configured',
  primaryIdentifierType: 'external_product_id',
  supportedStatuses: ['active', 'inactive'],
  currency: index === 1 ? 'IRR' : 'EUR',
  unit: index === 1 ? 'TOMAN' : 'EUR',
  writeAvailable: true,
  version: 'benchmark-v1',
}))

function row(index: number) {
  const channel = channels[index % channels.length]
  return {
    rowId: `row-${index}`,
    canonicalProductId: `product-${Math.floor(index / 2)}`,
    canonicalName: `Product ${String(index).padStart(5, '0')}`,
    displayName: `Product ${String(index).padStart(5, '0')}`,
    productType: index % 25 === 0 ? 'variation' : 'simple',
    listingId: `listing-${index}`,
    listingLabel: `Listing ${index}`,
    channelId: channel.channelId,
    externalPrimaryId: `external-${index}`,
    externalIdType: 'external_product_id',
    sku: `SKU-${index}`,
    mappingState: 'resolved',
    mappingVersion: 1,
    cacheVersion: 1,
    cacheFreshness: 'fresh',
    fields: {
      price: { current: String(1000 + index), target: String(1000 + index), status: index % 7 === 0 ? 'warning' : 'ready', readOnly: false, currency: channel.currency, unit: channel.unit },
      stock: { current: String(index % 40), target: String(index % 40), status: 'ready', readOnly: false, currency: null, unit: null },
      status: { current: 'active', target: 'active', status: 'read_only', readOnly: true, currency: null, unit: null },
    },
  }
}

function groupedProduct(index: number) {
  const item = row(index)
  return {
    sourceProductId: item.canonicalProductId,
    name: item.canonicalName,
    sourceKey: item.sku,
    cost: null,
    category: null,
    brand: null,
    productType: item.productType,
    mappedChannelCount: 1,
    listingCount: 1,
    changedListingCount: 0,
    selectedListingCount: 0,
    state: 'unchanged',
    children: [{
      listingId: item.listingId,
      channelId: item.channelId,
      listingLabel: item.listingLabel,
      externalId: item.externalPrimaryId,
      externalIdType: item.externalIdType,
      sku: item.sku,
      mappingState: item.mappingState,
      cacheFreshness: item.cacheFreshness,
      state: 'unchanged',
      changedFields: [],
      selected: false,
      reviewItemIds: [],
      fields: {
        price: { ...item.fields.price, changed: false, status: 'unchanged' },
        stock: { ...item.fields.stock, changed: false, status: 'unchanged' },
        status: { ...item.fields.status, changed: false, status: 'unchanged' },
      },
    }],
  }
}

const sourceChannels = channels.map((item, index) => ({
  channelId: item.channelId,
  name: `Configured Channel ${index + 1}`,
  connectorType: 'synthetic',
  capabilityVersion: item.version,
  capabilities: {
    writePrice: item.writePrice,
    writeStock: item.writeStock,
    writeStatus: item.writeStatus,
    writeAvailable: item.writeAvailable,
    supportedStatuses: item.supportedStatuses,
    currency: item.currency,
    unit: item.unit,
  },
  enabled: true,
  implementationState: 'implemented',
  available: true,
}))

async function installApi(page: Page) {
  const requests: URL[] = []
  await page.addInitScript(() => {
    localStorage.setItem('wp_token', 'isolated-browser-token')
  })
  await page.route('**/*', async (route: Route) => {
    const url = new URL(route.request().url())
    if (!url.pathname.startsWith('/api/')) return route.continue()
    requests.push(url)
    const json = (body: unknown) => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(body),
    })
    if (url.pathname === '/api/v2/setup/status') return json({ completed: true })
    if (url.pathname === '/api/auth/me') return json({
      username: 'browser-admin', role: 'admin', is_admin: true, is_super_admin: false,
      permissions: { can_access_site: true, can_fetch: true, can_view_logs: true, can_view_settings: true },
      maintenance: { enabled: false, message: '' },
    })
    if (url.pathname === '/api/v2/source-profiles/channels') return json({ items: sourceChannels })
    if (url.pathname === '/api/v2/unified-workspaces/preferences/me') return json({
      visibleChannelIds: channels.map(item => item.channelId),
      channelOrder: channels.map(item => item.channelId),
      visibleFields: { price: true, stock: true, status: true, sku: true },
      displayNameSource: 'canonical', version: 1,
    })
    if (url.pathname === '/api/v2/unified-workspaces/browser-benchmark') return json({
      id: 'browser-benchmark', name: '10,000 Product Benchmark', entryPoint: 'manual',
      ownerUserId: 1, status: 'active', version: 1,
      snapshot: { id: 'snapshot-browser', checksum: 'a'.repeat(64), schemaVersion: '1', createdAt: new Date().toISOString() },
      draft: { id: 'draft-browser', version: 0, currentRevisionId: null, status: 'draft' },
      createdAt: new Date().toISOString(),
    })
    if (url.pathname === '/api/v2/unified-workspaces/browser-benchmark/grid') {
      const requestedPage = Number(url.searchParams.get('page') ?? 1)
      const search = (url.searchParams.get('search') ?? '').toLowerCase()
      const start = (requestedPage - 1) * PAGE_SIZE
      let items = Array.from({ length: PAGE_SIZE }, (_, offset) => row(start + offset))
      if (search) items = items.filter(item => item.canonicalName.toLowerCase().includes(search))
      return json({
        items,
        total: search ? items.length : TOTAL_PRODUCTS,
        page: requestedPage,
        pageSize: PAGE_SIZE,
        channels,
        draftVersion: 0,
        revisionId: null,
      })
    }
    if (url.pathname === '/api/v2/unified-workspaces/browser-benchmark/grouped-grid') {
      const requestedPage = Number(url.searchParams.get('page') ?? 1)
      const requestedSize = Math.min(Number(url.searchParams.get('pageSize') ?? 100), 500)
      const search = (url.searchParams.get('search') ?? '').toLowerCase()
      const all = Array.from({ length: TOTAL_PRODUCTS }, (_, index) => index)
      const matching = search ? all.filter(index => `product ${String(index).padStart(5, '0')}`.includes(search)) : all
      const indexes = matching.slice((requestedPage - 1) * requestedSize, requestedPage * requestedSize)
      return json({ items: indexes.map(groupedProduct), total: matching.length, page: requestedPage, pageSize: requestedSize, view: 'all', summary: { ready: 0, blocked: 0, unchanged: matching.length, selected: 0 }, draftVersion: 0, revisionId: null, reviewId: null, reviewStatus: null, selectionChecksum: null })
    }
    return route.fulfill({ status: 404, contentType: 'application/json', body: '{}' })
  })
  return requests
}

test('virtualizes a paged 10,000-product, five-channel Workspace in Chromium', async ({ page, browser, browserName }) => {
  const requests = await installApi(page)
  page.on('console', message => console.log(`browser:${message.type()}:${message.text()}`))
  page.on('pageerror', error => console.log(`browser-error:${error.message}`))
  page.on('response', response => {
    if (response.status() >= 400) console.log(`browser-response:${response.status()}:${response.url()}`)
  })
  const started = performance.now()
  const workspaceResponse = page.waitForResponse(response => {
    const url = new URL(response.url())
    return url.pathname === '/api/v2/unified-workspaces/browser-benchmark'
  })
  await page.goto('/workspace/browser-benchmark', { waitUntil: 'domcontentloaded' })
  expect((await workspaceResponse).status()).toBe(200)
  // CI browsers can spend several seconds compiling the Handsontable chunk;
  // wait for the API-backed readiness signal rather than racing the default
  // five-second locator timeout.
  await expect(page.getByText('10,000 Product Benchmark')).toBeVisible({ timeout: 30_000 })
  await expect(page.locator('[data-pricing-grid]')).toBeVisible()
  const readyMs = Math.round(performance.now() - started)
  const initialRows = await page.locator('.ht_master tbody tr').count()
  expect(initialRows).toBeGreaterThan(0)
  expect(initialRows).toBeLessThan(100)
  expect(requests.some(url => url.pathname.endsWith('/grouped-grid') && url.searchParams.get('pageSize') === '100')).toBe(true)
  expect(requests.some(url => url.pathname.endsWith('/grouped-grid') && url.searchParams.get('pageSize') === '10000')).toBe(false)

  const scrollStarted = performance.now()
  await page.locator('.wtHolder').last().evaluate(element => { element.scrollTop = element.scrollHeight })
  await page.waitForTimeout(100)
  const scrollMs = Math.round(performance.now() - scrollStarted)
  expect(await page.locator('.ht_master tbody tr').count()).toBeLessThan(100)

  await page.getByRole('button', { name: 'Next' }).click()
  await expect(page.getByText('Page 2 of 100')).toBeVisible()
  expect(requests.some(url => url.pathname.endsWith('/grouped-grid') && url.searchParams.get('page') === '2')).toBe(true)

  await page.getByRole('searchbox', { name: /Search Source Products/i }).fill('Product 00500')
  await page.getByRole('button', { name: 'Filter server data' }).click()
  await expect(page.getByText('Page 1 of 1')).toBeVisible()
  expect(requests.some(url => url.searchParams.get('search') === 'Product 00500')).toBe(true)

  const metrics = await page.evaluate(() => ({
    heap: (performance as Performance & { memory?: { usedJSHeapSize: number } }).memory?.usedJSHeapSize ?? null,
    domNodes: document.getElementsByTagName('*').length,
  }))
  console.log(JSON.stringify({
    browserName,
    browserVersion: browser.version(),
    operatingSystem: `${os.platform()} ${os.release()}`,
    cpu: os.cpus()[0]?.model ?? 'unknown',
    logicalCpuCount: os.cpus().length,
    totalMemoryBytes: os.totalmem(),
    readyMs,
    scrollMs,
    initialApiRowCount: 100,
    initialRows,
    ...metrics,
  }))
  expect(metrics.domNodes).toBeLessThan(10_000)
})

test('keeps visible Listing identity through sort, filter, paging, keyboard and paste', async ({ page, context }) => {
  const submitted: Array<{ changes: Array<{ listing_id: string; target_value: string }> }> = []
  const savedTargets = new Map<string, string>()
  let draftVersion = 0
  let visibleChannelIds = [channels[0].channelId]
  let preferenceVersion = 1
  await context.grantPermissions(['clipboard-read', 'clipboard-write'])
  await page.addInitScript(() => localStorage.setItem('wp_token', 'isolated-identity-token'))
  await page.route('**/*', async route => {
    const url = new URL(route.request().url())
    if (!url.pathname.startsWith('/api/')) return route.continue()
    const json = (body: unknown) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
    if (url.pathname === '/api/v2/setup/status') return json({ completed: true })
    if (url.pathname === '/api/auth/me') return json({
      username: 'identity-admin', role: 'admin', is_admin: true, is_super_admin: false,
      permissions: { can_access_site: true, can_fetch: true, can_view_logs: true, can_view_settings: true },
      maintenance: { enabled: false, message: '' },
    })
    if (url.pathname === '/api/v2/source-profiles/channels') return json({ items: sourceChannels })
    if (url.pathname === '/api/v2/unified-workspaces/preferences/me') {
      if (route.request().method() === 'PUT') {
        const body = JSON.parse(route.request().postData() ?? '{}') as { visibleChannelIds: string[] }
        visibleChannelIds = body.visibleChannelIds
        preferenceVersion += 1
      }
      return json({
      visibleChannelIds, channelOrder: [channels[0].channelId],
      visibleFields: { price: true, stock: true, status: true, sku: true },
      displayNameSource: 'canonical', version: preferenceVersion,
      })
    }
    if (url.pathname === '/api/v2/unified-workspaces/identity-workspace') return json({
      id: 'identity-workspace', name: 'Identity Workspace', entryPoint: 'manual', ownerUserId: 1,
      status: 'active', version: 1,
      snapshot: { id: 'identity-snapshot', checksum: 'b'.repeat(64), schemaVersion: '1', createdAt: new Date().toISOString() },
      draft: { id: 'identity-draft', version: draftVersion, currentRevisionId: draftVersion ? `revision-${draftVersion}` : null, status: 'draft' },
      createdAt: new Date().toISOString(),
    })
    if (url.pathname === '/api/v2/unified-workspaces/identity-workspace/draft/revisions') {
      const body = JSON.parse(route.request().postData() ?? '{}') as { changes: Array<{ listing_id: string; target_value: string }> }
      submitted.push(body)
      for (const change of body.changes) savedTargets.set(change.listing_id, change.target_value)
      draftVersion += 1
      return json({ id: `revision-${draftVersion}`, revisionNumber: draftVersion, checksum: 'c'.repeat(64), draftVersion })
    }
    if (url.pathname === '/api/v2/unified-workspaces/identity-workspace/grid') {
      const requestedPage = Number(url.searchParams.get('page') ?? 1)
      const search = url.searchParams.get('search') ?? ''
      const identityRow = (listingId: string, name: string, external: string) => {
        const value = savedTargets.get(listingId) ?? (listingId === 'listing-a' ? '100' : '200')
        return {
          ...row(listingId === 'listing-a' ? 0 : 1),
          rowId: `row-${listingId}`,
          canonicalProductId: 'shared-canonical-product',
          canonicalName: name,
          displayName: name,
          listingId,
          listingLabel: `${name} Listing`,
          channelId: channels[0].channelId,
          externalPrimaryId: external,
          fields: {
            price: { current: listingId === 'listing-a' ? '100' : '200', target: value, status: savedTargets.has(listingId) ? 'draft_saved' : 'ready', readOnly: false, currency: 'EUR', unit: 'EUR' },
            stock: { current: '5', target: '5', status: 'ready', readOnly: false, currency: null, unit: null },
            status: { current: 'active', target: 'active', status: 'read_only', readOnly: true, currency: null, unit: null },
          },
        }
      }
      let items = requestedPage === 1
        ? [identityRow('listing-a', 'Alpha', '101'), identityRow('listing-b', 'Beta', '102')]
        : [identityRow('listing-page-two', 'Page Two', '501')]
      if ((url.searchParams.get('sort') ?? '').includes('desc')) items.reverse()
      if (search) items = items.filter(item => item.canonicalName.includes(search))
      return json({ items, total: search ? items.length : 501, page: requestedPage, pageSize: 500, channels: [channels[0]], draftVersion, revisionId: draftVersion ? `revision-${draftVersion}` : null })
    }
    if (url.pathname === '/api/v2/unified-workspaces/identity-workspace/grouped-grid') {
      const requestedPage = Number(url.searchParams.get('page') ?? 1)
      const search = url.searchParams.get('search') ?? ''
      const identityListing = (listingId: string, label: string, externalId: string, current: string) => {
        const target = savedTargets.get(listingId) ?? current
        const changed = target !== current
        return {
          listingId, channelId: channels[0].channelId, listingLabel: `${label} Listing`, externalId, externalIdType: 'external_product_id', sku: label.toUpperCase(), mappingState: 'resolved', cacheFreshness: 'fresh', state: changed ? 'ready' : 'unchanged', changedFields: changed ? ['price'] : [], selected: changed, reviewItemIds: [],
          fields: {
            price: { current, target, changed, status: changed ? 'ready' : 'unchanged', readOnly: false, currency: 'EUR', unit: 'EUR' },
            stock: { current: '5', target: '5', changed: false, status: 'unchanged', readOnly: false, currency: null, unit: null },
            status: { current: 'active', target: 'active', changed: false, status: 'unchanged', readOnly: true, currency: null, unit: null },
          },
        }
      }
      const pageOne = {
        sourceProductId: 'shared-canonical-product', name: 'Shared Product', sourceKey: 'SHARED', cost: null, category: null, brand: null, productType: 'simple', mappedChannelCount: 1, listingCount: 2, changedListingCount: savedTargets.size, selectedListingCount: savedTargets.size, state: savedTargets.size ? 'ready' : 'unchanged',
        children: [identityListing('listing-a', 'Alpha', '101', '100'), identityListing('listing-b', 'Beta', '102', '200')],
      }
      const pageTwo = {
        sourceProductId: 'page-two-product', name: 'Page Two', sourceKey: 'PAGE-2', cost: null, category: null, brand: null, productType: 'simple', mappedChannelCount: 1, listingCount: 1, changedListingCount: 0, selectedListingCount: 0, state: 'unchanged',
        children: [identityListing('listing-page-two', 'Page Two', '501', '500')],
      }
      const items = search.includes('Beta') ? [pageOne] : requestedPage === 1 ? [pageOne] : [pageTwo]
      return json({ items, total: search ? 1 : 101, page: requestedPage, pageSize: 100, view: 'all', summary: { ready: savedTargets.size, blocked: 0, unchanged: 101 - savedTargets.size, selected: savedTargets.size }, draftVersion, revisionId: draftVersion ? `revision-${draftVersion}` : null, reviewId: null, reviewStatus: null, selectionChecksum: null })
    }
    return route.fulfill({ status: 404, contentType: 'application/json', body: '{}' })
  })

  await page.goto('/workspace/identity-workspace')
  await expect(page.getByText('Identity Workspace')).toBeVisible()
  await page.locator('[data-pricing-sort="product"]').click()
  await page.locator('[data-pricing-sort="product"]').click()
  const betaTarget = page.locator('.ht_master td[data-listing-id="listing-b"][data-target-field="price"]').first()
  await expect(betaTarget).toBeVisible()
  await betaTarget.dblclick()
  await page.keyboard.press('Control+A')
  await page.keyboard.type('225')
  await page.keyboard.press('Enter')
  await expect(page.locator('[data-pending-summary]')).toContainText('1 pending change')

  await page.getByRole('button', { name: 'Next' }).click()
  await expect(page.getByText('Page 2 of 2')).toBeVisible()
  await page.getByRole('button', { name: 'Previous' }).click()
  await expect(page.getByText('Page 1 of 2')).toBeVisible()
  await expect(page.locator('.ht_master td[data-listing-id="listing-b"][data-target-field="price"]').first()).toContainText('225')

  await page.getByRole('searchbox', { name: /Search Source Products/i }).fill('Beta')
  await page.getByRole('button', { name: 'Filter server data' }).click()
  await expect(page.locator('.ht_master td[data-listing-id="listing-b"]')).not.toHaveCount(0)
  const pastedTarget = page.locator('.ht_master td[data-listing-id="listing-b"][data-target-field="price"]').first()
  await pastedTarget.click()
  await page.evaluate(() => navigator.clipboard.writeText('230'))
  await page.keyboard.press('Control+V')
  await expect(page.locator('[data-pending-summary]')).toContainText('1 pending change')

  const checkbox = page.locator('.ht_master td[data-listing-id="listing-b"][data-field-selection][data-field="price"] input').first()
  await expect(checkbox).toBeChecked()
  await checkbox.uncheck()
  await expect(checkbox).not.toBeChecked()
  await expect(page.locator('[data-pending-summary]')).toContainText('1 pending change')
})
