// -- Health --------------------------------------------------------------------

export interface SystemHealth {
  status: 'ok' | 'degraded' | 'error'
  version: string
  environment: string
  checkedAt: Date
}

// -- Products ------------------------------------------------------------------

export type ProductSyncStatus = 'synced' | 'pending' | 'stale' | 'error'

export interface Product {
  id: string
  name: string
  sku: string
  currentPrice: number
  sourcePrice: number | null
  currency: string
  status: ProductSyncStatus
  lastSynced: Date | null
  categoryNames: string[]
  imageUrl?: string | null
  productType?: 'simple' | 'variable'
}

export interface ProductFilter {
  search: string
  status: ProductSyncStatus | 'all'
  page: number
  pageSize: number
  categoryId?: number | null
  productType?: 'simple' | 'variable' | null
  channelId?: string | null
}

export interface PaginatedResult<T> {
  items: T[]
  total: number
  page: number
  pageSize: number
  configured?: boolean
}

// -- Sources -------------------------------------------------------------------

export type SourceType = 'nextcloud_excel'
export type SourceStatus = 'active' | 'error' | 'unconfigured'

export interface Source {
  id: string
  name: string
  type: SourceType
  displayUrl: string
  status: SourceStatus
  lastSynced: Date | null
  productCount: number
}

export interface SourceConfig {
  name: string
  type: SourceType
  url: string
  username: string
  password: string
  filePath: string
}

export interface ConnectionTestResult {
  success: boolean
  message: string
  discoveredProductCount?: number
}

// -- Workspace -----------------------------------------------------------------

export type WorkspaceState = 'idle' | 'previewing' | 'preview_ready' | 'error'

export interface PriceChange {
  productId: string
  productName: string
  sku: string
  currentPrice: number
  proposedPrice: number
  difference?: number
  changePct: number
  currency: string
  warning?: string | null
  status?: string
  eligible_for_dry_run?: boolean
  validationStatus?: string
  source?: WorkspaceSourceRowInfo
  validationWarnings?: string[]
}

export interface WorkspaceSourceRowInfo {
  previewId: string
  sourceId: string
  sourceType: string
  sourceSnapshotId: number
  sourceSnapshotVersion: number
  sourceFilePath: string
  worksheet: string
  rowNumber: number
  productId?: string | null
  sku?: string
  productName?: string
  rawPrice?: string
}

export interface WorkspaceMatchedProductInfo {
  channelId: string
  productId: string
  externalId?: number | null
  productType: string
  parentId?: string | null
  sku: string
  name: string
  currentPrice: number
  regularPrice?: number | null
  salePrice?: number | null
  effectivePrice: number
  imageUrl?: string | null
  categoryNames: string[]
  freshness?: string | null
}

export interface WorkspacePreviewRow {
  id: string
  source: WorkspaceSourceRowInfo
  matchedProduct: WorkspaceMatchedProductInfo | null
  currentPrice: number | null
  proposedPrice: number | null
  difference: number | null
  changePct: number | null
  status: 'valid_change' | 'warning' | 'unchanged' | 'error'
  errors: string[]
  warnings: string[]
  eligible_for_dry_run: boolean
}

export interface WorkspacePreviewSummary {
  total_rows: number
  valid_changes: number
  unchanged_rows: number
  warning_rows: number
  error_rows: number
  duplicate_rows: number
  missing_products: number
  large_changes: number
}

export interface WorkspacePreview {
  id: string
  sourceId: string
  sourceName: string
  state: WorkspaceState
  totalChanges: number
  changes: PriceChange[]
  rows: WorkspacePreviewRow[]
  summary: WorkspacePreviewSummary
  startedAt: Date
  duplicateWarnings?: string[]
}

// -- Write Pipeline ------------------------------------------------------------

export type WritePipelineStatus =
  | 'dry_run_ready'
  | 'approved'
  | 'executing'
  | 'applied'
  | 'partially_failed'
  | 'failed'

