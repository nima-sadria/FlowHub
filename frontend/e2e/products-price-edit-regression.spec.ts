import { expect, test, type Page, type Route } from '@playwright/test'
import {
  PRODUCTS,
  WORKSPACE_ID,
  installProductsMocks,
  json,
  seedSession,
  type TrafficAudit,
} from './products-fixtures'

// Regression coverage for PR #3 (Products price-edit CAS conflict, Actions
// menu clipping, filter data-loss). Reuses the Products Playwright harness
// from products-screen.spec.ts rather than a second one. All network
// traffic is mocked; nothing leaves the isolated browser.

const REVIEW_ITEM_ID = 'review-item-woo-price'

/**
 * A minimal stateful mock of the Draft/Review endpoints that actually
 * enforces the same CAS semantics as the real backend
 * (draft.version != expected_version -> 409 DRAFT_VERSION_CONFLICT), so a
 * regression in the frontend's version reconciliation would organically
 * produce a real conflict here rather than the test only inspecting call
 * arguments against a dumb mock.
 */
function installDraftReviewMocks(page: Page) {
  let draftVersion = 0
  let latestRevisionId = ''
  let saveCallCount = 0
  const capturedSaves: Array<{ expectedVersion: number; targetValue: string }> = []

  page.route('**/api/v2/unified-workspaces/*/draft/revisions', async (route: Route) => {
    saveCallCount += 1
    const body = route.request().postDataJSON() as { expected_version: number; changes: Array<{ target_value: string }> }
    capturedSaves.push({ expectedVersion: body.expected_version, targetValue: body.changes[0]?.target_value ?? '' })
    if (body.expected_version !== draftVersion) {
      return json(route, {
        code: 'DRAFT_VERSION_CONFLICT',
        message: 'Draft was saved from an obsolete version.',
        context: { expected: body.expected_version, actual: draftVersion },
      }, 409)
    }
    draftVersion += 1
    latestRevisionId = `revision-${draftVersion}`
    return json(route, {
      id: latestRevisionId,
      revisionNumber: draftVersion,
      checksum: `checksum-${draftVersion}`,
      draftVersion,
      noOp: false,
    }, 201)
  })

  page.route('**/api/v2/unified-workspaces/*/reviews', async (route: Route) => {
    if (route.request().method() !== 'POST') return route.fallback()
    return json(route, {
      id: 'review-1',
      workspaceId: WORKSPACE_ID,
      snapshotId: 'snapshot-1',
      draftRevisionId: latestRevisionId,
      status: 'ready',
      checksum: 'review-checksum',
      summary: { total: 1, eligible: 1, blocked: 0, warnings: 0 },
      items: [{
        id: REVIEW_ITEM_ID,
        canonicalProductId: 'p1',
        listingId: 'p1-woo',
        channelId: 'woocommerce:primary',
        field: 'price',
        current: '129',
        target: '150',
        validationState: 'ready',
        warnings: [],
        errors: [],
        eligible: true,
        selected: false,
      }],
      staleReason: null,
    }, 201)
  })

  page.route('**/api/v2/unified-workspaces/*/reviews/*/selection', async (route: Route) => {
    return json(route, { selectionChecksum: 'selection-checksum-1' }, 200)
  })

  return {
    capturedSaves: () => capturedSaves,
    saveCallCount: () => saveCallCount,
    currentDraftVersion: () => draftVersion,
  }
}

async function gotoProducts(page: Page, audit: TrafficAudit) {
  await installProductsMocks(page, audit)
  await seedSession(page, 'en', 'light')
  await page.goto('/products')
  await expect(page.locator('[data-products-table]')).toBeVisible()
}

