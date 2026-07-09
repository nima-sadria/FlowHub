import type { WorkspaceState, WorkspacePreview, PriceChange } from '../types'
import type { WorkspaceService } from './WorkspaceService'
import { apiFetch } from '../../api/client'
import { authFetch } from '../../api/authFetch'

interface RawChange {
  productId: string
  productName: string
  sku: string
  currentPrice: number
  proposedPrice: number
  difference?: number
  changePct: number
  currency: string
  warning?: string | null
  eligible_for_dry_run?: boolean
  validationStatus?: string
  source?: Record<string, unknown>
  validationWarnings?: string[]
}

interface RawPreview {
  id: string
  sourceId: string
  sourceName: string
  state: string
  totalChanges: number
  changes: RawChange[]
  rows?: WorkspacePreview['rows']
  summary?: WorkspacePreview['summary']
  startedAt: string
  duplicateWarnings?: string[]
}

function mapChange(r: RawChange): PriceChange {
  return {
    productId: r.productId,
    productName: r.productName,
    sku: r.sku,
    currentPrice: r.currentPrice,
    proposedPrice: r.proposedPrice,
    difference: r.difference ?? (r.proposedPrice - r.currentPrice),
    changePct: r.changePct,
    currency: r.currency,
    warning: r.warning ?? null,
    eligible_for_dry_run: r.eligible_for_dry_run,
    validationStatus: r.validationStatus,
    source: r.source as PriceChange['source'],
    validationWarnings: r.validationWarnings,
  }
}

export class ApiWorkspaceService implements WorkspaceService {
  async getState(): Promise<WorkspaceState> {
    const data = await apiFetch<{ state: WorkspaceState }>('/api/v2/workspace/state', authFetch)
    return data.state
  }

  async startPreview(_sourceId: string): Promise<WorkspacePreview> {
    const data = await apiFetch<RawPreview>(
      '/api/v2/workspace/preview',
      authFetch,
      { method: 'POST' },
    )
    return {
      id: data.id,
      sourceId: data.sourceId,
      sourceName: data.sourceName,
      state: data.state as WorkspaceState,
      totalChanges: data.totalChanges,
      changes: data.changes.map(mapChange),
      rows: data.rows ?? [],
      summary: data.summary ?? {
        total_rows: data.changes.length,
        valid_changes: data.changes.length,
        unchanged_rows: 0,
        warning_rows: 0,
        error_rows: 0,
        duplicate_rows: 0,
        missing_products: 0,
        large_changes: 0,
      },
      startedAt: new Date(data.startedAt),
      duplicateWarnings: data.duplicateWarnings,
    }
  }

  async cancelPreview(_previewId: string): Promise<void> {
    // Stateless preview: nothing to cancel on the backend.
  }
}
