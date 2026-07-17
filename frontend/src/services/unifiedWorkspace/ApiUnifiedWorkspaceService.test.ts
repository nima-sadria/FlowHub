// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiUnifiedWorkspaceService } from './ApiUnifiedWorkspaceService'
import type { DraftChangeInput } from './types'

const CHANGE: DraftChangeInput = {
  canonical_product_id: 'product-1',
  listing_id: 'listing-1',
  channel_id: 'woocommerce:primary',
  field: 'price',
  target_value: '120',
  currency: 'IRR',
  unit: 'IRR',
}

afterEach(() => {
  vi.restoreAllMocks()
  localStorage.clear()
})

describe('ApiUnifiedWorkspaceService Draft save mode', () => {
  it.each([
    [undefined, 'merge'],
    ['replace' as const, 'replace'],
  ])('sends %s as %s', async (requestedMode, expectedMode) => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({
      id: 'revision-1',
      revisionNumber: 1,
      checksum: 'checksum',
      draftVersion: 2,
    }), { status: 201, headers: { 'Content-Type': 'application/json' } }))

    await new ApiUnifiedWorkspaceService().saveDraft('workspace-1', 1, [CHANGE], requestedMode)

    const request = fetchMock.mock.calls[0]
    expect(request[0]).toBe('/api/v2/unified-workspaces/workspace-1/draft/revisions')
    expect(JSON.parse(String(request[1]?.body))).toEqual({
      expected_version: 1,
      changes: [CHANGE],
      mode: expectedMode,
      metadata: { client: 'handsontable', action: 'save_draft' },
    })
  })
})
