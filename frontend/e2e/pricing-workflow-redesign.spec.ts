import os from 'node:os'
import path from 'node:path'
import { mkdirSync, writeFileSync } from 'node:fs'
import { expect, test, type Browser, type BrowserContext, type Page, type Route } from '@playwright/test'

// The acceptance video is captured and checked into docs/videos. Keep routine
// regression runs video-free so installed-Chrome teardown remains deterministic.
test.use({ video: 'off' })

const screenshotRoot = path.resolve('..', 'docs', 'screenshots', 'v1.3', 'pricing-workflow-redesign')
const videoRoot = path.resolve('..', 'docs', 'videos', 'v1.3', 'pricing-workflow-redesign')
mkdirSync(screenshotRoot, { recursive: true })
mkdirSync(videoRoot, { recursive: true })
const captureEvidence = process.env.FLOWHUB_CAPTURE_PRICING_EVIDENCE === '1'

type Field = 'price' | 'stock' | 'status'
type DraftChange = {
  canonical_product_id: string
  listing_id: string
  channel_id: string
  field: Field
  target_value: string
  currency: string | null
  unit: string | null
}

interface RequestRecord {
  method: string
  pathname: string
  search: string
}

interface Audit {
  external: string[]
  requests: RequestRecord[]
  draftChanges: DraftChange[]
  selectedItemIds: string[]
  reviewCalls: number
  dryRunCalls: number
  applyCalls: number
  catalogBootstrapCalls: number
  maximumReturnedProducts: number
}

interface MockOptions {
  workspaceId: string
  workspaceName: string
  totalProducts: number
  channelIds: string[]
  defaultPageSize: number
}

const acceptanceChannels = ['woocommerce:primary', 'snappshop:main', 'tapsishop:main']
const benchmarkChannels = [
  'woocommerce:primary',
  'snappshop:main',
  'tapsishop:main',
  'shopify:main',
  'marketplace-five:main',
]

const channelName = (channelId: string) => ({
  'woocommerce:primary': 'WooCommerce',
  'snappshop:main': 'SnappShop',
  'tapsishop:main': 'TapsiShop',
  'shopify:main': 'Shopify',
  'marketplace-five:main': 'Marketplace Five',
}[channelId] ?? channelId)

const reviewItemId = (change: DraftChange) => `review:${change.listing_id}:${change.field}`

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({
    status,
    contentType: 'application/json; charset=utf-8',
    body: JSON.stringify(body),
  })
}

function workspace(options: MockOptions) {
  return {
    id: options.workspaceId,
    name: options.workspaceName,
    entryPoint: 'manual',
    ownerUserId: 1,
    status: 'active',
    version: 1,
    snapshot: {
      id: `snapshot-${options.workspaceId}`,
      checksum: 's'.repeat(64),
      schemaVersion: 'uw-snapshot-1',
      createdAt: '2026-07-16T08:00:00Z',
    },
    draft: {
      id: `draft-${options.workspaceId}`,
      version: 1,
      currentRevisionId: null,
      status: 'draft',
    },
    createdAt: '2026-07-16T08:00:00Z',
  }
}

