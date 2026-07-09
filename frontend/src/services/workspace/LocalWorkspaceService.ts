import type { WorkspaceState, WorkspacePreview, PriceChange } from '../types'
import type { WorkspaceService } from './WorkspaceService'

const delay = (ms: number) => new Promise<void>(r => setTimeout(r, ms))
const SESSION_KEY = 'wp_local_workspace'

const LOCAL_BASE_CHANGES: PriceChange[] = [
  { productId: 'prod-001', productName: 'Wireless Headphones Pro', sku: 'WHP-001', currentPrice: 89.99, proposedPrice: 94.99, changePct: 5.56, currency: 'EUR' },
  { productId: 'prod-002', productName: 'USB-C Hub 7-Port', sku: 'UCH-002', currentPrice: 49.99, proposedPrice: 52.99, changePct: 6.00, currency: 'EUR' },
  { productId: 'prod-004', productName: '27" 4K Monitor', sku: 'MON-004', currentPrice: 299.00, proposedPrice: 319.00, changePct: 6.69, currency: 'EUR' },
  { productId: 'prod-009', productName: 'Cable Management Kit', sku: 'CMK-009', currentPrice: 14.99, proposedPrice: 15.99, changePct: 6.67, currency: 'EUR' },
]

interface PersistedPreview {
  id: string
  sourceId: string
  sourceName: string
  startedAt: string
}

function loadPreview(): WorkspacePreview | null {
  try {
    const raw = sessionStorage.getItem(SESSION_KEY)
    if (!raw) return null
    const p = JSON.parse(raw) as PersistedPreview
    return {
      ...p,
      state: 'preview_ready',
      totalChanges: LOCAL_BASE_CHANGES.length,
      changes: localChanges(p.id),
      rows: localRows(p.id),
      summary: localSummary(),
      startedAt: new Date(p.startedAt),
    }
  } catch {
    return null
  }
}

function savePreview(preview: WorkspacePreview): void {
  try {
    sessionStorage.setItem(SESSION_KEY, JSON.stringify({
      id: preview.id,
      sourceId: preview.sourceId,
      sourceName: preview.sourceName,
      startedAt: preview.startedAt.toISOString(),
    }))
  } catch { /* ignore */ }
}

function clearPreview(): void {
  try { sessionStorage.removeItem(SESSION_KEY) } catch { /* ignore */ }
}

export class LocalWorkspaceService implements WorkspaceService {
  private preview: WorkspacePreview | null = loadPreview()

  async getState(): Promise<WorkspaceState> {
    await delay(80)
    return this.preview ? 'preview_ready' : 'idle'
  }

  async startPreview(sourceId: string): Promise<WorkspacePreview> {
    await delay(2000)
    const preview: WorkspacePreview = {
      id: `preview-${Date.now()}`,
      sourceId,
      sourceName: 'Nextcloud Price List',
      state: 'preview_ready',
      totalChanges: LOCAL_BASE_CHANGES.length,
      changes: [],
      rows: [],
      summary: localSummary(),
      startedAt: new Date(),
    }
    preview.changes = localChanges(preview.id)
    preview.rows = localRows(preview.id)
    this.preview = preview
    savePreview(preview)
    return preview
  }

  async cancelPreview(_previewId: string): Promise<void> {
    await delay(100)
    this.preview = null
    clearPreview()
  }
}

function localChanges(previewId: string): PriceChange[] {
  return LOCAL_BASE_CHANGES.map((change, index) => ({
    ...change,
    difference: change.proposedPrice - change.currentPrice,
    status: 'valid_change',
    validationStatus: 'valid_change',
    eligible_for_dry_run: true,
    source: localSource(previewId, change, index),
    validationWarnings: [],
  }))
}

function localRows(previewId: string): WorkspacePreview['rows'] {
  return LOCAL_BASE_CHANGES.map((change, index) => ({
    id: `local:${change.productId}`,
    source: localSource(previewId, change, index),
    matchedProduct: {
      channelId: 'woocommerce:primary',
      productId: change.productId,
      productType: 'simple',
      sku: change.sku,
      name: change.productName,
      currentPrice: change.currentPrice,
      effectivePrice: change.currentPrice,
      categoryNames: [],
    },
    currentPrice: change.currentPrice,
    proposedPrice: change.proposedPrice,
    difference: change.proposedPrice - change.currentPrice,
    changePct: change.changePct,
    status: 'valid_change',
    errors: [],
    warnings: change.warning ? [change.warning] : [],
    eligible_for_dry_run: true,
  }))
}

function localSource(previewId: string, change: PriceChange, index: number) {
  return {
    previewId,
    sourceId: 'local',
    sourceType: 'local_demo',
    sourceSnapshotId: 0,
    sourceSnapshotVersion: 1,
    sourceFilePath: 'local-demo',
    worksheet: 'Demo',
    rowNumber: index + 3,
    productId: change.productId,
    sku: change.sku,
    productName: change.productName,
    rawPrice: String(change.proposedPrice),
  }
}

function localSummary(): WorkspacePreview['summary'] {
  return {
    total_rows: LOCAL_BASE_CHANGES.length,
    valid_changes: LOCAL_BASE_CHANGES.length,
    unchanged_rows: 0,
    warning_rows: 0,
    error_rows: 0,
    duplicate_rows: 0,
    missing_products: 0,
    large_changes: 0,
  }
}
