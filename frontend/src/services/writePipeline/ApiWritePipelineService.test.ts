// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ApiWritePipelineService } from './ApiWritePipelineService'


afterEach(() => {
  vi.restoreAllMocks()
  localStorage.clear()
})


describe('ApiWritePipelineService', () => {
  it('submits only previewId and selectedRowIds for Dry Run', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({
      id: 'wb_1',
      channelId: 'woocommerce:primary',
      channelType: 'woocommerce',
      operationType: 'price_update',
      status: 'dry_run_ready',
      sourcePreviewId: 'wp_1',
      batchHash: 'hash',
      itemCount: 1,
      currency: 'EUR',
      safetySummary: {},
      resultSummary: {},
      createdBy: 'admin',
      createdAt: '2026-07-10T00:00:00Z',
      approvedAt: null,
      executedAt: null,
      items: [],
    }), { status: 201, headers: { 'Content-Type': 'application/json' } }))

    await new ApiWritePipelineService().createDryRun('wp_1', ['wp_1:Sheet1:3'])

    const request = fetchMock.mock.calls[0]
    expect(request[0]).toBe('/api/v2/write-pipeline/dry-run')
    expect(JSON.parse(String(request[1]?.body))).toEqual({
      previewId: 'wp_1',
      selectedRowIds: ['wp_1:Sheet1:3'],
    })
  })
})
