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
}

interface RawPreview {
  id: string
  sourceId: string
  sourceName: string
  state: string
  totalChanges: number
  changes: RawChange[]
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
      startedAt: new Date(data.startedAt),
      duplicateWarnings: data.duplicateWarnings,
    }
  }

  async cancelPreview(_previewId: string): Promise<void> {
    // Stateless BU5 — nothing to cancel on the backend
  }
}
