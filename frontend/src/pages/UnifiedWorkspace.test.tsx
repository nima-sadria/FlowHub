// @vitest-environment jsdom
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { changeLocale } from '../i18n'
import { NotificationProvider } from '../notifications/NotificationProvider'
import { ServiceProvider, type Services } from '../services/ServiceContext'
import type { ReviewResource, UnifiedWorkspaceResource, WorkspaceGridPage, WorkspacePreferences } from '../services/unifiedWorkspace/types'
import { sourceWorkspaceApi } from '../features/sourceWorkspace/api'
import type { GroupedWorkspacePage } from '../features/sourceWorkspace/types'
import UnifiedWorkspace from './UnifiedWorkspace'

vi.mock('@handsontable/react-wrapper', async () => {
  const React = await import('react')
  const HotTable = React.forwardRef(function MockHotTable(
    props: { data?: Array<Record<string, unknown>> },
    ref: React.ForwardedRef<unknown>,
  ) {
    const rootRef = React.useRef<HTMLDivElement>(null)
    const rows = props.data ?? []
    React.useImperativeHandle(ref, () => ({
      hotInstance: {
        getPlugin: () => ({ sort: vi.fn() }),
        getSourceDataAtRow: (row: number) => rows[row],
        rootElement: rootRef.current,
        toPhysicalRow: (row: number) => row,
      },
    }), [rows])
    return React.createElement('div', { ref: rootRef, 'data-mocked-handsontable': 'true' }, rows.map((row, index) => {
      const listingId = Object.entries(row).find(([key]) => key.endsWith('__listing_id'))?.[1]
      return React.createElement('div', {
        key: String(row.rowKey ?? index),
        'data-listing-id': String(listingId ?? ''),
        'data-pricing-row': 'true',
      }, String(row.productName ?? ''))
    }))
  })
  return { HotTable }
})

;(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true
;(globalThis as typeof globalThis & { ResizeObserver: typeof ResizeObserver }).ResizeObserver = class {
  observe() {}
  unobserve() {}
  disconnect() {}
} as unknown as typeof ResizeObserver
;(globalThis as typeof globalThis & { IntersectionObserver: typeof IntersectionObserver }).IntersectionObserver = class {
  readonly root = null
  readonly rootMargin = '0px'
  readonly thresholds = [0]

  constructor(private readonly callback: IntersectionObserverCallback) {}

  observe(target: Element) {
    this.callback([{
      boundingClientRect: target.getBoundingClientRect(),
      intersectionRatio: 1,
      intersectionRect: target.getBoundingClientRect(),
      isIntersecting: true,
      rootBounds: null,
      target,
      time: 0,
    }], this as unknown as IntersectionObserver)
  }

  unobserve() {}
  disconnect() {}
  takeRecords() { return [] }
} as unknown as typeof IntersectionObserver

const MANUAL_WORKSPACE: UnifiedWorkspaceResource = {
  id: 'workspace-1', name: 'Pricing workspace', entryPoint: 'manual', ownerUserId: 1,
  status: 'active', version: 1, snapshot: { id: 'snapshot-1', checksum: 'hash', schemaVersion: '1', createdAt: new Date().toISOString() },
  draft: { id: 'draft-1', version: 0, currentRevisionId: null, status: 'draft' }, createdAt: new Date().toISOString(),
}

const SOURCE_WORKSPACE: UnifiedWorkspaceResource = { ...MANUAL_WORKSPACE, entryPoint: 'source' }

const GRID: GroupedWorkspacePage = {
  items: [{ sourceProductId: 'product-1', name: 'Cable', sourceKey: 'SKU-1', cost: null, category: null, brand: null, productType: 'simple', mappedChannelCount: 1, listingCount: 1, changedListingCount: 1, selectedListingCount: 0, state: 'ready', children: [{ listingId: 'listing-1', channelId: 'woocommerce:primary', listingLabel: 'Main', externalId: '101', externalIdType: 'product_id', sku: 'SKU-1', mappingState: 'resolved', cacheFreshness: 'fresh', state: 'ready', changedFields: ['price'], selected: false, reviewItemIds: [], fields: { price: { current: '100', target: '100', changed: false, readOnly: false, status: 'ready', currency: 'EUR', unit: 'EUR' }, stock: { current: '5', target: '5', changed: false, readOnly: false, status: 'ready', currency: null, unit: null }, status: { current: 'publish', target: 'publish', changed: false, readOnly: true, status: 'ready', currency: null, unit: null } } }] }],
  total: 1, page: 1, pageSize: 100, view: 'all', summary: { ready: 1, blocked: 0, unchanged: 0, selected: 0 }, draftVersion: 0, revisionId: null, reviewId: null, reviewStatus: null, selectionChecksum: null,
}

let activeRoot: ReturnType<typeof createRoot>

describe('Unified Workspace pricing editor', () => {
  let container: HTMLDivElement
  let root: ReturnType<typeof createRoot>

  beforeEach(() => {
    container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container); activeRoot = root
    vi.spyOn(sourceWorkspaceApi, 'groupedGrid').mockResolvedValue(GRID)
  })
  afterEach(async () => { act(() => root.unmount()); container.remove(); vi.restoreAllMocks(); await changeLocale('en') })

  it('redirects a source-entry pricing URL to Products while preserving the Workspace identity', async () => {
    await renderWorkspace(services(SOURCE_WORKSPACE))
    expect(container.querySelector('[data-products-route]')?.textContent).toBe('?workspace=workspace-1')
    expect(container.querySelector('[data-pricing-grid]')).toBeNull()
  })

  it.each([['en', 'ltr'], ['fa', 'rtl']] as const)('keeps the compatibility redirect direction in %s', async (locale, direction) => {
    await changeLocale(locale); await renderWorkspace(services(SOURCE_WORKSPACE))
    expect(document.documentElement.dir).toBe(direction)
    expect(container.querySelector('[data-products-route]')?.textContent).toBe('?workspace=workspace-1')
  })

  it('redirects a legacy manual pricing URL to Products while preserving the Workspace identity', async () => {
    await renderWorkspace(services(MANUAL_WORKSPACE))
    expect(container.querySelector('[data-products-route]')?.textContent).toBe('?workspace=workspace-1')
    expect(container.querySelector('[data-pricing-grid]')).toBeNull()
  })
})