function makeProduct(index: number, options: MockOptions, audit: Audit) {
  const productNumber = index + 1
  const productId = `product-${productNumber}`
  const isVariableParent = productNumber % 137 === 0
  const savedByKey = new Map(audit.draftChanges.map(change => [`${change.listing_id}:${change.field}`, change]))
  const children = options.channelIds.map((channelId, channelIndex) => {
    const listingId = `listing-${productNumber}-${channelIndex + 1}`
    const blocked = productNumber >= 21 && productNumber <= 23 && channelIndex === 0
    const basePrice = 10_000 + productNumber * 100 + channelIndex * 25
    const baseStock = 20 + (productNumber % 30)
    const priceChange = savedByKey.get(`${listingId}:price`)
    const stockChange = savedByKey.get(`${listingId}:stock`)
    const statusChange = savedByKey.get(`${listingId}:status`)
    const listingChanges = audit.draftChanges.filter(change => change.listing_id === listingId)
    return {
      listingId,
      channelId,
      listingLabel: channelIndex === 0 ? 'Primary' : 'Main',
      externalId: `${500_000 + productNumber * 10 + channelIndex}`,
      externalIdType: channelId === 'tapsishop:main' ? 'seller_sku' : 'product_id',
      sku: `SKU-${String(productNumber).padStart(5, '0')}`,
      mappingState: 'resolved',
      cacheFreshness: 'fresh',
      state: blocked ? 'blocked' : 'ready',
      changedFields: listingChanges.map(change => change.field),
      selected: listingChanges.some(change => audit.selectedItemIds.includes(reviewItemId(change))),
      reviewItemIds: listingChanges.map(reviewItemId),
      fields: {
        price: {
          current: String(basePrice),
          target: priceChange?.target_value ?? String(basePrice),
          changed: Boolean(priceChange),
          readOnly: isVariableParent,
          status: blocked ? 'blocked' : priceChange ? 'ready' : 'unchanged',
          currency: 'IRR',
          unit: 'IRR',
        },
        stock: {
          current: String(baseStock),
          target: stockChange?.target_value ?? String(baseStock),
          changed: Boolean(stockChange),
          readOnly: isVariableParent,
          status: blocked ? 'blocked' : stockChange ? 'ready' : 'unchanged',
          currency: null,
          unit: null,
        },
        status: {
          current: 'publish',
          target: statusChange?.target_value ?? 'publish',
          changed: Boolean(statusChange),
          readOnly: isVariableParent,
          status: blocked ? 'blocked' : statusChange ? 'ready' : 'unchanged',
          currency: null,
          unit: null,
        },
      },
    }
  })
  return {
    sourceProductId: productId,
    name: `Synthetic Product ${String(productNumber).padStart(5, '0')}`,
    sourceKey: `SRC-${String(productNumber).padStart(5, '0')}`,
    cost: null,
    category: productNumber % 2 ? 'Accessories' : 'Cables',
    brand: productNumber % 3 ? 'FlowHub' : 'Synthetic',
    productType: isVariableParent ? 'variable' : productNumber % 7 === 0 ? 'variation' : 'simple',
    mappedChannelCount: options.channelIds.length,
    listingCount: children.length,
    changedListingCount: children.filter(child => child.changedFields.length).length,
    selectedListingCount: children.filter(child => child.selected).length,
    state: children.some(child => child.state === 'blocked') ? 'blocked' : 'ready',
    children,
  }
}

function reviewResource(options: MockOptions, audit: Audit) {
  const items = audit.draftChanges.map(change => {
    const productNumber = Number(change.canonical_product_id.replace('product-', ''))
    const channelIndex = options.channelIds.indexOf(change.channel_id)
    const blocked = productNumber >= 21 && productNumber <= 23 && channelIndex === 0
    const current = change.field === 'price'
      ? String(10_000 + productNumber * 100 + channelIndex * 25)
      : change.field === 'stock'
        ? String(20 + (productNumber % 30))
        : 'publish'
    return {
      id: reviewItemId(change),
      canonicalProductId: change.canonical_product_id,
      listingId: change.listing_id,
      channelId: change.channel_id,
      field: change.field,
      current,
      target: change.target_value,
      validationState: blocked ? 'blocked' : 'ready',
      warnings: [],
      errors: blocked ? ['Synthetic blocked item'] : [],
      eligible: !blocked,
      selected: audit.selectedItemIds.includes(reviewItemId(change)),
    }
  })
  return {
    id: `review-${options.workspaceId}`,
    workspaceId: options.workspaceId,
    snapshotId: `snapshot-${options.workspaceId}`,
    draftRevisionId: `revision-${options.workspaceId}`,
    status: 'ready',
    checksum: 'r'.repeat(64),
    summary: {
      total: items.length,
      eligible: items.filter(item => item.eligible).length,
      blocked: items.filter(item => !item.eligible).length,
      warnings: 0,
    },
    items,
    staleReason: null,
  }
}

function filteredIndexes(url: URL, options: MockOptions) {
  const search = (url.searchParams.get('search') ?? '').trim().toLowerCase()
  const indexes = Array.from({ length: options.totalProducts }, (_, index) => index)
  const filtered = search
    ? indexes.filter(index => `synthetic product ${String(index + 1).padStart(5, '0')}`.includes(search))
    : indexes
  const sort = url.searchParams.get('sort') ?? url.searchParams.get('sortBy') ?? ''
  const direction = url.searchParams.get('direction') ?? url.searchParams.get('sortDirection') ?? ''
  if (sort.includes('desc') || direction === 'desc') filtered.reverse()
  return filtered
}

