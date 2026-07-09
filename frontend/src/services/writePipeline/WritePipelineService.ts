import type { PriceChange, WorkspacePreviewSummary, WritePipelineBatch } from '../types'

export interface WritePipelineService {
  createDryRun(previewId: string, changes: PriceChange[], previewSummary?: WorkspacePreviewSummary): Promise<WritePipelineBatch>
  approve(batchId: string, reason?: string): Promise<WritePipelineBatch>
  applyToWooCommerce(batchId: string): Promise<WritePipelineBatch>
  getBatch(batchId: string): Promise<WritePipelineBatch>
}
