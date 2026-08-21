// -- Health --------------------------------------------------------------------

export interface SystemHealth {
  status: 'ok' | 'degraded' | 'error'
  version: string
  environment: string
  checkedAt: Date
}

export type DiagnosticState =
  | 'HEALTHY'
  | 'INFO'
  | 'COMING_SOON'
  | 'NOT_CHECKED'
  | 'NOT_APPLICABLE'
  | 'DISABLED'
  | 'WARNING'
  | 'ERROR'

export type ChannelHealthLevel =
  | 'Operational'
  | 'Information'
  | 'Coming Soon'
  | 'Not checked'
  | 'Not applicable'
  | 'Warning'
  | 'Error'
  | 'Unable to check'
  | 'Disabled'

export interface DiagnosticEvidence {
  state?: DiagnosticState
  reason_code?: string | null
  checked_at?: string | null
  evidence_source?: string | null
  is_actionable?: boolean
  recommended_action?: string | null
  freshness_threshold_hours?: number | null
}

export interface ChannelHealthDimension extends DiagnosticEvidence {
  status: ChannelHealthLevel
  message: string
}

export interface ChannelHealthItem extends DiagnosticEvidence {
  channelId: string
  channelType: string
  displayName?: string | null
  displayNameCustom?: boolean
  enabled: boolean
  accessMode: string
  status: ChannelHealthLevel
  summary: string
  lastChecked: string | null
  lastSuccessfulVerification?: string | null
  latency: number | null
  lastSuccessfulOperation: string | null
  lastSuccessfulSyncOrRead?: string | null
  lastErrorCategory: string | null
  capabilityState: Record<string, boolean>
  connectionTestSupported: boolean
  credentialsConfigured: boolean
  nextRecommendedAction: string
  dimensions: Record<string, ChannelHealthDimension>
  lastProductRead: string | null
  lastProductWrite: string | null
  lastOrderSync: string | null
  polling: { cursor: string | null; lastRunAt: string | null }
  webhooks: {
    supported: boolean
    received: number
    queued: number
    processed: number
    deadLetter: number
    lastReceivedAt: string | null
    lastProcessedAt: string | null
  }
  canonical?: CanonicalDiagnosticResource | null
}

export type ConnectivityState = 'UNKNOWN' | 'HEALTHY' | 'DEGRADED' | 'UNHEALTHY' | 'NOT_APPLICABLE'
export type ReadinessState = 'READY' | 'NEEDS_ATTENTION' | 'BLOCKED' | 'DISABLED' | 'ARCHIVED' | 'COMING_SOON' | 'NOT_APPLICABLE'
export type FreshnessState = 'FRESH' | 'STALE' | 'NEVER_RUN' | 'NOT_SCHEDULED' | 'NOT_ENABLED' | 'NOT_APPLICABLE'
/**
 * Distinct axis from FreshnessState above: "has any read completed
 * recently" (channel-level, coarse) vs. "do we currently trust this
 * channel's cached prices" (per-row evidence, worst-value-wins rollup).
 * See ADR_CHANNEL_READ_ARCHITECTURE.md. Never derived from FreshnessState.
 */
export type ObservationConfidenceValue = 'CONFIRMED' | 'LIKELY_FRESH' | 'STALE' | 'UNKNOWN' | 'RECOVERY_REQUIRED'
export type CanonicalOverallState = 'ERROR' | 'BLOCKED' | 'NEEDS_ATTENTION' | 'HEALTHY' | 'ARCHIVED' | 'COMING_SOON' | 'DISABLED'
export type ScheduleMode =
  | 'SCHEDULED'
  | 'EVENT_DRIVEN'
  | 'EVENT_DRIVEN_WITH_RECONCILIATION'
  | 'MANUAL'
  | 'NOT_SCHEDULED'
  | 'NOT_ENABLED'
  | 'NOT_APPLICABLE'
export type ReconciliationMode = 'SCHEDULED' | 'MANUAL' | 'DISABLED'
export type RunnerState = 'RUNNING' | 'IDLE' | 'PENDING' | 'DEGRADED' | 'FAILED' | 'UNKNOWN'

export interface CanonicalCapabilityEvidence {
  support: string
  freshness: FreshnessState
  schedule: {
    mode: string
    enabled: boolean
    intervalSeconds: number | null
    jitterSeconds: number
    policySource: string
  }
  lastAttemptAt: string | null
  lastSuccessAt: string | null
  lastOutcome: string
  nextExpectedAt: string | null
  required: boolean
  policy: { freshnessTtlSeconds: number | null; source: string; requiredForReadiness?: boolean }
  evidenceKey: string
  cachedItemCount?: number
  lastReceivedAt?: string | null
  lastProcessedAt?: string | null
  deadLetterCount?: number
  queuedCount?: number
  acceptedCount?: number
  /**
   * Reconciliation is a separate axis from event delivery: an event-driven
   * channel may still have a scheduled safety-net poll, a manual refresh, or
   * nothing at all. Present on the product-synchronization capability.
   */
  reconciliation?: { mode: ReconciliationMode; nextReconciliationAt: string | null }
}

