import type { WritePipelineBatch } from '../types'

export interface WritePipelineService {
  createDryRun(previewId: string, selectedRowIds: string[]): Promise<WritePipelineBatch>
  approve(batchId: string, reason?: string): Promise<WritePipelineBatch>
  applyToWooCommerce(batchId: string): Promise<WritePipelineBatch>
  getBatch(batchId: string): Promise<WritePipelineBatch>
}
