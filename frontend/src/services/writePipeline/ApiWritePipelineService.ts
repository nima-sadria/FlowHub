import type { PriceChange, WorkspacePreviewSummary, WritePipelineBatch } from '../types'
import type { WritePipelineService } from './WritePipelineService'
import { apiFetch } from '../../api/client'
import { authFetch } from '../../api/authFetch'

interface RawBatch extends Omit<WritePipelineBatch, 'createdAt' | 'approvedAt' | 'executedAt'> {
  createdAt: string
  approvedAt?: string | null
  executedAt?: string | null
}

function mapBatch(raw: RawBatch): WritePipelineBatch {
  return {
    ...raw,
    createdAt: new Date(raw.createdAt),
    approvedAt: raw.approvedAt ? new Date(raw.approvedAt) : null,
    executedAt: raw.executedAt ? new Date(raw.executedAt) : null,
  }
}
export class ApiWritePipelineService implements WritePipelineService {
  async createDryRun(previewId: string, changes: PriceChange[], previewSummary?: WorkspacePreviewSummary): Promise<WritePipelineBatch> {
    const raw = await apiFetch<RawBatch>(
      '/api/v2/write-pipeline/dry-run',
      authFetch,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          previewId,
          channelId: 'woocommerce:primary',
          operationType: 'price_update',
          previewSummary: previewSummary ?? {},
          changes,
        }),
      },
    )
    return mapBatch(raw)
  }

  async approve(batchId: string, reason?: string): Promise<WritePipelineBatch> {
    const raw = await apiFetch<RawBatch>(
      `/api/v2/write-pipeline/batches/${batchId}/approve`,
      authFetch,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason: reason ?? null }),
      },
    )
    return mapBatch(raw)
  }

  async applyToWooCommerce(batchId: string): Promise<WritePipelineBatch> {
    const raw = await apiFetch<RawBatch>(
      `/api/v2/write-pipeline/batches/${batchId}/execute`,
      authFetch,
      { method: 'POST' },
    )
    return mapBatch(raw)
  }

  async getBatch(batchId: string): Promise<WritePipelineBatch> {
    const raw = await apiFetch<RawBatch>(
      `/api/v2/write-pipeline/batches/${batchId}`,
      authFetch,
    )
    return mapBatch(raw)
  }
}
