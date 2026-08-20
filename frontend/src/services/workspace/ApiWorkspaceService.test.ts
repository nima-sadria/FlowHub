// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiWorkspaceService } from './ApiWorkspaceService'

afterEach(() => {
  vi.restoreAllMocks()
  localStorage.clear()
})

describe('ApiWorkspaceService Source binding contract', () => {
  it('loads the canonical binding and active candidates', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({
      boundSource: null,
      candidates: [{ sourceId: 'source-active', sourceName: 'Current Nextcloud', status: 'active' }],
    }), { status: 200, headers: { 'Content-Type': 'application/json' } }))

    const result = await new ApiWorkspaceService().getSourceBinding()

    expect(fetchMock.mock.calls[0][0]).toBe('/api/v2/workspace/source-binding')
    expect(result.candidates[0].sourceId).toBe('source-active')
  })

  it('binds the exact selected Source through the canonical API', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({
      sourceId: 'source-active',
      sourceName: 'Current Nextcloud',
      status: 'active',
    }), { status: 200, headers: { 'Content-Type': 'application/json' } }))

    await new ApiWorkspaceService().bindSource('source-active')

    const request = fetchMock.mock.calls[0]
    expect(request[0]).toBe('/api/v2/workspace/source-binding')
    expect(request[1]?.method).toBe('PUT')
    expect(JSON.parse(String(request[1]?.body))).toEqual({ source_id: 'source-active' })
  })

  it('sends the bound Source ID in Preview and never omits it', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({
      id: 'preview-1',
      sourceId: 'source-active',
      sourceName: 'Current Nextcloud',
      state: 'preview_ready',
      totalChanges: 0,
      changes: [],
      rows: [],
      summary: {
        total_rows: 0,
        valid_changes: 0,
        unchanged_rows: 0,
        warning_rows: 0,
        error_rows: 0,
        duplicate_rows: 0,
        missing_products: 0,
        large_changes: 0,
      },
      startedAt: '2026-08-20T00:00:00Z',
    }), { status: 200, headers: { 'Content-Type': 'application/json' } }))

    await new ApiWorkspaceService().startPreview('source-active')

    const request = fetchMock.mock.calls[0]
    expect(request[0]).toBe('/api/v2/workspace/preview')
    expect(request[1]?.method).toBe('POST')
    expect(JSON.parse(String(request[1]?.body))).toEqual({ source_id: 'source-active' })
  })
})
