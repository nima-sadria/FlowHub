// @vitest-environment jsdom
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { changeLocale } from '../../i18n'
import { NotificationProvider } from '../../notifications/NotificationProvider'
import type { UnifiedWorkspaceService } from '../../services/unifiedWorkspace/UnifiedWorkspaceService'
import type { DryRunResource, ReviewResource, UnifiedWorkspaceResource } from '../../services/unifiedWorkspace/types'
import { sourceWorkspaceApi } from './api'
import { formatSourceChannelDisplayName } from '../unifiedWorkspace/channelDisplayName'
import SourceCentricWorkspace from './SourceCentricWorkspace'
import type { GroupedListing, GroupedWorkspacePage, SourceChannel } from './types'

;(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true

function setInputValue(input: HTMLInputElement, value: string) {
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set
  setter?.call(input, value)
  input.dispatchEvent(new Event('input', { bubbles: true }))
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(done => { resolve = done })
  return { promise, resolve }
}

const WORKSPACE: UnifiedWorkspaceResource = {
  id: 'workspace-1',
  name: 'Daily pricing',
  entryPoint: 'source',
  ownerUserId: 1,
  status: 'active',
  version: 1,
  snapshot: { id: 'snapshot-1', checksum: 'hash', schemaVersion: '1', createdAt: '2026-07-15T08:00:00Z' },
  draft: { id: 'draft-1', version: 0, currentRevisionId: null, status: 'draft' },
  createdAt: '2026-07-15T08:00:00Z',
}

function listing(listingId: string, channelId: string, label: string): GroupedListing {
  const field = (current: string, target: string) => ({
    current,
    target,
    changed: current !== target,
    readOnly: false,
    status: 'ready' as const,
    currency: 'IRR',
    unit: 'IRR',
  })
  return {
    listingId,
    channelId,
    listingLabel: label,
    externalId: `${listingId}-external`,
    externalIdType: 'external_id',
    sku: `${listingId}-sku`,
    mappingState: 'resolved',
    cacheFreshness: 'fresh',
    state: 'ready',
    changedFields: ['price'],
    selected: false,
    reviewItemIds: [],
    fields: { price: field('100', '110'), stock: field('5', '5'), status: field('active', 'active') },
  }
}

const GRID: GroupedWorkspacePage = {
  items: [{
    sourceProductId: 'product-1',
    name: 'iPhone Cable',
    sourceKey: 'cable-1',
    cost: null,
    category: null,
    brand: null,
    productType: 'simple',
    primaryImageUrl: 'https://cdn.example.test/product-1.jpg',
    media: [{ type: 'image', url: 'https://cdn.example.test/product-1.jpg', position: 0, source: 'woocommerce' }],
    mappedChannelCount: 3,
    listingCount: 4,
    changedListingCount: 4,
    selectedListingCount: 0,
    state: 'ready',
    children: [
      listing('woo-main', 'woocommerce:primary', 'Woo main'),
      listing('snap-black', 'snappshop:main', 'Black listing'),
      listing('tapsi-main', 'tapsishop:main', 'Tapsi main'),
      listing('snap-white', 'snappshop:main', 'White listing'),
    ],
  }],
  total: 1,
  page: 1,
  pageSize: 100,
  view: 'changed',
  summary: { ready: 4, blocked: 0, unchanged: 0, selected: 0 },
  draftVersion: 0,
  revisionId: null,
  reviewId: null,
  reviewStatus: null,
  selectionChecksum: null,
}

describe('SourceCentricWorkspace Channel ordering', () => {
  let container: HTMLDivElement
  let root: ReturnType<typeof createRoot>
  let service: UnifiedWorkspaceService

  beforeEach(() => {
    window.sessionStorage.clear()
    container = document.createElement('div')
    document.body.appendChild(container)
    root = createRoot(container)
    vi.spyOn(sourceWorkspaceApi, 'groupedGrid').mockResolvedValue(GRID)
    vi.spyOn(sourceWorkspaceApi, 'channels').mockResolvedValue({ items: [
      sourceChannel('woocommerce:primary', 'WooCommerce'),
      sourceChannel('snappshop:main', 'SnappShop'),
      sourceChannel('tapsishop:main', 'TapsiShop'),
    ] })
    service = createService()
  })

  afterEach(async () => {
    act(() => root.unmount())
    container.remove()
    vi.restoreAllMocks()
    await changeLocale('en')
  })

  it.each([
    ['en', 'ltr'],
    ['fa', 'rtl'],
  ] as const)('keeps grouped Listing identity in the same display-name order in %s (%s)', async (locale, direction) => {
    await changeLocale(locale)
    await renderWorkspace(container, root, service)

    expect(document.documentElement.dir).toBe(direction)
    const listingIds = new Set(Array.from(
      container.querySelectorAll<HTMLElement>('[data-listing-id]'),
      item => item.dataset.listingId,
    ))
    expect(listingIds).toEqual(new Set(['snap-black', 'snap-white', 'tapsi-main', 'woo-main']))
    expect(container.textContent).toContain(formatSourceChannelDisplayName(sourceChannel('snappshop:main', 'SnappShop')))
    expect(container.textContent).toContain(formatSourceChannelDisplayName(sourceChannel('tapsishop:main', 'TapsiShop')))
    expect(container.textContent).toContain(formatSourceChannelDisplayName(sourceChannel('woocommerce:primary', 'WooCommerce')))
    expect(container.textContent).not.toContain('snappshop:main')
  })

  it('portals the row Actions menu outside the clipping products table so it is never hard-clipped', async () => {
    await renderWorkspace(container, root, service)
    const trigger = container.querySelector<HTMLButtonElement>('[data-row-menu-trigger][data-listing-id="snap-black"]')
    expect(trigger).toBeTruthy()

    await act(async () => {
      trigger?.click()
      await Promise.resolve()
    })

    const menu = document.querySelector('[data-row-actions-portal]')
    expect(menu).toBeTruthy()
    // .fh-products-card clips overflow-y; the menu must not be its descendant.
    expect(container.querySelector('[data-row-actions-portal]')).toBeNull()
    expect(menu?.closest('[data-products-table]')).toBeNull()
    expect((menu as HTMLElement).style.position).toBe('fixed')
  })

  it('omits its PageShell when embedded in the Products page', async () => {
    await renderWorkspace(container, root, service, true)

    expect(container.querySelector('[data-pricing-workspace]')).toBeTruthy()
    expect(container.querySelector('[data-products-critical-controls]')).toBeTruthy()
    expect(container.querySelector('.fh-page')).toBeNull()
  })

  it('renders canonical product media and falls back after an image error', async () => {
    await renderWorkspace(container, root, service)

    const thumbnail = container.querySelector('[data-product-thumbnail]')
    const image = thumbnail?.querySelector('img')
    expect(image?.getAttribute('src')).toBe('https://cdn.example.test/product-1.jpg')
    expect(sourceWorkspaceApi.groupedGrid).toHaveBeenCalledTimes(1)

    await act(async () => image?.dispatchEvent(new Event('error')))

    expect(thumbnail?.querySelector('img')).toBeNull()
    expect(thumbnail?.querySelector('svg')).toBeTruthy()
  })

  it('renders the existing product icon when canonical media is unavailable', async () => {
    vi.mocked(sourceWorkspaceApi.groupedGrid).mockResolvedValue({
      ...GRID,
      items: [{ ...GRID.items[0], primaryImageUrl: null, media: [] }],
    })

    await renderWorkspace(container, root, service)

    const thumbnail = container.querySelector('[data-product-thumbnail]')
    expect(thumbnail?.querySelector('img')).toBeNull()
    expect(thumbnail?.querySelector('svg')).toBeTruthy()
  })

  it('binds an edit from one of several marketplace Listings to that immutable Listing ID', async () => {
    await renderWorkspace(container, root, service)
    const targetPrice = container.querySelector<HTMLInputElement>('[data-listing-id="snap-black"][data-target-field="price"]')
    expect(targetPrice).toBeTruthy()

    await act(async () => {
      targetPrice?.focus()
      setInputValue(targetPrice!, '125')
      targetPrice?.blur()
    })
    const saveButton = container.querySelector<HTMLButtonElement>('[data-products-save]')
    expect(saveButton).toBeTruthy()
    expect(saveButton?.disabled).toBe(false)
    await act(async () => {
      saveButton?.click()
      await Promise.resolve()
    })

    expect(service.saveDraft).toHaveBeenCalledTimes(1)
    expect(vi.mocked(service.saveDraft).mock.calls[0][2]).toEqual(expect.arrayContaining([expect.objectContaining({
      listing_id: 'snap-black',
      channel_id: 'snappshop:main',
      field: 'price',
      target_value: '125',
    })]))
  })

  it('flushes an in-progress edit before a filter change can unmount its row', async () => {
    await renderWorkspace(container, root, service)
    const targetPrice = container.querySelector<HTMLInputElement>('[data-listing-id="snap-black"][data-target-field="price"]')!

    // Deliberately do not blur: the Owner is still mid-edit when they reach
    // for a filter dropdown instead of clicking elsewhere first.
    await act(async () => {
      targetPrice.focus()
      setInputValue(targetPrice, '125')
    })

    const channelSelect = container.querySelector<HTMLSelectElement>('select[name="channelId"]')!
    await act(async () => {
      channelSelect.value = 'tapsishop:main'
      channelSelect.dispatchEvent(new Event('change', { bubbles: true }))
      await Promise.resolve()
    })

    const saveButton = container.querySelector<HTMLButtonElement>('[data-products-save]')!
    await act(async () => {
      saveButton.click()
      await Promise.resolve()
    })

    expect(service.saveDraft).toHaveBeenCalledTimes(1)
    expect(vi.mocked(service.saveDraft).mock.calls[0][2]).toEqual(expect.arrayContaining([expect.objectContaining({
      listing_id: 'snap-black',
      channel_id: 'snappshop:main',
      field: 'price',
      target_value: '125',
    })]))
  })

  it('renders the Settings display unit while persisting the exact native Listing value', async () => {
    await renderWorkspace(container, root, service, false, { currency: 'IRR', unit: 'TOMAN' })
    const targetPrice = container.querySelector<HTMLInputElement>('[data-listing-id="snap-black"][data-target-field="price"]')!
    expect(container.querySelector('[data-price-unit]')?.textContent).toContain('Toman')
    expect(targetPrice.value).toBe('11')

    await act(async () => {
      targetPrice.focus()
      setInputValue(targetPrice, '12.5')
      targetPrice.blur()
    })
    await act(async () => {
      container.querySelector<HTMLButtonElement>('[data-products-save]')?.click()
      await Promise.resolve()
    })

    expect(vi.mocked(service.saveDraft).mock.calls[0][2]).toEqual(expect.arrayContaining([expect.objectContaining({
      listing_id: 'snap-black',
      target_value: '125',
      currency: 'IRR',
      unit: 'IRR',
    })]))
  })

  it('merges the full local session into the Draft and excludes only the explicitly deselected field from Selection', async () => {
    const created: ReviewResource = {
      id: 'review-1',
      workspaceId: WORKSPACE.id,
      snapshotId: WORKSPACE.snapshot.id,
      draftRevisionId: 'revision-1',
      status: 'ready',
      checksum: 'review-checksum',
      summary: { total: 4, eligible: 4, blocked: 0, warnings: 0 },
      items: [
        reviewItemFor('review-woo', 'woo-main', 'woocommerce:primary'),
        reviewItemFor('review-snap-black', 'snap-black', 'snappshop:main'),
        reviewItemFor('review-tapsi', 'tapsi-main', 'tapsishop:main'),
        reviewItemFor('review-snap-white', 'snap-white', 'snappshop:main'),
      ],
      staleReason: null,
    }
    service.createReview = vi.fn().mockResolvedValue(created)
    service.saveSelection = vi.fn().mockResolvedValue({
      reviewId: created.id, selectedItemIds: [], selectionChecksum: 'checksum-1', selectionVersion: 1,
    })
    await renderWorkspace(container, root, service)
    const trigger = container.querySelector<HTMLButtonElement>('[data-row-menu-trigger][data-listing-id="snap-black"]')
    expect(trigger).toBeTruthy()

    await act(async () => {
      trigger?.click()
      await Promise.resolve()
    })
    // The row-actions menu portals to document.body to escape the products
    // table's clipping ancestor -- it is a sibling of container, not a
    // descendant, so it must be queried from the document.
    const excludeAction = document.querySelector<HTMLButtonElement>('[data-row-menu-action="toggle-selection"]')
    expect(excludeAction).toBeTruthy()
    expect(excludeAction?.disabled).toBe(false)
    await act(async () => {
      excludeAction?.click()
      await Promise.resolve()
    })

    const saveButton = container.querySelector<HTMLButtonElement>('[data-products-save]')
    await act(async () => {
      saveButton?.click()
      await Promise.resolve()
    })

    // Draft save now merges the current session's full local scope -- including
    // the deselected field's still-accurate target value -- instead of wiping
    // out every field outside this one page with a wholesale replace.
    const savedChanges = vi.mocked(service.saveDraft).mock.calls[0][2]
    expect(savedChanges).toHaveLength(4)
    expect(savedChanges).toContainEqual(expect.objectContaining({
      listing_id: 'snap-black',
      channel_id: 'snappshop:main',
      field: 'price',
      target_value: '110',
    }))
    expect(vi.mocked(service.saveDraft).mock.calls[0][3]).toBe('merge')

    // Every eligible Review item is auto-selected by identity; only the field
    // the Owner explicitly excluded this Preview is left out.
    const selectedIds = vi.mocked(service.saveSelection).mock.calls[0][2]
    expect(selectedIds).toEqual(['review-woo', 'review-tapsi', 'review-snap-white'])
  })

  it('reconciles draftVersion after a successful Draft save even when a newer local edit invalidates the in-flight Review', async () => {
    let resolveCreateReview!: (value: ReviewResource) => void
    const pendingReview = new Promise<ReviewResource>(resolve => { resolveCreateReview = resolve })
    const emptyReview: ReviewResource = {
      id: 'review-1', workspaceId: WORKSPACE.id, snapshotId: WORKSPACE.snapshot.id,
      draftRevisionId: 'revision-1', status: 'ready', checksum: 'review-checksum',
      summary: { total: 0, eligible: 0, blocked: 0, warnings: 0 }, items: [], staleReason: null,
    }
    service.createReview = vi.fn().mockReturnValueOnce(pendingReview).mockResolvedValue(emptyReview)
    await renderWorkspace(container, root, service)

    const saveButton = container.querySelector<HTMLButtonElement>('[data-products-save]')!
    await act(async () => {
      saveButton.click()
      await Promise.resolve()
    })
    // The Draft save itself already resolved (server draftVersion advanced to
    // 1); createReview is still pending. expected_version on this first call
    // was the pre-save value.
    expect(service.saveDraft).toHaveBeenCalledTimes(1)
    expect(vi.mocked(service.saveDraft).mock.calls[0][1]).toBe(0)

    // A newer local edit arrives while the Review round-trip is still in flight
    // -- an entirely normal Owner interaction, not a conflicting concurrent session.
    const targetPrice = container.querySelector<HTMLInputElement>('[data-listing-id="snap-black"][data-target-field="price"]')!
    await act(async () => {
      targetPrice.focus()
      setInputValue(targetPrice, '130')
      targetPrice.blur()
    })

    await act(async () => {
      resolveCreateReview(emptyReview)
      await Promise.resolve()
      await Promise.resolve()
    })

    // The next Save must use the server-confirmed version from the save that
    // actually succeeded (1), not the stale pre-save value (0) -- otherwise
    // it is rejected as DRAFT_VERSION_CONFLICT even though nothing is stale.
    await act(async () => {
      saveButton.click()
      await Promise.resolve()
    })
    expect(service.saveDraft).toHaveBeenCalledTimes(2)
    expect(vi.mocked(service.saveDraft).mock.calls[1][1]).toBe(1)
  })

  it('shows Dry Run running state and keeps Review, confirmation, and Apply unavailable', async () => {
    const currentReview = reviewForGrid()
    const pendingDryRun = deferred<DryRunResource>()
    service.createReview = vi.fn().mockResolvedValue(currentReview)
    service.saveSelection = vi.fn().mockResolvedValue(selectionFor(currentReview))
    service.runDryRun = vi.fn().mockReturnValue(pendingDryRun.promise)
    await renderWorkspace(container, root, service)

    await startOwnerFlow(container)
    expect(service.runDryRun).toHaveBeenCalledWith(WORKSPACE.id, currentReview.id)
    expect(container.querySelector('[role="status"]')?.textContent).toContain('Verifying current Channel state')
    expect(container.querySelector('[data-pricing-apply]')).toBeNull()
    expect(container.querySelector('[data-products-save]')).toHaveProperty('disabled', true)
    expect(container.textContent).not.toContain('Confirm selected Apply')
  })

  it('does not make Apply available from selection alone before a passed Dry Run', async () => {
    const currentReview = reviewForGrid()
    const pendingDryRun = deferred<DryRunResource>()
    service.createReview = vi.fn().mockResolvedValue(currentReview)
    service.saveSelection = vi.fn().mockResolvedValue(selectionFor(currentReview))
    service.runDryRun = vi.fn().mockReturnValue(pendingDryRun.promise)
    await renderWorkspace(container, root, service)

    await startOwnerFlow(container)
    expect(service.saveSelection).toHaveBeenCalledWith(
      WORKSPACE.id,
      currentReview.id,
      currentReview.items.map(item => item.id),
    )
    expect(container.querySelector('[data-pricing-apply]')).toBeNull()
    expect(container.textContent).not.toContain('Confirm selected Apply')
  })

  it('shows exact Dry Run counts and enables manifest review only after a passed current Dry Run', async () => {
    const currentReview = reviewForGrid()
    const dryRun = passedDryRun({ reviewedCount: 4, writeCount: 2, blockerCount: 0 })
    service.createReview = vi.fn().mockResolvedValue(currentReview)
    service.saveSelection = vi.fn().mockResolvedValue(selectionFor(currentReview))
    service.runDryRun = vi.fn().mockResolvedValue(dryRun)
    await renderWorkspace(container, root, service)

    await startOwnerFlow(container)
    const applyButton = container.querySelector<HTMLButtonElement>('[data-pricing-apply]')
    expect(applyButton?.disabled).toBe(false)
    expect(container.querySelector('[data-dry-run-summary]')?.textContent).toContain('Verified writes: 2')
    expect(container.querySelector('[data-dry-run-summary]')?.textContent).toContain('Already current: 2')
    expect(container.querySelector('[data-dry-run-summary]')?.textContent).toContain('Blocked: 0')

    await act(async () => { applyButton?.click(); await Promise.resolve() })
    expect(container.textContent).toContain('Confirm selected Apply')
    expect(container.textContent).toContain('iPhone Cable')
  })

  it('invalidates a passed Dry Run and removes its manifest review when selection changes', async () => {
    const currentReview = reviewForGrid()
    service.createReview = vi.fn().mockResolvedValue(currentReview)
    service.saveSelection = vi.fn().mockResolvedValue(selectionFor(currentReview))
    service.runDryRun = vi.fn().mockResolvedValue(passedDryRun())
    await renderWorkspace(container, root, service)

    await startOwnerFlow(container)
    expect(container.querySelector<HTMLButtonElement>('[data-pricing-apply]')?.disabled).toBe(false)
    await act(async () => {
      container.querySelector<HTMLButtonElement>('.fh-pricing-dialog .fh-button-secondary')?.click()
      await Promise.resolve()
    })
    const trigger = container.querySelector<HTMLButtonElement>('[data-row-menu-trigger][data-listing-id="snap-black"]')!
    await act(async () => { trigger.click(); await Promise.resolve() })
    await act(async () => {
      document.querySelector<HTMLButtonElement>('[data-row-menu-action="toggle-selection"]')?.click()
      await Promise.resolve()
    })

    expect(container.querySelector('[data-pricing-apply]')).toBeNull()
    expect(container.textContent).not.toContain('Confirm selected Apply')
    expect(container.querySelector<HTMLButtonElement>('[data-products-save]')?.disabled).toBe(false)
  })

  it.each([
    ['CHANNEL_DRIFT', 'Channel changed since Preview'],
    ['CHANNEL_STATE_UNVERIFIABLE', 'Unable to verify current Channel state'],
  ] as const)('blocks Apply with the distinct human-readable %s state', async (reason, message) => {
    const currentReview = reviewForGrid()
    service.createReview = vi.fn().mockResolvedValue(currentReview)
    service.saveSelection = vi.fn().mockResolvedValue(selectionFor(currentReview))
    service.runDryRun = vi.fn().mockResolvedValue({
      ...passedDryRun(), status: 'blocked', manifestId: undefined, manifestChecksum: undefined,
      operations: undefined, affectedChannelIds: undefined, blockerCount: 1,
      scopes: [{ reviewItemId: currentReview.items[0].id, disposition: 'blocked', reason }],
    })
    await renderWorkspace(container, root, service)

    await startOwnerFlow(container)
    expect(container.querySelector('[data-dry-run-status]')?.textContent).toContain(message)
    expect(container.querySelector('[data-pricing-apply]')).toBeNull()
    expect(container.textContent).not.toContain('Confirm selected Apply')
  })
})

async function renderWorkspace(
  _container: HTMLElement,
  root: ReturnType<typeof createRoot>,
  service: UnifiedWorkspaceService,
  embedded = false,
  displayProfile: { currency: string; unit: string } | null = null,
) {
  await act(async () => {
    root.render(
      <NotificationProvider>
        <SourceCentricWorkspace workspace={WORKSPACE} service={service} embedded={embedded} displayProfile={displayProfile} />
      </NotificationProvider>,
    )
    await Promise.resolve()
    await new Promise(resolve => setTimeout(resolve, 0))
  })
}

function reviewItemFor(id: string, listingId: string, channelId: string) {
  return {
    id,
    canonicalProductId: 'product-1',
    listingId,
    channelId,
    field: 'price' as const,
    current: '100',
    target: '110',
    validationState: 'ready',
    warnings: [],
    errors: [],
    eligible: true,
    selected: false,
  }
}

function sourceChannel(channelId: string, name: string): SourceChannel {
  return {
    channelId,
    name,
    connectorType: channelId.split(':')[0],
    capabilityVersion: 'production-shape-v1',
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
  }
}

function createService(): UnifiedWorkspaceService {
  const review: ReviewResource = {
    id: 'review-1',
    workspaceId: WORKSPACE.id,
    snapshotId: WORKSPACE.snapshot.id,
    draftRevisionId: 'revision-1',
    status: 'ready',
    checksum: 'review-checksum',
    summary: { total: 0, eligible: 0, blocked: 0, warnings: 0 },
    items: [],
    staleReason: null,
  }
  return {
    createManual: vi.fn(),
    getWorkspace: vi.fn(),
    getGrid: vi.fn(),
    saveDraft: vi.fn().mockResolvedValue({ id: 'revision-1', revisionNumber: 1, checksum: 'revision-checksum', draftVersion: 1 }),
    createReview: vi.fn().mockResolvedValue(review),
    saveSelection: vi.fn(),
    applySelected: vi.fn(),
    getApply: vi.fn(),
    reconcileApply: vi.fn(),
    getPreferences: vi.fn(),
    savePreferences: vi.fn(),
  }
}

function reviewForGrid(): ReviewResource {
  return {
    id: 'review-owner-flow', workspaceId: WORKSPACE.id, snapshotId: WORKSPACE.snapshot.id,
    draftRevisionId: 'revision-1', status: 'ready', checksum: 'review-owner-flow-checksum',
    summary: { total: 4, eligible: 4, blocked: 0, warnings: 0 },
    items: [
      reviewItemFor('review-woo', 'woo-main', 'woocommerce:primary'),
      reviewItemFor('review-snap-black', 'snap-black', 'snappshop:main'),
      reviewItemFor('review-tapsi', 'tapsi-main', 'tapsishop:main'),
      reviewItemFor('review-snap-white', 'snap-white', 'snappshop:main'),
    ],
    staleReason: null,
  }
}

function selectionFor(review: ReviewResource) {
  return {
    reviewId: review.id,
    selectedItemIds: review.items.map(item => item.id),
    selectionChecksum: 'selection-owner-flow-checksum',
    selectionVersion: 1,
  }
}

function passedDryRun(overrides: Partial<DryRunResource> = {}): DryRunResource {
  return {
    id: 'dry-run-owner-flow', status: 'passed', reviewedCount: 4, writeCount: 4, blockerCount: 0,
    evidenceChecksum: 'e'.repeat(64),
    scopes: [
      { reviewItemId: 'review-woo', disposition: 'write', reason: null },
      { reviewItemId: 'review-snap-black', disposition: 'write', reason: null },
      { reviewItemId: 'review-tapsi', disposition: 'write', reason: null },
      { reviewItemId: 'review-snap-white', disposition: 'write', reason: null },
    ],
    manifestId: 'manifest-owner-flow', manifestChecksum: 'm'.repeat(64),
    operations: [{
      id: 'operation-owner-flow', reviewItemId: 'review-woo', canonicalProductId: 'product-1',
      listingId: 'woo-main', channelId: 'woocommerce:primary', field: 'price', current: '100',
      target: '110', currency: 'IRR', unit: 'IRR',
    }],
    affectedChannelIds: ['woocommerce:primary'],
    ...overrides,
  }
}

async function startOwnerFlow(container: HTMLElement) {
  await act(async () => {
    container.querySelector<HTMLButtonElement>('[data-products-save]')?.click()
    await Promise.resolve()
    await Promise.resolve()
    await Promise.resolve()
  })
}