async function renderWorkspace(services: Services) {
  await act(async () => {
    activeRoot.render(<MemoryRouter initialEntries={['/workspace/workspace-1']}><NotificationProvider><ServiceProvider services={services}><Routes><Route path="/workspace/:workspaceId" element={<UnifiedWorkspace />} /><Route path="/products" element={<ProductsRouteMarker />} /></Routes></ServiceProvider></NotificationProvider></MemoryRouter>)
    await Promise.resolve(); await new Promise(resolve => setTimeout(resolve, 0))
  })
}

function ProductsRouteMarker() {
  const location = useLocation()
  return <div data-products-route>{location.search}</div>
}

function services(workspaceResource: UnifiedWorkspaceResource): Services {
  const review: ReviewResource = { id: 'review-1', workspaceId: workspaceResource.id, snapshotId: workspaceResource.snapshot.id, draftRevisionId: 'revision-1', status: 'ready', checksum: 'review', summary: { total: 0, eligible: 0, blocked: 0, warnings: 0 }, items: [], staleReason: null }
  const legacyGrid: WorkspaceGridPage = { items: [], total: 0, page: 1, pageSize: 500, channels: [], draftVersion: 0, revisionId: null }
  const preferences: WorkspacePreferences = { visibleChannelIds: ['woocommerce:primary'], channelOrder: ['woocommerce:primary'], visibleFields: {}, displayNameSource: 'canonical', version: 1 }
  return {
    unifiedWorkspace: {
      createManual: vi.fn(), async getWorkspace() { return workspaceResource }, async getGrid() { return legacyGrid },
      async saveDraft() { return { id: 'revision-1', revisionNumber: 1, checksum: 'checksum', draftVersion: 1 } }, async createReview() { return review }, async saveSelection() { return { reviewId: 'review-1', selectedItemIds: [], selectionChecksum: 'checksum', selectionVersion: 1 } }, async applySelected() { throw new Error('not used') }, async getApply() { throw new Error('not used') }, async reconcileApply() { throw new Error('not used') }, async getPreferences() { return preferences },
      async savePreferences(value: WorkspacePreferences) { return value },
    },
    products: {}, health: {}, sources: {}, workspace: {}, settings: {}, activity: {}, commerce: {}, writePipeline: {}, orders: {},
  } as unknown as Services
}