export interface CanonicalDiagnosticResource {
  id: string
  connectorId?: string | null
  kind: 'CHANNEL' | 'SOURCE'
  provider: string
  displayName: string
  lifecycle: string
  enabled: boolean
  configured: boolean
  denominatorEligible: boolean
  connectivity: { state: ConnectivityState; freshness: FreshnessState; lastVerifiedAt: string | null; lastCheckedAt: string | null }
  readiness: { state: ReadinessState; reasonCode: string }
  freshness: { state: FreshnessState }
  observationConfidence: { value: ObservationConfidenceValue; reasonCode: string; recoveryRequiredCount: number; computedAt: string | null }
  capabilities: Record<string, CanonicalCapabilityEvidence>
  overallState: CanonicalOverallState
  reasonCode: string
  recommendedAction: { code: string; scheduledAt: string | null; actionable: boolean }
  latestRelevantAt: string | null
  advancedEvidence: Array<{ key: string; label: string; value: unknown; recordedAt: string | null }>
}

export interface CanonicalDiagnosticsStateModel {
  schemaVersion: string
  generatedAt: string
  overallState: CanonicalOverallState
  summary: {
    overallState: CanonicalOverallState
    channels: { ready: number; operational: number; needsAttention: number; blocked: number; disabled: number; comingSoon: number }
    sources: { ready: number; active: number; needsAttention: number; blocked: number; disabled: number; archived: number }
  }
  resources: CanonicalDiagnosticResource[]
  backgroundJobs: Array<{ id: string; displayName: string; state: RunnerState | string; health: string; required: boolean; lastHeartbeatAt: string | null; heartbeatTtlSeconds: number; runnerId: string | null; lastSuccessfulJobAt: string | null; queueDepth: number; staleQueueDepth?: number; lastFailureAt: string | null; lastFailureCode: string | null; advancedEvidence?: Array<{ key: string; label: string; value: unknown; recordedAt: string | null }> }>
  recentChecks: Array<{ id: string; kind: string; displayName: string; provider: string; lifecycle: string; connectivity: string; readiness: string; freshness: string; state: CanonicalOverallState; reasonCode: string; recordedAt: string | null }>
  consumerStates: Record<string, CanonicalOverallState>
  externalCallPerformed: false
}

export interface ChannelHealthResponse {
  checkedAt: string
  summary: {
    overall: ChannelHealthLevel
    overall_state?: DiagnosticState
    /** Compatibility alias used by early v1.3 fixtures. */
    state?: DiagnosticState
    counts: Partial<Record<ChannelHealthLevel, number>>
    state_counts?: Partial<Record<DiagnosticState, number>>
  }
  items: ChannelHealthItem[]
  stateModel?: CanonicalDiagnosticsStateModel
  external_call_performed: boolean
}

// -- Products ------------------------------------------------------------------

export type ProductSyncStatus = 'synced' | 'pending' | 'stale' | 'error'

export interface Product {
  id: string
  connectorId?: string
  name: string
  sku: string
  currentPrice: number
  sourcePrice: number | null
  currency: string
  status: ProductSyncStatus
  lastSynced: Date | null
  categoryNames: string[]
  imageUrl?: string | null
  productType?: 'simple' | 'variable' | 'variation'
}

export interface ProductFilter {
  search: string
  status: ProductSyncStatus | 'all'
  page: number
  pageSize: number
  categoryId?: number | null
  productType?: 'simple' | 'variable' | 'variation' | null
  channelId?: string | null
}

export interface PaginatedResult<T> {
  items: T[]
  total: number
  page: number
  pageSize: number
  configured?: boolean
}

export type ChannelPriceValidationState = 'valid' | 'error' | 'read_only' | 'disconnected'
export type ChannelPriceOperationStatus = 'dry_run_ready' | 'approved' | 'applied' | 'partially_failed' | 'failed'

export interface ProductChannelPriceState {
  channelId: string
  channelName: string
  connectorType: string
  channelProductId: string
  sku: string
  connectionState: string
  healthStatus: string
  canRead: boolean
  canWrite: boolean
  readOnly: boolean
  writeCapability: string
  currentValue: number | null
  proposedValue: number | null
  currency: string
  unit: string
  normalizedValue: number | null
  normalizedCurrency: string
  normalizedUnit: string
  freshness: string
  lastSyncedAt: string | null
  outboundValue?: number | null
  outboundUnit?: string
  validationState: ChannelPriceValidationState
  validationMessage: string | null
  pendingChange: boolean
  staleToken: string
}

