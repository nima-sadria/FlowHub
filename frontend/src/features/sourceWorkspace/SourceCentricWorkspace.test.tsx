// @vitest-environment jsdom
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { changeLocale } from '../../i18n'
import { NotificationProvider } from '../../notifications/NotificationProvider'
import type { UnifiedWorkspaceService } from '../../services/unifiedWorkspace/UnifiedWorkspaceService'
import type { ReviewResource, UnifiedWorkspaceResource } from '../../services/unifiedWorkspace/types'
import { sourceWorkspaceApi } from './api'
import SourceCentricWorkspace from './SourceCentricWorkspace'
import type { GroupedListing, GroupedWorkspacePage } from './types'

;(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true

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
    container = document.createElement('div')
    document.body.appendChild(container)
    root = createRoot(container)
    vi.spyOn(sourceWorkspaceApi, 'groupedGrid').mockResolvedValue(GRID)
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
    const listingIds = Array.from(
      container.querySelectorAll<HTMLElement>('[data-listing-id]'),
      item => item.dataset.listingId,
    )
    expect(listingIds).toEqual(['snap-black', 'snap-white', 'tapsi-main', 'woo-main'])
    expect(new Set(listingIds).size).toBe(4)
    expect(container.textContent).toContain('SnappShop')
    expect(container.textContent).toContain('TapsiShop')
    expect(container.textContent).toContain('WooCommerce')
    expect(container.textContent).not.toContain('snappshop:main')
  })

  it('binds an edit from one of several marketplace Listings to that immutable Listing ID', async () => {
    await renderWorkspace(container, root, service)
    const blackListing = container.querySelector<HTMLElement>('[data-listing-id="snap-black"]')
    const targetPrice = blackListing?.querySelectorAll<HTMLInputElement>('input')[1]
    expect(targetPrice).toBeTruthy()

    await act(async () => {
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set
      setter?.call(targetPrice, '125')
      targetPrice?.dispatchEvent(new Event('input', { bubbles: true }))
    })
    const reviewButton = Array.from(container.querySelectorAll('button')).find(button => button.textContent?.includes('Review')) as HTMLButtonElement
    await act(async () => {
      reviewButton.click()
      await Promise.resolve()
    })

    expect(service.saveDraft).toHaveBeenCalledTimes(1)
    expect(vi.mocked(service.saveDraft).mock.calls[0][2]).toEqual([expect.objectContaining({
      listing_id: 'snap-black',
      channel_id: 'snappshop:main',
      field: 'price',
      target_value: '125',
    })])
  })
})

async function renderWorkspace(
  _container: HTMLElement,
  root: ReturnType<typeof createRoot>,
  service: UnifiedWorkspaceService,
) {
  await act(async () => {
    root.render(
      <NotificationProvider>
        <SourceCentricWorkspace workspace={WORKSPACE} service={service} />
      </NotificationProvider>,
    )
    await Promise.resolve()
    await new Promise(resolve => setTimeout(resolve, 0))
  })
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
