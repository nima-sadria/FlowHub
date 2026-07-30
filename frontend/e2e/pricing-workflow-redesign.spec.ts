import os from 'node:os'
import path from 'node:path'
import { mkdirSync } from 'node:fs'
import { expect, test, type Browser, type BrowserContext, type Page, type Route } from '@playwright/test'

// The acceptance video is captured and checked into docs/videos. Keep routine
// regression runs video-free so installed-Chrome teardown remains deterministic.
test.use({ video: 'off' })

const screenshotRoot = path.resolve('..', 'docs', 'screenshots', 'v1.3', 'pricing-workflow-redesign')
mkdirSync(screenshotRoot, { recursive: true })
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
}

interface MockOptions {
  workspaceId: string
  workspaceName: string
  totalProducts: number
  channelIds: string[]
  defaultPageSize: number
}

interface BrowserStartupMetrics {
  lcpMs: number
  lcpElement: string
  lcpText: string
  cls: number
  totalBlockingTimeMs: number
  longestTaskMs: number
  longTaskCount: number
  inpMs: number
  firstContentfulPaintMs: number
  responseStartMs: number
  renderDelayMs: number
  renderDelayPercent: number
}

const acceptanceChannels = ['woocommerce:primary', 'snappshop:main', 'tapsishop:main']

const channelName = (channelId: string) => ({
  'woocommerce:primary': 'WooCommerce',
  'snappshop:main': 'SnappShop',
  'tapsishop:main': 'TapsiShop',
}[channelId] ?? channelId)

const reviewItemId = (change: DraftChange) => `review:${change.listing_id}:${change.field}`

async function installStartupPerformanceObservers(page: Page) {
  await page.addInitScript(() => {
    const state = {
      lcpMs: 0,
      lcpElement: '',
      lcpText: '',
      cls: 0,
      longTasks: [] as number[],
      interactions: [] as number[],
    }
    Object.defineProperty(window, '__flowhubStartupPerformance', {
      configurable: false,
      enumerable: false,
      value: state,
      writable: false,
    })
    try {
      new PerformanceObserver(list => {
        const entries = list.getEntries()
        const latest = entries.at(-1) as PerformanceEntry & { element?: Element }
        if (latest) {
          state.lcpMs = latest.startTime
          const element = latest.element
          state.lcpElement = element
            ? `${element.tagName.toLowerCase()}${element.id ? `#${element.id}` : ''}${element.className ? `.${String(element.className).trim().replace(/\s+/g, '.')}` : ''}`.slice(0, 240)
            : ''
          state.lcpText = element?.textContent?.trim().replace(/\s+/g, ' ').slice(0, 160) ?? ''
        }
      }).observe({ type: 'largest-contentful-paint', buffered: true })
    } catch { /* Browser does not expose LCP observation. */ }
    try {
      new PerformanceObserver(list => {
        for (const entry of list.getEntries()) {
          const shift = entry as PerformanceEntry & { hadRecentInput?: boolean; value?: number }
          if (!shift.hadRecentInput) state.cls += shift.value ?? 0
        }
      }).observe({ type: 'layout-shift', buffered: true })
    } catch { /* Browser does not expose layout-shift observation. */ }
    try {
      new PerformanceObserver(list => {
        for (const entry of list.getEntries()) state.longTasks.push(entry.duration)
      }).observe({ type: 'longtask', buffered: true })
    } catch { /* Browser does not expose long-task observation. */ }
    try {
      new PerformanceObserver(list => {
        for (const entry of list.getEntries()) {
          const event = entry as PerformanceEntry & { interactionId?: number }
          if (event.interactionId) state.interactions.push(event.duration)
        }
      }).observe({ type: 'event', buffered: true, durationThreshold: 16 } as PerformanceObserverInit)
    } catch { /* Browser does not expose event-timing observation. */ }
  })
}