export interface ProductChannelPriceStateSet {
  product: {
    id: string
    name: string
    sku: string
    productType: string
    imageUrl?: string | null
  }
  version: string
  canonical: {
    label: string
    value: number | null
    currency: string
    unit: string
    freshness: string
    lastSyncedAt: string | null
    staleToken: string
  }
  channels: ProductChannelPriceState[]
  dryRunRequired: boolean
  applyRequiresApproval: boolean
  status?: string
}

export interface ProductChannelPriceChange {
  channelId: string
  proposedValue: number
  unit: string
  staleToken: string
  specialPrice?: number | null
}

export interface ProductChannelPriceRequest {
  version?: string
  changes: ProductChannelPriceChange[]
}

export interface ProductChannelPriceOperationItem {
  id: number
  channelId: string
  connectorType: string
  channelProductId: string
  sku: string
  currentValue: number
  proposedValue: number
  currency: string
  unit: string
  outboundValue: number
  outboundUnit: string
  staleToken: string
  status: string
  validationState: string
  errorMessage: string | null
  result: Record<string, unknown>
}

export interface ProductChannelPriceOperation {
  id: string
  productId: string
  sku: string
  productName: string
  status: ChannelPriceOperationStatus
  version: string
  createdBy: string
  approvedBy: string | null
  approvalReason: string | null
  createdAt: string | null
  approvedAt: string | null
  appliedAt: string | null
  summary: {
    total: number
    pending: number
    success: number
    failed: number
    external_write_performed: boolean
  }
  items: ProductChannelPriceOperationItem[]
  externalWritePerformed: boolean
  applyRequiresApproval: boolean
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

// -- Write Pipeline ------------------------------------------------------------

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
  sourceDisplayName?: string
  sourceProductKey?: string | null
  sourceRowNumber?: number | null
  sourceLocation?: string | null
  sku?: string
  productName?: string
  rawPrice?: string
  rawStock?: string
  sourceStock?: number | null
  rawValues?: Record<string, string>
}

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
  itemType?: string
  parentProductId?: string | null
  parentProductName?: string | null
  variationId?: string | null
  variationAttributes?: Array<Record<string, string>>
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

// -- Orders --------------------------------------------------------------------

export interface ChannelOrderListItem {
  internalId: number
  channelId: string
  connectorType: string
  providerOrderId: string
  orderNumber: string | null
  providerStatus: string
  normalizedStatus: string
  createdAtProvider: string | null
  updatedAtProvider: string | null
  currency: string | null
  finalAmount: number | null
  itemCount: number
  synchronizationState: string
  eventSource: string
  errorState: string | null
  lastSeenAt: string | null
  customerDisplay: string | null
  paymentStatus: string
  fulfillmentStatus: string
}

export interface ChannelOrderItem {
  providerItemId: string
  externalProductId: string | null
  sku: string | null
  productNumber: string | null
  parentProductNumber: string | null
  name: string
  quantity: number
  canceledQuantity: number
  deliverableQuantity: number | null
  originalPrice: number | null
  finalPrice: number | null
  itemStatus: string | null
  cancellationReason: string | null
}

export interface ChannelShipment {
  shipmentNumber: string
  statusCode: string | null
  statusTitle: string | null
  deliveryMethod: string | null
  pickupOrSendWindow: string | null
}

export interface ChannelInvoice {
  invoiceNumber: string
  amount: number | null
  currency: string | null
}

export interface ChannelOrderTimelineEvent {
  eventName: string
  message: string
  createdAt: string | null
  metadata: Record<string, unknown>
}

export interface ChannelOrderDetail extends ChannelOrderListItem {
  items: ChannelOrderItem[]
  shipments: ChannelShipment[]
  invoices: ChannelInvoice[]
  timeline: ChannelOrderTimelineEvent[]
}

// -- Settings ------------------------------------------------------------------