async function installMocks(page: Page, options: MockOptions, audit: Audit) {
  await page.addInitScript(() => {
    localStorage.setItem('wp_token', 'pricing-workflow-isolated-token')
    if (!localStorage.getItem('flowhub.locale')) localStorage.setItem('flowhub.locale', 'en')
  })
  await page.route('**/*', async route => {
    const request = route.request()
    const url = new URL(request.url())
    const method = request.method().toUpperCase()
    if (!['127.0.0.1', 'localhost'].includes(url.hostname)) {
      audit.external.push(`${method} ${url.href}`)
      return route.abort('blockedbyclient')
    }
    if (!url.pathname.startsWith('/api/')) return route.continue()
    audit.requests.push({ method, pathname: url.pathname, search: url.search })

    if (url.pathname === '/api/v2/setup/status') return json(route, { completed: true })
    if (url.pathname === '/api/auth/me') return json(route, {
      username: 'pricing-owner',
      role: 'admin',
      is_admin: true,
      is_super_admin: false,
      permissions: {
        can_access_site: true,
        can_fetch: true,
        can_view_logs: true,
        can_view_settings: true,
      },
      maintenance: { enabled: false, message: '' },
    })
    if (url.pathname === '/api/health') return json(route, { status: 'ok', env: 'test' })
    if (url.pathname === '/api/v2/products/categories') return json(route, { items: [] })
    if (url.pathname === '/api/v2/source-profiles/channels') return json(route, {
      items: options.channelIds.map(channelId => ({
        channelId,
        name: channelName(channelId),
        connectorType: channelId.split(':')[0],
        capabilityVersion: 'benchmark-v1',
        capabilities: {
          writePrice: true,
          writeStock: true,
          writeStatus: true,
          writeAvailable: true,
          supportedStatuses: ['active', 'inactive'],
          currency: 'IRR',
          unit: 'IRR',
        },
        enabled: true,
        implementationState: 'implemented',
        available: true,
      })),
    })
    if (url.pathname === '/api/v2/products') {
      const requestedPage = Number(url.searchParams.get('page') ?? 1)
      const pageSize = Math.min(Number(url.searchParams.get('pageSize') ?? 50), 500)
      const indexes = filteredIndexes(url, options)
      const pageIndexes = indexes.slice((requestedPage - 1) * pageSize, requestedPage * pageSize)
      return json(route, {
        items: pageIndexes.map(index => ({
          id: String(index + 1),
          productId: String(index + 1),
          name: `Synthetic Product ${String(index + 1).padStart(5, '0')}`,
          sku: `SKU-${String(index + 1).padStart(5, '0')}`,
          connectorId: 'woocommerce:primary',
          currentPrice: 10_000 + index * 100,
          sourcePrice: null,
          currency: 'IRR',
          productType: index % 7 === 0 ? 'variation' : 'simple',
          categoryNames: ['Accessories'],
          imageUrl: null,
          status: 'active',
          lastSynced: null,
        })),
        total: indexes.length,
        page: requestedPage,
        pageSize,
        configured: true,
      })
    }
    if (url.pathname === '/api/v2/unified-workspaces/manual' && method === 'POST') {
      const body = JSON.parse(request.postData() ?? '{}') as { catalog_scope?: unknown; selections?: unknown }
      if (!body.catalog_scope || body.selections !== undefined) {
        return json(route, { code: 'INVALID_PRODUCTS_WORKSPACE_SCOPE', message: 'Products must bootstrap from the catalog scope.' }, 422)
      }
      audit.catalogBootstrapCalls += 1
      return json(route, workspace(options))
    }
    if (url.pathname === `/api/v2/unified-workspaces/${options.workspaceId}`) return json(route, workspace(options))
    if (url.pathname === `/api/v2/unified-workspaces/${options.workspaceId}/grid`) return json(route, {
      items: [], total: 0, page: 1, pageSize: 500, channels: [], draftVersion: 1, revisionId: null,
    })
    if (url.pathname === '/api/v2/unified-workspaces/preferences/me') return json(route, {
      visibleChannelIds: options.channelIds,
      channelOrder: options.channelIds,
      visibleFields: { price: true, stock: true, status: true, sku: true },
      displayNameSource: 'canonical',
      version: 1,
    })
    if (url.pathname === `/api/v2/unified-workspaces/${options.workspaceId}/grouped-grid`) {
      const requestedPage = Number(url.searchParams.get('page') ?? 1)
      const requestedSize = Math.min(Number(url.searchParams.get('pageSize') ?? options.defaultPageSize), 500)
      const indexes = filteredIndexes(url, options)
      const pageIndexes = indexes.slice((requestedPage - 1) * requestedSize, requestedPage * requestedSize)
      audit.maximumReturnedProducts = Math.max(audit.maximumReturnedProducts, pageIndexes.length)
      const selected = audit.selectedItemIds.length
      return json(route, {
        items: pageIndexes.map(index => makeProduct(index, options, audit)),
        total: indexes.length,
        page: requestedPage,
        pageSize: requestedSize,
        view: url.searchParams.get('view') ?? 'all',
        summary: {
          ready: Math.max(0, options.totalProducts - 3),
          blocked: Math.min(3, options.totalProducts),
          unchanged: Math.max(0, options.totalProducts - audit.draftChanges.length),
          selected,
        },
        draftVersion: 1,
        revisionId: audit.draftChanges.length ? `revision-${options.workspaceId}` : null,
        reviewId: audit.reviewCalls ? `review-${options.workspaceId}` : null,
        reviewStatus: audit.reviewCalls ? 'ready' : null,
        selectionChecksum: audit.reviewCalls ? 'selection-checksum' : null,
      })
    }
    if (url.pathname === `/api/v2/unified-workspaces/${options.workspaceId}/draft/revisions` && method === 'POST') {
      const body = JSON.parse(request.postData() ?? '{}') as { changes?: DraftChange[] }
      audit.draftChanges = body.changes ?? []
      return json(route, {
        id: `revision-${options.workspaceId}`,
        revisionNumber: 1,
        checksum: 'd'.repeat(64),
        draftVersion: 2,
      })
    }
    if (url.pathname === `/api/v2/unified-workspaces/${options.workspaceId}/reviews` && method === 'POST') {
      audit.reviewCalls += 1
      audit.dryRunCalls += 1
      return json(route, reviewResource(options, audit))
    }
    if (url.pathname === `/api/v2/unified-workspaces/${options.workspaceId}/reviews/review-${options.workspaceId}` && method === 'GET') {
      return json(route, reviewResource(options, audit))
    }
    if (url.pathname === `/api/v2/unified-workspaces/${options.workspaceId}/reviews/review-${options.workspaceId}/selection` && method === 'PUT') {
      const body = JSON.parse(request.postData() ?? '{}') as { review_item_ids?: string[] }
      audit.selectedItemIds = body.review_item_ids ?? []
      return json(route, {
        reviewId: `review-${options.workspaceId}`,
        selectedItemIds: audit.selectedItemIds,
        selectionChecksum: 'selection-checksum',
        selectionVersion: 2,
      })
    }
    if (url.pathname === `/api/v2/unified-workspaces/${options.workspaceId}/apply` && method === 'POST') {
      audit.applyCalls += 1
      const selectedChanges = audit.draftChanges.filter(change => audit.selectedItemIds.includes(reviewItemId(change)))
      return json(route, {
        id: `apply-${options.workspaceId}`,
        workspaceId: options.workspaceId,
        status: 'partially_applied',
        correlationId: 'pricing-mock-correlation',
        items: selectedChanges.slice(0, 3).map((change, index) => ({
          id: `apply-${index + 1}`,
          listingId: change.listing_id,
          channelId: change.channel_id,
          field: change.field,
          status: index === 1 ? 'reconciliation_required' : index === 2 ? 'failed' : 'applied',
          errorMessage: index === 1 ? 'Provider response uncertain' : index === 2 ? 'Synthetic provider failure' : null,
          cacheSyncStatus: index === 0 ? 'verified' : 'pending',
        })),
      })
    }
    return json(route, { code: 'UNHANDLED_ISOLATED_TEST_REQUEST', path: url.pathname }, 500)
  })
}

