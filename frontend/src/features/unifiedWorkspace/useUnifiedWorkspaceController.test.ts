// @vitest-environment jsdom

import { act, createElement } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { UnifiedWorkspaceService } from '../../services/unifiedWorkspace/UnifiedWorkspaceService'
import type {
  ReviewResource,
  UnifiedWorkspaceResource,
  WorkspaceGridPage,
  WorkspacePreferences,
} from '../../services/unifiedWorkspace/types'
import { useUnifiedWorkspaceController } from './useUnifiedWorkspaceController'

type Controller = ReturnType<typeof useUnifiedWorkspaceController>

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(done => { resolve = done })
  return { promise, resolve }
}

const workspace: UnifiedWorkspaceResource = {
  id: 'workspace-1',
  name: 'Race test',
  entryPoint: 'manual',
  ownerUserId: 1,
  status: 'draft',
  version: 1,
  snapshot: { id: 'snapshot-1', checksum: 'a'.repeat(64), schemaVersion: '1', createdAt: '2026-01-01T00:00:00Z' },
  draft: { id: 'draft-1', version: 1, currentRevisionId: 'revision-1', status: 'draft' },
  createdAt: '2026-01-01T00:00:00Z',
}

const preferences: WorkspacePreferences = {
  visibleChannelIds: ['woocommerce:primary'],
  channelOrder: ['woocommerce:primary'],
  visibleFields: {},
  displayNameSource: 'canonical',
  version: 1,
}

function grid(page: number, name: string): WorkspaceGridPage {
  return {
    page,
    pageSize: 500,
    total: 1500,
    draftVersion: 1,
    revisionId: 'revision-1',
    channels: [],
    items: [{ rowId: `row-${page}`, canonicalName: name }],
  }
}

function serviceWith(overrides: Partial<UnifiedWorkspaceService>): UnifiedWorkspaceService {
  return {
    createManual: vi.fn(),
    getWorkspace: vi.fn().mockResolvedValue(workspace),
    getGrid: vi.fn().mockResolvedValue(grid(1, 'default')),
    saveDraft: vi.fn(),
    createReview: vi.fn(),
    saveSelection: vi.fn(),
    applySelected: vi.fn(),
    getApply: vi.fn(),
    reconcileApply: vi.fn(),
    getPreferences: vi.fn().mockResolvedValue(preferences),
    savePreferences: vi.fn(),
    ...overrides,
  }
}

let mountedRoot: Root | null = null

afterEach(async () => {
  if (mountedRoot) await act(async () => mountedRoot?.unmount())
  mountedRoot = null
})

async function mount(service: UnifiedWorkspaceService): Promise<() => Controller> {
  const host = document.createElement('div')
  document.body.append(host)
  let current: Controller | null = null
  function Harness() {
    current = useUnifiedWorkspaceController('workspace-1', service)
    return null
  }
  mountedRoot = createRoot(host)
  await act(async () => mountedRoot?.render(createElement(Harness)))
  return () => {
    if (current === null) throw new Error('Controller was not mounted.')
    return current
  }
}

describe('Unified Workspace request generations', () => {
  it('ignores older page, filter, and sort responses that resolve last', async () => {
    const requests = [deferred<WorkspaceGridPage>(), deferred<WorkspaceGridPage>(), deferred<WorkspaceGridPage>()]
    const getGrid = vi.fn()
      .mockImplementationOnce(() => requests[0].promise)
      .mockImplementationOnce(() => requests[1].promise)
      .mockImplementationOnce(() => requests[2].promise)
    const current = await mount(serviceWith({ getGrid }))

    await act(async () => current().setPage(2))
    await act(async () => current().updateGridQuery({ search: 'latest', sort: 'price:desc' }))

    await act(async () => requests[2].resolve(grid(1, 'latest-filter-sort')))
    expect(current().grid?.items[0].canonicalName).toBe('latest-filter-sort')
    await act(async () => requests[1].resolve(grid(2, 'stale-page')))
    await act(async () => requests[0].resolve(grid(1, 'stale-initial')))
    expect(current().grid?.items[0].canonicalName).toBe('latest-filter-sort')
  })

  it('ignores an older Review response that resolves after a newer Review', async () => {
    const first = deferred<ReviewResource>()
    const second = deferred<ReviewResource>()
    const createReview = vi.fn()
      .mockImplementationOnce(() => first.promise)
      .mockImplementationOnce(() => second.promise)
    const current = await mount(serviceWith({ createReview }))
    await act(async () => undefined)

    void current().createReview()
    void current().createReview()
    const review = (id: string): ReviewResource => ({
      id,
      workspaceId: workspace.id,
      snapshotId: workspace.snapshot.id,
      draftRevisionId: 'revision-1',
      status: 'ready',
      checksum: id.padEnd(64, '0'),
      summary: { total: 0, eligible: 0, blocked: 0, warnings: 0 },
      items: [],
      staleReason: null,
    })
    await act(async () => second.resolve(review('review-new')))
    expect(current().review?.id).toBe('review-new')
    await act(async () => first.resolve(review('review-old')))
    expect(current().review?.id).toBe('review-new')
  })
})