test.describe('Products price-edit CAS regression (PR #3)', () => {
  test('a newer edit made while Save & Review is in flight does not cause a false obsolete-version conflict on retry', async ({ page }) => {
    const audit: TrafficAudit = { externalRequests: [], unhandledApiRequests: [] }
    await gotoProducts(page, audit)
    const mock = installDraftReviewMocks(page)

    const priceInput = page.locator('[data-listing-id="p1-woo"][data-target-field="price"]')
    await priceInput.fill('150')
    await priceInput.blur()

    const saveButton = page.getByTestId ? page.locator('[data-products-save]') : page.locator('[data-products-save]')
    await expect(saveButton).toBeEnabled()

    // Delay the review-creation response so a second, newer edit can arrive
    // while the first Save & Review round-trip is still in flight -- the
    // exact race PR #3 fixed. The Draft save itself must still succeed and
    // durably advance the server's version before this gate opens.
    let releaseReview!: () => void
    const reviewGate = new Promise<void>(resolve => { releaseReview = resolve })
    await page.route('**/api/v2/unified-workspaces/*/reviews', async route => {
      if (route.request().method() !== 'POST') return route.fallback()
      await reviewGate
      return route.fallback()
    })

    await saveButton.click()
    await expect.poll(() => mock.saveCallCount()).toBe(1)
    expect(mock.currentDraftVersion(), 'the Draft save resolved and advanced the server version before Review returns').toBe(1)

    // A newer local edit arrives while Review is still pending.
    const secondPriceInput = page.locator('[data-listing-id="p2-woo"][data-target-field="price"]')
    await secondPriceInput.fill('360')
    await secondPriceInput.blur()

    releaseReview()
    await expect(page.getByText('Review could not be completed')).toBeVisible()

    // The retry must use the server-confirmed version (1), not the stale
    // pre-save value (0) -- otherwise it is rejected as
    // DRAFT_VERSION_CONFLICT even though nothing is actually stale.
    await saveButton.click()
    await expect.poll(() => mock.saveCallCount()).toBe(2)
    const saves = mock.capturedSaves()
    expect(saves[1].expectedVersion).toBe(1)
    await expect(page.getByText('Draft was saved from an obsolete version', { exact: false })).not.toBeVisible()
    await expect(page.getByText('DRAFT_VERSION_CONFLICT', { exact: false })).not.toBeVisible()

    expect(audit.externalRequests).toEqual([])
  })

  test('a normal single edit saves and advances the Draft version with no false conflict', async ({ page }) => {
    const audit: TrafficAudit = { externalRequests: [], unhandledApiRequests: [] }
    await gotoProducts(page, audit)
    const mock = installDraftReviewMocks(page)

    const priceInput = page.locator('[data-listing-id="p1-woo"][data-target-field="price"]')
    await priceInput.fill('150')
    await priceInput.blur()

    const saveButton = page.locator('[data-products-save]')
    await saveButton.click()

    await expect.poll(() => mock.currentDraftVersion()).toBe(1)
    await expect(page.getByText('Review and Dry Run complete')).toBeVisible()
    await expect(page.getByText('Draft was saved from an obsolete version', { exact: false })).not.toBeVisible()
    expect(audit.externalRequests).toEqual([])
  })
})

