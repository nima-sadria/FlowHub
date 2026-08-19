// @vitest-environment jsdom
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { changeLocale } from '../../i18n'
import { NotificationProvider } from '../../notifications/NotificationProvider'
import type { UnifiedWorkspaceService } from '../../services/unifiedWorkspace/UnifiedWorkspaceService'
import type { ReviewResource, UnifiedWorkspaceResource } from '../../services/unifiedWorkspace/types'
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

  it('saves only exact selected fields with replace mode after manual deselection', async () => {
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

    const savedChanges = vi.mocked(service.saveDraft).mock.calls[0][2]
    expect(savedChanges).not.toContainEqual(expect.objectContaining({
      listing_id: 'snap-black',
      channel_id: 'snappshop:main',
      field: 'price',
    }))
    expect(savedChanges).toHaveLength(3)
    expect(savedChanges).toContainEqual(expect.objectContaining({
      listing_id: 'woo-main',
      channel_id: 'woocommerce:primary',
      field: 'price',
      target_value: '110',
    }))
    expect(vi.mocked(service.saveDraft).mock.calls[0][3]).toBe('replace')
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