function createAudit(): Audit {
  return {
    external: [],
    requests: [],
    draftChanges: [],
    selectedItemIds: [],
    reviewCalls: 0,
    dryRunCalls: 0,
    applyCalls: 0,
    catalogBootstrapCalls: 0,
    maximumReturnedProducts: 0,
  }
}

async function browserIdentity(browser: Browser) {
  return {
    browserVersion: browser.version(),
    operatingSystem: `${os.platform()} ${os.release()}`,
    cpu: os.cpus()[0]?.model ?? 'unknown',
    logicalCpuCount: os.cpus().length,
    totalMemoryBytes: os.totalmem(),
  }
}

async function captureScreenshot(page: Page, name: string) {
  if (!captureEvidence) return
  await page.screenshot({ path: path.join(screenshotRoot, name) })
}

async function grantClipboard(context: BrowserContext) {
  await context.grantPermissions(['clipboard-read', 'clipboard-write'], { origin: 'http://127.0.0.1:4188' })
}

function targetCell(page: Page, listingId: string, field: Field) {
  return page.locator(`.ht_master td[data-listing-id="${listingId}"][data-target-field="${field}"]`).first()
}

function fieldSelection(page: Page, listingId: string, field: Field) {
  return page.locator(`.ht_master td[data-listing-id="${listingId}"][data-field-selection][data-field="${field}"] input`).first()
}