async function startupPerformanceMetrics(page: Page): Promise<BrowserStartupMetrics> {
  return page.evaluate(() => {
    const state = (window as Window & {
      __flowhubStartupPerformance?: { lcpMs: number; cls: number; longTasks: number[] }
    }).__flowhubStartupPerformance as { lcpMs: number; lcpElement: string; lcpText: string; cls: number; longTasks: number[]; interactions: number[] } | undefined
      ?? { lcpMs: 0, lcpElement: '', lcpText: '', cls: 0, longTasks: [], interactions: [] }
    const navigation = performance.getEntriesByType('navigation')[0] as PerformanceNavigationTiming | undefined
    const firstContentfulPaint = performance.getEntriesByName('first-contentful-paint')[0]
    const totalBlockingTimeMs = state.longTasks.reduce((total, duration) => total + Math.max(0, duration - 50), 0)
    const responseStartMs = navigation?.responseStart ?? 0
    const renderDelayMs = Math.max(0, state.lcpMs - responseStartMs)
    return {
      lcpMs: Math.round(state.lcpMs),
      lcpElement: state.lcpElement,
      lcpText: state.lcpText,
      cls: Number(state.cls.toFixed(4)),
      totalBlockingTimeMs: Math.round(totalBlockingTimeMs),
      longestTaskMs: Math.round(Math.max(0, ...state.longTasks)),
      longTaskCount: state.longTasks.length,
      inpMs: Math.round(Math.max(0, ...state.interactions)),
      firstContentfulPaintMs: Math.round(firstContentfulPaint?.startTime ?? 0),
      responseStartMs: Math.round(responseStartMs),
      renderDelayMs: Math.round(renderDelayMs),
      renderDelayPercent: state.lcpMs > 0 ? Number(((renderDelayMs / state.lcpMs) * 100).toFixed(1)) : 0,
    }
  })
}

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

