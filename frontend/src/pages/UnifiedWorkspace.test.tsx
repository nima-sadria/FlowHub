// @vitest-environment jsdom
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { changeLocale } from '../i18n'
import { NotificationProvider } from '../notifications/NotificationProvider'
import { ServiceProvider, type Services } from '../services/ServiceContext'
import type { ReviewResource, UnifiedWorkspaceResource, WorkspaceGridPage, WorkspacePreferences } from '../services/unifiedWorkspace/types'
import { sourceWorkspaceApi } from '../features/sourceWorkspace/api'
import type { GroupedWorkspacePage } from '../features/sourceWorkspace/types'
import UnifiedWorkspace from './UnifiedWorkspace'

;(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true

const WORKSPACE: UnifiedWorkspaceResource = {
  id: 'workspace-1', name: 'Pricing workspace', entryPoint: 'manual', ownerUserId: 1,
  status: 'active', version: 1, snapshot: { id: 'snapshot-1', checksum: 'hash', schemaVersion: '1', createdAt: new Date().toISOString() },
  draft: { id: 'draft-1', version: 0, currentRevisionId: null, status: 'draft' }, createdAt: new Date().toISOString(),
}

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

  it('renders a grouped product with inline channel fields and batch Review/Dry Run action', async () => {
    await renderWorkspace(services())
    expect(container.textContent).toContain('Cable')
    expect(container.textContent).toContain('Review & Dry Run')
    expect(container.querySelector('[data-listing-id="listing-1"]')).not.toBeNull()
  })

  it.each([['en', 'ltr'], ['fa', 'rtl']] as const)('keeps grouped workspace direction in %s', async (locale, direction) => {
    await changeLocale(locale); await renderWorkspace(services())
    expect(document.documentElement.dir).toBe(direction)
    expect(container.textContent).toContain('WooCommerce')
  })
})

async function renderWorkspace(services: Services) {
  await act(async () => {
    activeRoot.render(<MemoryRouter initialEntries={['/workspace/workspace-1']}><NotificationProvider><ServiceProvider services={services}><Routes><Route path="/workspace/:workspaceId" element={<UnifiedWorkspace />} /></Routes></ServiceProvider></NotificationProvider></MemoryRouter>)
    await Promise.resolve(); await new Promise(resolve => setTimeout(resolve, 0))
  })
}

function services(): Services {
  const review: ReviewResource = { id: 'review-1', workspaceId: WORKSPACE.id, snapshotId: WORKSPACE.snapshot.id, draftRevisionId: 'revision-1', status: 'ready', checksum: 'review', summary: { total: 0, eligible: 0, blocked: 0, warnings: 0 }, items: [], staleReason: null }
  const legacyGrid: WorkspaceGridPage = { items: [], total: 0, page: 1, pageSize: 500, channels: [], draftVersion: 0, revisionId: null }
  const preferences: WorkspacePreferences = { visibleChannelIds: ['woocommerce:primary'], channelOrder: ['woocommerce:primary'], visibleFields: {}, displayNameSource: 'canonical', version: 1 }
  return {
    unifiedWorkspace: {
      createManual: vi.fn(), async getWorkspace() { return WORKSPACE }, async getGrid() { return legacyGrid },
      async saveDraft() { return { id: 'revision-1', revisionNumber: 1, checksum: 'checksum', draftVersion: 1 } }, async createReview() { return review }, async saveSelection() { return { reviewId: 'review-1', selectedItemIds: [], selectionChecksum: 'checksum', selectionVersion: 1 } }, async applySelected() { throw new Error('not used') }, async getApply() { throw new Error('not used') }, async reconcileApply() { throw new Error('not used') }, async getPreferences() { return preferences },
      async savePreferences(value: WorkspacePreferences) { return value },
    },
    products: {}, health: {}, sources: {}, workspace: {}, settings: {}, activity: {}, commerce: {}, writePipeline: {}, orders: {},
  } as unknown as Services
}