async function fullyVisiblePricingRows(page: Page): Promise<number> {
  return page.locator('[data-pricing-grid] .ht_master tbody tr').evaluateAll(rows => rows.filter(row => {
    const rect = row.getBoundingClientRect()
    return rect.height > 0 && rect.top >= 0 && rect.bottom <= window.innerHeight
  }).length)
}

async function replaceCell(page: Page, cell: ReturnType<Page['locator']>, value: string, commitKey: 'Enter' | 'Tab' = 'Enter') {
  // Handsontable recycles horizontal viewport cells. Settle the requested
  // immutable Listing/Field locator after scrolling before activating edit.
  await cell.scrollIntoViewIfNeeded()
  await cell.evaluate(() => new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))))
  await cell.dblclick()
  await page.keyboard.press('Control+A')
  await page.keyboard.insertText(value)
  await page.keyboard.press(commitKey)
}

async function submitSearch(page: Page, search: ReturnType<Page['locator']>, value: string) {
  await search.fill(value)
  await page.getByRole('button', { name: /Filter server data/i }).click()
}

test('matches Wanted Model with direct field editing, immediate selection, bulk preview, one Review, one Dry Run and one Apply', async ({ page, context, browser, browserName }) => {
  test.setTimeout(180_000)
  await grantClipboard(context)
  const audit = createAudit()
  const options: MockOptions = {
    workspaceId: 'pricing-workspace',
    workspaceName: 'Wanted Model Pricing Workspace',
    totalProducts: 250,
    channelIds: acceptanceChannels,
    defaultPageSize: 100,
  }
  await installMocks(page, options, audit)
  await page.setViewportSize({ width: 1440, height: 900 })
  const workflowStarted = performance.now()
  await page.goto('/products', { waitUntil: 'domcontentloaded' })

  const grid = page.locator('[data-pricing-grid]')
  await expect(grid).toBeVisible({ timeout: 30_000 })
  expect(new URL(page.url()).pathname).toBe('/products')
  await expect(page.getByRole('button', { name: /Open pricing workspace/i })).toHaveCount(0)
  await expect(page.getByText(/Choose a product set first|Edit inline in the pricing workspace/i)).toHaveCount(0)
  expect(audit.catalogBootstrapCalls).toBe(1)
  await expect.poll(() => page.locator('[data-pricing-grid] .ht_master tbody tr').count()).toBeGreaterThanOrEqual(15)
  const timeToFirstEditableCellMs = Math.round(performance.now() - workflowStarted)
  const initiallyVisibleRows = await page.locator('[data-pricing-grid] .ht_master tbody tr').count()
  await expect(page.locator('[data-pricing-grid] button[aria-expanded]')).toHaveCount(0)

  const search = page.getByRole('searchbox', { name: /Search Source Products|Search products/i })
  await submitSearch(page, search, 'Synthetic Product')
  await expect.poll(() => audit.requests.some(request => request.pathname.endsWith('/grouped-grid') && request.search.includes('search=Synthetic'))).toBe(true)
  await submitSearch(page, search, '')

  const wooPrices = page.locator('.ht_master td[data-target-field="price"][data-channel-id="woocommerce:primary"]')
  await expect.poll(() => wooPrices.count()).toBeGreaterThanOrEqual(15)
  const editTenStarted = performance.now()
  for (let index = 0; index < 10; index += 1) {
    await replaceCell(page, wooPrices.nth(index), String(20_000 + index * 100))
  }
  const editTenProductsMs = Math.round(performance.now() - editTenStarted)
  await expect(page.locator('.ht_master td[data-field-selection][data-field="price"] input:checked')).toHaveCount(10)
  await expect(page.locator('.fh-pricing-counter-changed strong')).toHaveText('10')
  await expect(page.locator('[data-pending-summary]')).toContainText('10 pending changes')

  await wooPrices.nth(0).click()
  await page.keyboard.press('Enter')
  await page.keyboard.insertText('31500')
  await page.keyboard.press('Enter')
  await expect(page.locator('.ht_master td.current')).toHaveAttribute('data-listing-id', 'listing-2-1')
  await page.keyboard.press('Tab')
  await page.keyboard.press('Shift+Tab')
  await expect(page.locator('.ht_master td.current')).toHaveAttribute('data-listing-id', 'listing-2-1')
  await page.keyboard.press('Control+C')
  await expect.poll(() => page.evaluate(() => navigator.clipboard.readText()).then(value => value.replace(/\D/g, ''))).toContain('20100')
  await wooPrices.nth(0).dblclick()
  await page.keyboard.insertText('99999')
  await page.keyboard.press('Escape')
  await expect(wooPrices.nth(0)).toContainText('31500')

  const firstPrice = wooPrices.nth(0)
  await firstPrice.click()
  await page.evaluate(() => navigator.clipboard.writeText('31000\t31\n32000\t32'))
  await page.keyboard.press('Control+V')
  await expect(wooPrices.nth(0)).toContainText('31000')
  await expect(wooPrices.nth(1)).toContainText('32000')
  await expect(targetCell(page, 'listing-1-1', 'stock')).toContainText('31')
  await expect(targetCell(page, 'listing-2-1', 'stock')).toContainText('32')

  const undo = page.locator('[data-pricing-undo]')
  const redo = page.locator('[data-pricing-redo]')
  await expect(undo).toBeEnabled()
  await undo.click()
  await expect(wooPrices.nth(0)).toContainText('31500')
  await expect(targetCell(page, 'listing-1-1', 'stock')).not.toContainText('31')
  await expect(redo).toBeEnabled()
  await redo.click()
  await expect(wooPrices.nth(0)).toContainText('31000')
  await expect(targetCell(page, 'listing-1-1', 'stock')).toContainText('31')

  await page.locator('select[data-bulk-action]').selectOption('increase_price_percent')
  await page.locator('[data-bulk-value]').fill('5')
  await page.locator('[data-bulk-preview]').click()
  await expect(page.locator('[data-bulk-preview-dialog]')).toBeVisible()
  await expect(page.locator('[data-bulk-preview-dialog]')).toContainText('10 products')
  await expect(page.locator('[data-bulk-preview-dialog]')).toContainText('10 Listings')
  await captureScreenshot(page, 'bulk-percentage-preview.png')
  await page.locator('[data-bulk-confirm]').click()
  await expect(targetCell(page, 'listing-1-1', 'price')).toContainText('32550')
  await expect(targetCell(page, 'listing-10-1', 'price')).toContainText('21945')

  const firstSelection = fieldSelection(page, 'listing-1-1', 'price')
  await expect(firstSelection).toBeChecked()
  await firstSelection.uncheck()
  await expect(firstSelection).not.toBeChecked()

  await submitSearch(page, search, 'Synthetic Product 00200')
  await expect(page.getByText(/pending changes.*hidden by current filters/i)).toBeVisible()
  await submitSearch(page, search, '')
  await expect(firstPrice).toContainText('32550')

  await page.getByRole('button', { name: /Next/i }).click()
  await expect(page.getByText(/Page 2/i)).toBeVisible()
  await page.getByRole('button', { name: /Previous/i }).click()
  await expect(page.getByText(/Page 1/i)).toBeVisible()
  await expect(targetCell(page, 'listing-1-1', 'price')).toContainText('32550')

  await page.getByRole('button', { name: /Collapse sidebar/i }).click()
  await page.setViewportSize({ width: 1366, height: 768 })
  await expect(targetCell(page, 'listing-1-1', 'price')).toContainText('32550')
  await page.evaluate(() => localStorage.setItem('flowhub.locale', 'fa'))
  await page.reload({ waitUntil: 'domcontentloaded' })
  await expect(page.locator('html')).toHaveAttribute('dir', 'rtl')
  await expect(targetCell(page, 'listing-1-1', 'price')).toContainText('32550')
  await page.evaluate(() => localStorage.setItem('flowhub.locale', 'en'))
  await page.reload({ waitUntil: 'domcontentloaded' })
  await expect(page.locator('html')).toHaveAttribute('dir', 'ltr')
  await expect(targetCell(page, 'listing-1-1', 'price')).toContainText('32550')

  await page.setViewportSize({ width: 1440, height: 900 })
  await expect.poll(() => page.locator('[data-pricing-grid] .ht_master tbody tr').count()).toBeGreaterThanOrEqual(15)
  await expect.poll(() => fullyVisiblePricingRows(page)).toBeGreaterThanOrEqual(15)
  await captureScreenshot(page, 'wanted-model-dense-grid.png')
  await page.locator('[data-pricing-review]').click()
  await expect(page.getByRole('heading', { name: /Review Changes/i })).toBeVisible()
  await captureScreenshot(page, 'wanted-model-review.png')
  expect(audit.reviewCalls).toBe(0)
  expect(audit.dryRunCalls).toBe(0)
  await page.getByRole('button', { name: /Back to grid/i }).click()

  await page.locator('[data-pricing-dry-run]').click()
  await expect(page.getByRole('heading', { name: /Review Changes/i })).toBeVisible()
  await captureScreenshot(page, 'wanted-model-dry-run.png')
  await expect.poll(() => audit.reviewCalls).toBe(1)
  expect(audit.dryRunCalls).toBe(1)
  expect(audit.draftChanges.length).toBeGreaterThanOrEqual(10)
  expect(audit.selectedItemIds).not.toContain('review:listing-1-1:price')
  expect([...audit.selectedItemIds].sort()).toEqual(audit.draftChanges
    .map(reviewItemId)
    .filter(itemId => itemId !== 'review:listing-1-1:price')
    .sort())
  await page.getByRole('button', { name: /Back to grid/i }).click()
  await expect(grid).toBeVisible()

  const applyButton = page.getByRole('button', { name: /^Apply \d+/i })
  await expect(applyButton).toBeEnabled()
  await applyButton.click()
  await expect(page.getByRole('dialog', { name: /Apply confirmation/i })).toBeVisible()
  await page.getByRole('button', { name: /Confirm Apply/i }).click()
  await expect(page.getByText(/partially applied/i)).toBeVisible()
  await expect(page.getByText(/Reconciliation Required/i)).toBeVisible()
  const applyResults = page.getByRole('region', { name: /Apply results/i })
  await expect(applyResults).toBeVisible()
  await applyResults.scrollIntoViewIfNeeded()
  await captureScreenshot(page, 'wanted-model-apply-results.png')

  expect(audit.reviewCalls).toBe(1)
  expect(audit.dryRunCalls).toBe(1)
  expect(audit.applyCalls).toBe(1)
  expect(new URL(page.url()).pathname).toBe('/products')
  expect(audit.external).toEqual([])
  const acceptanceMetrics = {
    browserName,
    ...(await browserIdentity(browser)),
    viewport: { width: 1440, height: 900 },
    productsEditedInline: 10,
    directCellEditActivations: 10,
    productEditModalOpenings: 0,
    routeChanges: 0,
    reviewOperations: audit.reviewCalls,
    dryRunOperations: audit.dryRunCalls,
    applyOperations: audit.applyCalls,
    initiallyVisibleRows,
    timeToFirstEditableCellMs,
    editTenProductsMs,
  }
  writeFileSync(path.join(screenshotRoot, 'wanted-model-acceptance-metrics.json'), `${JSON.stringify(acceptanceMetrics, null, 2)}\n`, 'utf8')
  console.log(`PRICING_ACCEPTANCE ${JSON.stringify(acceptanceMetrics)}`)
})