test.describe('Products row Actions menu escapes the clipping table (PR #3)', () => {
  for (const dir of ['ltr', 'rtl'] as const) {
    test(`the Actions menu for a row near the bottom of a constrained-height table stays fully in the viewport (${dir})`, async ({ page }) => {
      const audit: TrafficAudit = { externalRequests: [], unhandledApiRequests: [] }
      // A short viewport forces .fh-products-card's internal scroll region
      // to be shorter than its content -- the exact condition that clipped
      // the menu before it was portaled.
      await page.setViewportSize({ width: 1280, height: 620 })
      await installProductsMocks(page, audit)
      await seedSession(page, dir === 'rtl' ? 'fa' : 'en', 'light')
      await page.goto('/products')
      await expect(page.locator('[data-products-table]')).toBeVisible()
      await expect(page.locator('html')).toHaveAttribute('dir', dir)

      const lastProduct = PRODUCTS[PRODUCTS.length - 1]
      const lastListing = lastProduct.listings[lastProduct.listings.length - 1]
      const trigger = page.locator(`[data-row-menu-trigger][data-listing-id="${lastListing.listingId}"]`)
      await trigger.scrollIntoViewIfNeeded()
      await trigger.click()

      const menu = page.locator('[data-row-actions-portal]')
      await expect(menu).toBeVisible()

      const menuBox = await menu.boundingBox()
      const viewport = page.viewportSize()
      expect(menuBox, 'the portaled menu must report real geometry').not.toBeNull()
      expect(viewport).not.toBeNull()
      if (menuBox && viewport) {
        expect(menuBox.y).toBeGreaterThanOrEqual(0)
        expect(menuBox.y + menuBox.height).toBeLessThanOrEqual(viewport.height + 1)
        expect(menuBox.x).toBeGreaterThanOrEqual(0)
        expect(menuBox.x + menuBox.width).toBeLessThanOrEqual(viewport.width + 1)
      }

      // Not a descendant of the clipping table -- the structural fix.
      expect(await page.locator('[data-products-table] [data-row-actions-portal]').count()).toBe(0)

      // And genuinely clickable, not just present in the DOM.
      const resetAction = menu.locator('[data-row-menu-action="reset"]')
      await expect(resetAction).toBeVisible()

      expect(audit.externalRequests).toEqual([])
    })
  }

  test('the Actions menu is clickable on a narrow viewport', async ({ page }) => {
    const audit: TrafficAudit = { externalRequests: [], unhandledApiRequests: [] }
    await page.setViewportSize({ width: 390, height: 700 })
    await installProductsMocks(page, audit)
    await seedSession(page, 'en', 'light')
    await page.goto('/products')
    await expect(page.locator('[data-products-table]')).toBeVisible()

    const firstListing = PRODUCTS[0].listings[0]
    const trigger = page.locator(`[data-row-menu-trigger][data-listing-id="${firstListing.listingId}"]`)
    await trigger.scrollIntoViewIfNeeded()
    await trigger.click()

    const menu = page.locator('[data-row-actions-portal]')
    await expect(menu).toBeVisible()
    const menuBox = await menu.boundingBox()
    expect(menuBox).not.toBeNull()
    if (menuBox) {
      expect(menuBox.x).toBeGreaterThanOrEqual(0)
      expect(menuBox.x + menuBox.width).toBeLessThanOrEqual(390 + 1)
    }
    expect(audit.externalRequests).toEqual([])
  })
})

test.describe('Products filter change flushes an in-progress edit (PR #3)', () => {
  test('changing the Channel filter while a price input is focused commits the typed value instead of discarding it', async ({ page }) => {
    const audit: TrafficAudit = { externalRequests: [], unhandledApiRequests: [] }
    await gotoProducts(page, audit)
    const mock = installDraftReviewMocks(page)

    const priceInput = page.locator('[data-listing-id="p1-woo"][data-target-field="price"]')
    await priceInput.focus()
    await priceInput.fill('150')
    // Deliberately do not blur: change a filter instead of clicking away.
    await page.locator('select[name="channelId"]').selectOption('snappshop:main')

    // Restore the full channel set so the edited row is visible again for
    // the Save assertion below (the filter itself is not under test here).
    await page.locator('select[name="channelId"]').selectOption('')

    const saveButton = page.locator('[data-products-save]')
    await expect(saveButton).toBeEnabled()
    await saveButton.click()

    await expect.poll(() => mock.saveCallCount()).toBe(1)
    const saves = mock.capturedSaves()
    expect(saves[0].targetValue, 'the typed value must have been committed before the filter-triggered reload, not lost').toBe('150')

    expect(audit.externalRequests).toEqual([])
  })

  test('changing the Status filter while a price input is focused commits the typed value instead of discarding it', async ({ page }) => {
    const audit: TrafficAudit = { externalRequests: [], unhandledApiRequests: [] }
    await gotoProducts(page, audit)
    const mock = installDraftReviewMocks(page)

    const priceInput = page.locator('[data-listing-id="p1-woo"][data-target-field="price"]')
    await priceInput.focus()
    await priceInput.fill('175')
    const statusFilter = page.locator('.fh-chip-select select').first()
    await statusFilter.selectOption('in_stock')

    const saveButton = page.locator('[data-products-save]')
    await expect(saveButton).toBeEnabled()
    await saveButton.click()

    await expect.poll(() => mock.saveCallCount()).toBe(1)
    const saves = mock.capturedSaves()
    expect(saves[0].targetValue).toBe('175')

    expect(audit.externalRequests).toEqual([])
  })
})