// Unchanged from the pre-redesign mock: the grouped-grid/review/apply API
// contracts did not change, only how DensePricingWorkspace presents them.
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
          current: 'active',
          target: statusChange?.target_value ?? 'active',
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
        : 'active'
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
  return search
    ? indexes.filter(index => `synthetic product ${String(index + 1).padStart(5, '0')}`.includes(search))
    : indexes
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
    if (url.pathname === '/api/v2/exchange-rates/me') return json(route, { selections: [], rates: [] })
    if (url.pathname === '/api/v2/products/categories') return json(route, { items: [] })
    if (url.pathname === '/api/v2/source-profiles/channels') return json(route, {
      items: options.channelIds.map(channelId => ({
        channelId,
        name: channelName(channelId),
        connectorType: channelId.split(':')[0],
        capabilityVersion: 'acceptance-v1',
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

// The Figma-approved table commits an edit on blur/Enter (matching a real
// user typing then tabbing away), not per keystroke. This replaces the old
// dblclick-into-the-Handsontable-editor pattern.
async function editField(page: Page, listingId: string, field: 'price' | 'stock', value: string) {
  const input = page.locator(`input[data-listing-id="${listingId}"][data-target-field="${field}"]`)
  await input.fill(value)
  await input.press('Enter')
}

function targetInput(page: Page, listingId: string, field: 'price' | 'stock') {
  return page.locator(`input[data-listing-id="${listingId}"][data-target-field="${field}"]`)
}

function availabilitySelect(page: Page, listingId: string) {
  return page.locator(`select[data-listing-id="${listingId}"][data-target-field="status"]`)
}

function listingRow(page: Page, listingId: string) {
  return page.locator(`tr[data-listing-id="${listingId}"]`)
}

async function submitSearch(page: Page, search: ReturnType<Page['locator']>, value: string) {
  await search.fill(value)
  await search.press('Enter')
}

test('matches Wanted Model with direct field editing, availability changes, bulk edit, one Review/Dry Run and one Apply', async ({ page, browser, browserName }) => {
  test.setTimeout(120_000)
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

  // -- Product-channel Listing rows + exact Listing identity -----------------
  const table = page.locator('[data-products-table]')
  await expect(table).toBeVisible({ timeout: 30_000 })
  expect(new URL(page.url()).pathname).toBe('/products')
  expect(audit.catalogBootstrapCalls).toBe(1)
  // One page = 100 products x 3 channels; no virtualization, every row is real DOM.
  await expect(page.locator('[data-pricing-row]')).toHaveCount(300)
  const timeToFirstEditableCellMs = Math.round(performance.now() - workflowStarted)
  await expect(listingRow(page, 'listing-1-1')).toHaveAttribute('data-channel-id', 'woocommerce:primary')
  await expect(targetInput(page, 'listing-1-1', 'price')).toHaveAttribute('data-listing-id', 'listing-1-1')
  await expect(targetInput(page, 'listing-2-1', 'price')).toHaveAttribute('data-listing-id', 'listing-2-1')

  const search = page.getByRole('searchbox', { name: 'Search products...' })
  await submitSearch(page, search, 'Synthetic Product')
  await expect.poll(() => audit.requests.some(request => request.pathname.endsWith('/grouped-grid') && request.search.includes('search=Synthetic'))).toBe(true)
  await submitSearch(page, search, '')
  await expect(page.locator('[data-pricing-row]')).toHaveCount(300)

  // -- Blocked field protection ------------------------------------------------
  // Products 21-23's first channel are seeded as source-blocked (stale cache).
  await expect(targetInput(page, 'listing-21-1', 'price')).toHaveAttribute('data-cell-status', 'blocked')

  // -- Price editing + Stock editing -------------------------------------------
  const editTenStarted = performance.now()
  for (let index = 1; index <= 10; index += 1) {
    await editField(page, `listing-${index}-1`, 'price', String(20_000 + index * 100))
  }
  const editTenProductsMs = Math.round(performance.now() - editTenStarted)
  for (let index = 1; index <= 10; index += 1) {
    await expect(targetInput(page, `listing-${index}-1`, 'price')).toHaveValue(String(20_000 + index * 100))
  }
  await editField(page, 'listing-1-1', 'stock', '31')
  await expect(targetInput(page, 'listing-1-1', 'stock')).toHaveValue('31')
  await expect(page.locator('[data-products-save]')).toBeEnabled()

  // -- Availability changes -----------------------------------------------------
  await availabilitySelect(page, 'listing-1-1').selectOption('inactive')
  await expect(availabilitySelect(page, 'listing-1-1')).toHaveValue('inactive')
  await expect(availabilitySelect(page, 'listing-1-1')).toHaveAttribute('data-cell-status', 'edited')

  // -- Reset a row's pending changes via row actions ---------------------------
  // A separate, otherwise-untouched Listing so this does not interact with
  // the price edits above or the bulk edit below.
  await editField(page, 'listing-11-1', 'price', '99999')
  await expect(targetInput(page, 'listing-11-1', 'price')).toHaveAttribute('data-cell-status', 'edited')
  await page.locator('[data-row-menu-trigger][data-listing-id="listing-11-1"]').click()
  await page.locator('[data-row-menu-action="reset"]').click()
  await expect(targetInput(page, 'listing-11-1', 'price')).toHaveAttribute('data-cell-status', 'unchanged')

  // -- Bulk edit: live preview + Apply to Draft --------------------------------
  // Bulk Edit's default scope is every Listing on the loaded page; narrow the
  // page via search first so the bulk result is a small, predictable set
  // instead of ~300 recomputed prices across the whole page.
  await submitSearch(page, search, 'Synthetic Product 00024')
  await expect(page.locator('[data-pricing-row]')).toHaveCount(3)
  await page.locator('[data-products-bulk-edit]').click()
  const bulkDialog = page.locator('[data-bulk-edit-dialog]')
  await expect(bulkDialog).toBeVisible()
  await expect(bulkDialog).toContainText('1 products selected')
  await captureScreenshot(page, 'bulk-edit-dialog.png')
  await bulkDialog.locator('[data-bulk-pricing-value]').fill('5')
  // productNumber 24, channel 0: base 10_000 + 24*100 = 12_400; +5% = 13_020.
  await expect(bulkDialog.locator('[data-bulk-preview]')).toContainText('13020')
  await bulkDialog.locator('[data-bulk-apply]').click()
  await expect(bulkDialog).toBeHidden()
  await expect(targetInput(page, 'listing-24-1', 'price')).toHaveValue('13020')
  await submitSearch(page, search, '')
  await expect(page.locator('[data-pricing-row]')).toHaveCount(300)

  // -- Blocked field protection under bulk edit --------------------------------
  // productNumber 21 (channel 0) is source-blocked; a page-wide bulk 5%
  // increase must not have touched it.
  await expect(targetInput(page, 'listing-21-1', 'price')).toHaveAttribute('data-cell-status', 'blocked')
  await expect(targetInput(page, 'listing-21-1', 'price')).toHaveValue(String(10_000 + 21 * 100))

  // -- Pagination preserves in-memory edits -------------------------------------
  await page.getByRole('button', { name: 'Next' }).click()
  await expect(page.getByText('Page 2')).toBeVisible()
  await page.getByRole('button', { name: 'Previous' }).click()
  await expect(page.getByText('Page 1')).toBeVisible()
  await expect(targetInput(page, 'listing-1-1', 'price')).toHaveValue('20100')
  await expect(targetInput(page, 'listing-24-1', 'price')).toHaveValue('13020')

  await captureScreenshot(page, 'wanted-model-products-table.png')

  // -- Review changes / Dry-run safety ------------------------------------------
  const saveButton = page.locator('[data-products-save]')
  await expect(saveButton).toBeEnabled()
  await saveButton.click()
  await expect(page.getByRole('heading', { name: 'Review Changes' })).toBeVisible()
  await captureScreenshot(page, 'wanted-model-review.png')
  await expect.poll(() => audit.reviewCalls).toBe(1)
  expect(audit.dryRunCalls).toBe(1)
  // 10 manual price edits + 1 stock edit + 1 availability change + 3 bulk
  // price changes (product 24, all channels) = 15; the reset Listing-11-1
  // edit must not appear at all.
  expect(audit.draftChanges).toHaveLength(15)
  expect(audit.draftChanges).toContainEqual(expect.objectContaining({
    listing_id: 'listing-1-1', channel_id: 'woocommerce:primary', field: 'status', target_value: 'inactive',
  }))
  expect(audit.draftChanges).toContainEqual(expect.objectContaining({
    listing_id: 'listing-1-1', channel_id: 'woocommerce:primary', field: 'stock', target_value: '31',
  }))
  expect(audit.draftChanges).toContainEqual(expect.objectContaining({
    listing_id: 'listing-24-1', channel_id: 'woocommerce:primary', field: 'price', target_value: '13020',
  }))
  expect(audit.draftChanges).not.toContainEqual(expect.objectContaining({ listing_id: 'listing-11-1' }))
  expect(audit.draftChanges).not.toContainEqual(expect.objectContaining({ listing_id: 'listing-21-1' }))
  // Reopening the same review must not create a duplicate Review/Dry Run.
  await page.getByRole('button', { name: 'Back to Grid' }).first().click()
  await expect(table).toBeVisible()
  await saveButton.click()
  await expect(page.getByRole('heading', { name: 'Review Changes' })).toBeVisible()
  expect(audit.reviewCalls).toBe(1)
  expect(audit.dryRunCalls).toBe(1)

  // -- Apply flow -----------------------------------------------------------------
  const applyButton = page.locator('[data-pricing-apply]')
  await expect(applyButton).toBeEnabled()
  await applyButton.click()
  await expect(page.getByRole('dialog', { name: 'Apply confirmation' })).toBeVisible()
  await page.getByRole('button', { name: 'Confirm Apply' }).click()
  await expect(page.getByText('Apply — Partially Applied')).toBeVisible()
  await expect(page.getByText('Reconciliation Required')).toBeVisible()
  const applyResults = page.getByRole('region', { name: 'Apply results' })
  await expect(applyResults).toBeVisible()
  await applyResults.scrollIntoViewIfNeeded()
  await captureScreenshot(page, 'wanted-model-apply-results.png')

  expect(audit.reviewCalls).toBe(1)
  expect(audit.dryRunCalls).toBe(1)
  expect(audit.applyCalls).toBe(1)
  expect(new URL(page.url()).pathname).toBe('/products')
  expect(audit.external).toEqual([])
  console.log(`PRICING_ACCEPTANCE ${JSON.stringify({
    browserName,
    ...(await browserIdentity(browser)),
    timeToFirstEditableCellMs,
    editTenProductsMs,
  })}`)
})

test('renders critical Products controls before deferred Grid startup', async ({ page, browser, browserName }) => {
  test.setTimeout(60_000)
  await installStartupPerformanceObservers(page)
  const audit = createAudit()
  const options: MockOptions = {
    workspaceId: 'pricing-critical-controls',
    workspaceName: 'Products',
    totalProducts: 6,
    channelIds: acceptanceChannels,
    defaultPageSize: 100,
  }
  await installMocks(page, options, audit)
  await page.setViewportSize({ width: 1440, height: 900 })

  await page.goto('/products', { waitUntil: 'domcontentloaded' })
  await expect(page.locator('[data-products-critical-controls]').first()).toBeVisible({ timeout: 10_000 })
  // LCP delivery is asynchronous to paint; allow the buffered observer to
  // receive the final critical-controls candidate without waiting for Grid.
  await page.waitForTimeout(500)
  const metrics = {
    browserName,
    ...(await browserIdentity(browser)),
    viewport: { width: 1440, height: 900 },
    ...(await startupPerformanceMetrics(page)),
  }
  expect(audit.external).toEqual([])
  console.log(`PRODUCTS_CRITICAL_CONTROLS ${JSON.stringify(metrics)}`)
})
