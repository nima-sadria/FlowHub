import type { ChangeBadgeClassification } from '../../features/sourceWorkspace/types'

export type WorkspaceCellStatus =
  | 'unchanged' | 'edited' | 'draft_saved' | 'warning' | 'error' | 'ready'
  | 'applying' | 'applied' | 'failed' | 'read_only' | 'unavailable' | 'stale_review'
  | 'reconciliation_required'

export interface WorkspaceChannelDefinition {
  channelId: string
  displayName?: string | null
  displayNameCustom?: boolean
  instanceLabel?: string | null
  readPrice: boolean
  writePrice: boolean
  readStock: boolean
  writeStock: boolean
  readStatus: boolean
  writeStatus: boolean
  supportsMultipleListings: boolean
  maximumBatchSize: number
  rateLimitPerMinute: number | null
  healthState: string
  primaryIdentifierType: string
  supportedStatuses: string[]
  currency: string
  unit: string
  writeAvailable: boolean
  version: string
}

export interface WorkspaceCellValue {
  current: string | null
  target: string | null
  status: WorkspaceCellStatus
  readOnly: boolean
  currency: string | null
  unit: string | null
}

export interface WorkspaceGridRow {
  rowId: string
  unresolved?: boolean
  canonicalProductId?: string
  canonicalName?: string
  displayName?: string
  displayNameSource?: string
  productType?: 'simple' | 'variable' | 'variation'
  parentProductId?: string | null
  listingId?: string
  listingLabel?: string
  channelId?: string
  externalPrimaryId?: string
  externalIdType?: string
  sku?: string | null
  mappingState?: 'resolved' | 'unresolved' | 'conflict'
  mappingVersion?: number
  cacheVersion?: number | null
  cacheFreshness?: string
  fields?: Record<'price' | 'stock' | 'status', WorkspaceCellValue>
}

export interface WorkspaceGridPage {
  items: WorkspaceGridRow[]
  total: number
  page: number
  pageSize: number
  channels: WorkspaceChannelDefinition[]
  draftVersion: number
  revisionId: string | null
}

export interface UnifiedWorkspaceResource {
  id: string
  name: string
  entryPoint: 'manual' | 'source'
  sourceType?: string | null
  ownerUserId: number
  status: string
  version: number
  snapshot: { id: string; checksum: string; schemaVersion: string; createdAt: string }
  draft: { id: string; version: number; currentRevisionId: string | null; status: string }
  createdAt: string
}

export interface DraftChangeInput {
  canonical_product_id: string
  listing_id: string
  channel_id: string
  field: 'price' | 'stock' | 'status'
  target_value: string
  currency?: string | null
  unit?: string | null
}

export interface DraftRevisionResource {
  id: string
  revisionNumber: number
  checksum: string
  draftVersion: number
  noOp?: boolean
}

export interface ReviewItemResource {
  id: string
  canonicalProductId: string
  listingId: string
  externalPrimaryId?: string | null
  channelId: string
  field: 'price' | 'stock' | 'status'
  current: string | null
  target: string
  changeClassification?: ChangeBadgeClassification | null
  validationState: string
  warnings: string[]
  errors: string[]
  eligible: boolean
  selected: boolean
}

export interface ReviewResource {
  id: string
  workspaceId: string
  snapshotId: string
  draftRevisionId: string
  status: 'ready' | 'blocked' | 'stale'
  checksum: string
  summary: { total: number; eligible: number; blocked: number; warnings: number }
  items: ReviewItemResource[]
  staleReason: string | null
}

export type ApplyJobStatus = 'pending' | 'running' | 'reconciliation_required' | 'partially_applied' | 'applied' | 'failed' | 'cancelled' | 'blocked' | 'stale'
export type ApplyItemStatus = 'pending' | 'dispatched' | 'provider_accepted' | 'recovering' | 'reconciliation_required' | 'applied' | 'failed' | 'cancelled'

export interface ApplyResource {
  id: string
  workspaceId: string
  status: ApplyJobStatus
  correlationId: string
  items: Array<{
    id: string
    listingId: string
    channelId: string
    field: string
    status: ApplyItemStatus
    errorMessage: string | null
    errorCategory?: string | null
    retryEligible?: boolean
    attemptNumber?: number
    cacheSyncStatus: string | null
  }>
}

export interface ManifestOperationResource {
  id: string
  reviewItemId: string
  canonicalProductId: string
  listingId: string
  channelId: string
  field: 'price' | 'stock' | 'status'
  current: string | null
  target: string
  currency: string | null
  unit: string | null
}

export interface ReviewSelectionResource {
  reviewId: string
  selectedItemIds: string[]
  selectionChecksum: string
  selectionVersion: number
  dryRunStatus?: 'idle'
  /** Compatibility-only: cache-era callers must not treat these as applyable. */
  manifestId?: string
  manifestChecksum?: string
  operations?: ManifestOperationResource[]
  affectedChannelIds?: string[]
}

export interface DryRunResource {
  id: string
  status: 'passed' | 'blocked' | 'error' | 'invalidated'
  reviewedCount: number
  writeCount: number
  blockerCount: number
  evidenceChecksum: string
  scopes: Array<{ reviewItemId: string; disposition: 'write' | 'no_op' | 'blocked'; reason: string | null; expected?: Record<string, unknown> | null; observed?: Record<string, unknown> | null }>
  manifestId?: string
  manifestChecksum?: string
  operations?: ManifestOperationResource[]
  affectedChannelIds?: string[]
}

export interface WorkspaceGridQuery {
  search?: string
  sort?: string
  productType?: string
  mappingState?: string
  channelId?: string
  sku?: string
  channelStatus?: string
  minPrice?: number
  maxPrice?: number
  stockQuantity?: number
  category?: string
  brand?: string
  listingId?: string
}

export interface WorkspacePreferences {
  visibleChannelIds: string[]
  channelOrder: string[]
  visibleFields: Record<string, boolean>
  displayNameSource: string
  version: number
}