test('benchmarks a virtualized 10,000-product, five-channel dense pricing grid with a bounded API window', async ({ page, context, browser, browserName }) => {
  test.setTimeout(180_000)
  await grantClipboard(context)
  const audit = createAudit()
  const options: MockOptions = {
    workspaceId: 'pricing-benchmark',
    workspaceName: '10,000 Product Pricing Benchmark',
    totalProducts: 10_000,
    channelIds: benchmarkChannels,
    defaultPageSize: 100,
  }
  await installMocks(page, options, audit)
  await page.setViewportSize({ width: 1440, height: 900 })

  const readyStarted = performance.now()
  await page.goto('/products', { waitUntil: 'domcontentloaded' })
  const grid = page.locator('[data-pricing-grid]')
  await expect(grid).toBeVisible({ timeout: 30_000 })
  expect(new URL(page.url()).pathname).toBe('/products')
  expect(audit.catalogBootstrapCalls).toBe(1)
  await expect.poll(() => page.locator('[data-pricing-grid] .ht_master tbody tr').count()).toBeGreaterThanOrEqual(15)
  const readyMs = Math.round(performance.now() - readyStarted)
  const renderedRows = await page.locator('[data-pricing-grid] .ht_master tbody tr').count()
  expect(renderedRows).toBeGreaterThanOrEqual(15)
  expect(renderedRows).toBeLessThan(100)
  expect(audit.maximumReturnedProducts).toBeLessThanOrEqual(500)
  expect(audit.requests.some(request => request.pathname.endsWith('/grouped-grid') && request.search.includes('pageSize=10000'))).toBe(false)

  const scrollContainer = page.locator('[data-pricing-virtual-viewport]')
  const scrollStarted = performance.now()
  await scrollContainer.evaluate(element => { element.scrollTop = Math.max(0, element.scrollHeight - element.clientHeight) })
  await page.waitForTimeout(100)
  const scrollMs = Math.round(performance.now() - scrollStarted)
  expect(await page.locator('[data-pricing-grid] .ht_master tbody tr').count()).toBeLessThan(100)
  await scrollContainer.evaluate(element => { element.scrollTop = 0 })
  await expect(targetCell(page, 'listing-1-1', 'price')).toBeVisible()

  const firstPrice = targetCell(page, 'listing-1-1', 'price')
  const editStarted = performance.now()
  await replaceCell(page, firstPrice, '99000')
  await expect(fieldSelection(page, 'listing-1-1', 'price')).toBeChecked()
  const editResponseMs = Math.round(performance.now() - editStarted)

  const pasteStarted = performance.now()
  await firstPrice.click()
  await page.evaluate(() => navigator.clipboard.writeText('99100\n99200\n99300\n99400\n99500'))
  await page.keyboard.press('Control+V')
  await expect(targetCell(page, 'listing-5-1', 'price')).toContainText('99500')
  const pasteResponseMs = Math.round(performance.now() - pasteStarted)

  const search = page.getByRole('searchbox', { name: /Search Source Products|Search products/i })
  const filterStarted = performance.now()
  await submitSearch(page, search, 'Synthetic Product 09999')
  await expect(page.locator('.ht_master td[data-product-id="product-9999"]').first()).toBeVisible()
  const filterMs = Math.round(performance.now() - filterStarted)
  await submitSearch(page, search, '')

  const sortStarted = performance.now()
  await page.locator('[data-pricing-sort="product"]').click()
  await page.locator('[data-pricing-sort="product"]').click()
  await expect(page.locator('.ht_master tr[data-pricing-row]').first()).toHaveAttribute('data-product-id', 'product-100')
  const sortedPrice = targetCell(page, 'listing-100-1', 'price')
  await replaceCell(page, sortedPrice, '88000')
  await expect(fieldSelection(page, 'listing-100-1', 'price')).toBeChecked()
  const sortMs = Math.round(performance.now() - sortStarted)
  await page.locator('[data-pricing-sort="product"]').click()
  await expect(page.locator('.ht_master tr[data-pricing-row]').first()).toHaveAttribute('data-product-id', 'product-1')
  await expect(targetCell(page, 'listing-1-1', 'price')).toContainText('99100')

  const pageStarted = performance.now()
  await page.getByRole('button', { name: /Next/i }).click()
  await expect(page.getByText(/Page 2/i)).toBeVisible()
  await page.getByRole('button', { name: /Previous/i }).click()
  await expect(page.getByText(/Page 1/i)).toBeVisible()
  await expect(targetCell(page, 'listing-1-1', 'price')).toContainText('99100')
  const pageReturnMs = Math.round(performance.now() - pageStarted)

  const browserMetrics = await page.evaluate(() => ({
    domNodeCount: document.getElementsByTagName('*').length,
    observedHeapBytes: (performance as Performance & { memory?: { usedJSHeapSize: number } }).memory?.usedJSHeapSize ?? null,
  }))
  expect(browserMetrics.domNodeCount).toBeLessThan(10_000)
  expect(audit.maximumReturnedProducts).toBeLessThanOrEqual(500)
  expect(audit.external).toEqual([])

  const metrics = {
    datasetProducts: options.totalProducts,
    visibleChannels: options.channelIds.length,
    maximumApiWindow: audit.maximumReturnedProducts,
    renderedRows,
    browserName,
    ...(await browserIdentity(browser)),
    viewport: { width: 1440, height: 900 },
    readyMs,
    scrollMs,
    editResponseMs,
    pasteResponseMs,
    filterMs,
    sortMs,
    pageReturnMs,
    ...browserMetrics,
  }
  writeFileSync(path.join(screenshotRoot, 'pricing-10000-benchmark-metrics.json'), `${JSON.stringify(metrics, null, 2)}\n`, 'utf8')
  console.log(`PRICING_BENCHMARK ${JSON.stringify(metrics)}`)
  await captureScreenshot(page, 'pricing-10000-benchmark.png')
})