export interface AppSettings {
  woocommerceUrl: string
  nextcloudUrl: string
  syncIntervalMinutes: number
  timezone: string
  currency: string
  currencyUnit?: string
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

// -- Exchange rates -----------------------------------------------------------

export type ExchangeRateStatus = 'fresh' | 'stale' | 'unavailable' | 'disabled'

export interface ExchangeRateDefinition {
  provider: string
  external_symbol: string
  canonical_code: string
  display_name: string
  display_name_fa: string
  classification: string
  side: string | null
  unit: string
}

export interface ExchangeRateSnapshotView extends ExchangeRateDefinition {
  position: number
  value: string | null
  change: string | null
  provider_timestamp: string | null
  fetched_at: string | null
  status: ExchangeRateStatus
  snapshot_id: string | null
}

export interface ExchangeRateAdminConfig {
  provider_id: string
  provider_type: string
  display_name: string
  enabled: boolean
  base_url: string
  request_timeout: number
  refreshes_per_day: number
  daily_request_limit: number
  reserved_request_count: number
  schedule_timezone: string
  api_key_configured: boolean
  api_key_masked: string
}

export interface ExchangeRateDiagnostics extends ExchangeRateAdminConfig {
  status: string
  estimated_scheduled_usage: number
  safe_scheduled_limit: number
  internal_daily_usage: number
  internal_completed_usage: number
  provider_usage: { daily_usage: number | null; hourly_usage: number | null; monthly_usage: number | null; last_use: string | null } | null
  effective_usage: number
  remaining_safe_requests: number
  usage_discrepancy: number | null
  usage_reconciliation_status: string
  usage_reconciled_at: string | null
  usage_error_code: string | null
  last_success_at: string | null
  last_failure_at: string | null
  last_error: string | null
  next_scheduled_refresh: string | null
  next_eligible_refresh: string | null
  runner_state: string | null
  runner_heartbeat_at: string | null
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
  implementation_status?: string | null
  placeholder: boolean
  credential_status: string
  connection_configured?: boolean
  configuration_state?: 'not_configured' | 'setup_required' | 'configured' | string
  /** Runtime availability of the persisted external connector. */
  enabled?: boolean
  source_profile_id?: string | null
  lifecycle_status?: 'active' | 'disabled' | 'archived' | string | null
  archived_at?: string | null
  last_health_check: string | null
  data_role: string
  action_label: string
  action_href: string
  health: CommerceHealth
  read_policy?: CommerceSourceReadPolicy
  read_status?: CommerceSourceReadStatus
  read_only: boolean
  runtime_write_blocked: boolean
  settings_available: boolean
}

export interface CommerceSourceReadPolicy {
  enabled: boolean
  max_reads_per_24h: number
  manual_read_allowed: boolean
  reads_used_last_24h: number
  reads_remaining: number
  reset_at: string | null
  last_read_at: string | null
}

export interface CommerceSourceReadStatus extends CommerceSourceReadPolicy {
  last_read_status: string | null
  last_row_count: number | null
  last_warning_count: number | null
  last_error_count: number | null
}

export interface CommerceChannel {
  id: string
  provider: string
  name: string
  display_name_custom?: boolean
  type: 'Channel'
  status: string
  implemented: boolean
  implementation_status?: string | null
  placeholder: boolean
  enabled: boolean
  read_only: boolean
  write_blocked: boolean
  runtime_write_blocked: boolean
  credential_status: string
  configuration_state?: string
  credentials_configured?: boolean
  credentials_verified?: boolean
  vendor_selected?: boolean
  vendor_accessible?: boolean
  token_configured?: boolean
  webhook_token_configured?: boolean
  access_token_configured?: boolean
  refresh_token_configured?: boolean
  last_health_check: string | null
  health: CommerceHealth
  capabilities: Record<string, boolean>
  capabilities_summary: string[]
  settings_available: boolean
  cached_products: number
  cached_variations: number
  last_cache_refresh: string | null
  cache_refresh_status: string
  cache_refresh_recovery_reason?: string | null
  cache_refresh_last_heartbeat?: string | null
  product_sync_error_category?: string | null
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
  implementation_status?: string | null
  placeholder: boolean
  read_only: boolean
  write_blocked?: boolean
  runtime_write_blocked: boolean
  settings_schema: CommerceTypeField[]
}

// -- Activity ------------------------------------------------------------------

export type ActivityEventKind = 'user_action' | 'system_log' | 'business_event'
export type ActivityLevel = 'critical' | 'error' | 'warning' | 'success' | 'info' | 'debug'
export type BusinessEventStatus = 'open' | 'acknowledged' | 'resolved'

export interface ActivityEvent {
  id: string
  timestamp: Date
  kind: ActivityEventKind
  level: ActivityLevel
  category?: string
  actor: string
  action: string
  detail: string | null
  repeatCount?: number
  // Present only for kind === 'business_event' rows (Business Observability v1).
  businessEventId?: string
  businessImpact?: string
  status?: BusinessEventStatus
  recommendedAction?: string | null
  actionUrl?: string | null
  retryable?: boolean
}

// -- Business Observability ------------------------------------------------------------------

export interface BusinessEventLifecycleTransition {
  id: number
  fromStatus: BusinessEventStatus | null
  toStatus: BusinessEventStatus
  actor: string
  occurredAt: Date
  note: string | null
}

export interface BusinessObservabilityKpis {
  openBlockingByDomain: Record<string, number>
  writePipelinePartialFailureRate30d: number
  oldestUnresolvedBlockingEventAgeSeconds: number | null
}