export interface WritePipelineItem {
  id: number | null
  productId: string
  productName: string
  sku: string
  currentPrice: number
  proposedPrice: number
  difference: number
  changePct: number
  currency: string
  status: string
  errorCode?: string | null
  errorMessage?: string | null
  source?: WorkspaceSourceRowInfo | null
  validationWarnings?: string[]
  providerResult?: Record<string, unknown>
  verification?: {
    verified: boolean
    observed_price?: number | null
    expected_price?: number | null
    verification_error?: string | null
  } | null
}

export interface WritePipelineResultSummary {
  total_attempted: number
  success_count: number
  failure_count: number
  skipped_count: number
  blocked_count: number
  warning_count: number
  verified_count: number
  unverified_count: number
  estimated_affected_products: number
}

export interface WritePipelineBatch {
  id: string
  channelId: string
  channelType: string
  operationType: string
  status: WritePipelineStatus
  sourcePreviewId?: string | null
  batchHash: string
  itemCount: number
  currency: string
  safetySummary: Record<string, unknown>
  resultSummary?: WritePipelineResultSummary
  createdBy: string
  approvedBy?: string | null
  approvalReason?: string | null
  createdAt: Date
  approvedAt?: Date | null
  executedAt?: Date | null
  items: WritePipelineItem[]
}

// -- Settings ------------------------------------------------------------------

export interface AppSettings {
  woocommerceUrl: string
  nextcloudUrl: string
  syncIntervalMinutes: number
  timezone: string
  currency: string
  environment: string
  wcConfigured?: boolean
  ncConfigured?: boolean
}

export interface RateLimitSettings {
  read_requests_per_minute: number
  write_requests_per_minute: number
  read_delay_ms: number
  write_delay_ms: number
  inherits_to_all_connectors: boolean
  per_connector_override_available: boolean
  scheduler_started: boolean
  automatic_sync: boolean
  runtime_write_blocked: boolean
}

// -- Commerce Hub --------------------------------------------------------------

export interface CommerceHealth {
  status: string
  message: string
  latency_ms: number | null
  error_code: string | null
}

export interface CommerceSource {
  id: string
  provider: string
  name: string
  type: 'Source'
  status: string
  implemented: boolean
  placeholder: boolean
  credential_status: string
  last_health_check: string | null
  data_role: string
  action_label: string
  action_href: string
  health: CommerceHealth
  read_only: boolean
  runtime_write_blocked: boolean
  settings_available: boolean
}

export interface CommerceChannel {
  id: string
  provider: string
  name: string
  type: 'Channel'
  status: string
  implemented: boolean
  placeholder: boolean
  read_only: boolean
  write_blocked: boolean
  runtime_write_blocked: boolean
  credential_status: string
  last_health_check: string | null
  health: CommerceHealth
  capabilities: Record<string, boolean>
  capabilities_summary: string[]
  settings_available: boolean
}

export interface CommerceRelationshipMap {
  nodes: string[]
  example: string[]
  runtime_write_blocked: boolean
  read_only: boolean
}

export interface CommerceTypeField {
  key: string
  label: string
  required: boolean
  secret: boolean
  default?: string | number | boolean | null
}

export interface CommerceTypeOption {
  id: string
  provider: string
  name: string
  type: 'Source' | 'Channel'
  implemented: boolean
  placeholder: boolean
  read_only: boolean
  write_blocked?: boolean
  runtime_write_blocked: boolean
  settings_schema: CommerceTypeField[]
}

// -- Activity ------------------------------------------------------------------

export type ActivityEventKind = 'user_action' | 'system_log'
export type ActivityLevel = 'info' | 'success' | 'warning' | 'error'

export interface ActivityEvent {
  id: string
  timestamp: Date
  kind: ActivityEventKind
  level: ActivityLevel
  actor: string
  action: string
  detail: string | null
}
