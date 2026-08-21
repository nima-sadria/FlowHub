export type ReferenceType = 'column_letter' | 'header_name' | 'column_id' | 'disabled'

export type IdentityAuthorityType = 'external_system' | 'internal' | 'custom' | 'unspecified'

export interface IdentityAuthority {
  type: IdentityAuthorityType
  systemIdentifier: string | null
  displayLabel: string | null
}

export type MappingReadiness = 'ready' | 'identity_validation_pending' | 'identity_validation_blocked'

export type IdentityValidationRow = string | { worksheetName: string; rowNumber: number }

export interface IdentityValidation {
  status: 'pass' | 'blocked' | 'pending'
  participatingRowCount?: number | null
  validKeyCount?: number | null
  missingKeyCount?: number | null
  duplicateKeyCount?: number | null
  duplicateRowCount?: number | null
  bindingConflictCount?: number | null
  bindingContextFingerprint?: string | null
  missingRows?: IdentityValidationRow[]
  duplicateGroups?: Array<{ keyValue: string; rows: IdentityValidationRow[] }>
  bindingConflicts?: Array<{
    keyValue: string
    rows: IdentityValidationRow[]
    boundCanonicalProductId: string | null
    conflictingCanonicalProductIds: string[]
  }>
  mappingReferences?: Array<{
    worksheetName: string | null
    referenceType: ReferenceType
    referenceValue: string | null
  }>
  evidence?: {
    kind: 'source_observation' | 'flowhub_sheet_revision' | 'none'
    sourceRevisionId: string | null
    datasetId: string | null
    snapshotId: number | null
    snapshotVersion: number | null
    label: string | null
    validatedAt: string | null
  } | null
}

export interface SourceProfile {
  id: string
  name: string
  sourceKind: 'flowhub_sheet' | 'imported_sheet' | 'external'
  externalSourceId: string | null
  worksheetMode: 'all' | 'selected'
  worksheetName: string | null
  dataStartRow: number
  status: string
  archivedAt?: string | null
  version: number
  mappingVersion: number
  mappingReadiness?: MappingReadiness | null
  sheetId: string | null
  createdAt: string | null
  updatedAt: string | null
  readQuota?: {
    enabled: boolean
    limit: number
    usage: number
    remaining: number
    reset_at: string | null
    exhausted: boolean
  }
  discoveryQuota?: {
    enabled: boolean
    limit: number
    usage: number
    remaining: number
    reset_at: string | null
    exhausted: boolean
  }
  worksheetDiscovery?: {
    requires_remote_read: boolean
    metadata_source: 'snapshot' | 'discovery_cache' | 'remote' | 'unavailable'
    reason: string | null
    snapshot_id: number | null
    snapshot_version: number | null
    snapshot_at: string | null
    worksheet_names: string[]
  }
  currencyProfile?: {
    status: 'resolved' | 'unresolved'
    currency: string | null
    unit: string | null
  }
  legacyMapping?: {
    primaryChannelId: string
    fields: FieldMapping[]
    requiresConfirmation: boolean
  } | null
}

export interface SourceLifecycleImpact {
  sourceId: string
  sourceName: string
  sourceVersion: number
  sourceStatus: string
  action: 'none' | 'delete' | 'archive' | 'blocked'
  blockers: Record<string, number>
  protectedHistory: Record<string, number>
  archiveAllowed?: boolean
  permanentDeleteAllowed?: boolean
  permanentDeletePolicy?: 'immutable_history_tombstone'
}

export interface SourceLifecycleResult {
  sourceId: string
  sourceName: string
  outcome: 'deleted' | 'archived'
  source: SourceProfile | null
  impact: SourceLifecycleImpact
  tombstone?: boolean
}

export type SourcePreviewValue = string | number | boolean | null

export interface SourcePreviewItem {
  rowKey: string
  rowNumber: number
  worksheetName: string
  recognized: boolean
  hasIssues: boolean
  ready: boolean
  sourceProduct: Record<string, SourcePreviewValue>
  channels: Array<{ channelId: string; fields: Record<string, SourcePreviewValue> }>
  valuePolicy: Record<string, unknown>
  issues: Array<{ category: string; severity: string; channelId: string | null; message: string; details?: Record<string, unknown> }>
}

export interface SourcePreview {
  items: SourcePreviewItem[]
  total: number
  recognized: number
  ignored: number
  issues: Array<{ category: string; severity: string; channelId: string | null; count: number }>
  businessSummary: {
    productsFound: number
    productsReady: number
    priceChanges: number | null
    stockChanges: number | null
    unchanged: number | null
    needsAttention: number
    channelsReady: number
    channelsNotConfigured: number
  }
  identityValidation?: IdentityValidation | null
  sheetRevisionId: string | null
  mappingRevisionId: string | null
}

export type DataQualityScanState = 'never_checked' | 'checking' | 'healthy' | 'issues_found' | 'failed' | 'permission_denied'

export interface DataQualitySummary {
  state: DataQualityScanState
  totalIssues: number
  blockingIssues: number
  warnings: number
  affectedProducts: number
  affectedChannels: number
  affectedSources: number
  resolvedSinceLastRead: number
  trendSinceLastRead: number | null
  productsChecked: number
  sourcesChecked: number
  checkedAt: string | null
  scanId: string | null
  errorCode: string | null
  categories: Array<{ category: string; count: number }>
}

export interface SourceChannel {
  channelId: string
  name: string
  displayNameCustom?: boolean
  connectorType: string
  capabilityVersion: string
  capabilities: Record<string, unknown>
  enabled: boolean
  implementationState: 'implemented' | 'coming_soon' | string
  available: boolean
  configured?: boolean
}

export interface FieldMapping {
  field: string
  referenceType: ReferenceType
  referenceValue: string | null
  required?: boolean
}

export interface SourceWorksheetRule {
  worksheetName: string
  enabled: boolean
  dataStartRow: number
  valuePolicy: Record<string, unknown>
  sourceFields: FieldMapping[]
  channels: SourceMapping['channels']
}

export interface SourceMapping {
  id: string
  version: number
  checksum: string
  worksheetMode: 'all' | 'selected'
  worksheetName: string | null
  dataStartRow: number
  valuePolicy: Record<string, unknown>
  worksheetRuleMode?: 'shared' | 'per_worksheet'
  selectedWorksheetNames?: string[]
  duplicateProductPolicy?: 'block' | 'last_sheet_wins'
  identityAuthority: IdentityAuthority
  identityPolicyVersion: number
  mappingReadiness: MappingReadiness
  identityValidation: IdentityValidation | null
  worksheetRules?: SourceWorksheetRule[]
  sourceFields: FieldMapping[]
  channels: Array<{
    channelId: string
    worksheetName: string | null
    enabled: boolean
    fields: FieldMapping[]
  }>
}

export interface SheetColumn {
  columnKey: string
  name: string
  position: number
  dataType: string
}

export interface SheetCell {
  raw: string | null
  value: string | null
  formula: string | null
  error: string | null
}

export interface SheetRow {
  rowKey: string
  position: number
  cells: Record<string, SheetCell>
}

export interface FlowHubSheetPage {
  id: string
  sourceId: string
  name: string
  version: number
  revisionId: string | null
  revisionChecksum?: string
  formulaEngineVersion?: string
  columns: SheetColumn[]
  rows: SheetRow[]
  total: number
  page: number
  pageSize: number
}

export interface GroupedField {
  current: string | null
  target: string | null
  changed: boolean
  readOnly: boolean
  status: 'ready' | 'blocked' | 'unchanged'
  currency: string | null
  unit: string | null
}

export interface ChangeBadgeDimension {
  state: string
  current?: string
  target?: string
  delta?: string
}

/** Backend-authoritative Phase B explanation; it never grants write authority. */
export interface ChangeBadgeClassification {
  version: string
  price: ChangeBadgeDimension
  quantity: ChangeBadgeDimension
  stockStatus: ChangeBadgeDimension
  warnings: Array<{ code: string; field?: string }>
  blockers: string[]
  eligibility: 'ELIGIBLE' | 'BLOCKED'
  actionable: boolean
}

export interface GroupedListing {
  listingId: string
  channelId: string
  listingLabel: string
  externalId: string
  externalIdType: string
  sku: string | null
  mappingState: string
  cacheFreshness: string
  state: 'ready' | 'blocked' | 'unchanged'
  changedFields: string[]
  selected: boolean
  reviewItemIds: string[]
  fields: Record<'price' | 'stock' | 'status', GroupedField>
  changeClassification?: ChangeBadgeClassification | null
}

export interface GroupedProduct {
  sourceProductId: string
  name: string
  sourceKey: string | null
  cost: string | null
  category: string | null
  brand: string | null
  productType: 'simple' | 'variable' | 'variation'
  primaryImageUrl?: string | null
  media?: Array<{ type: 'image'; url: string; position: number; source?: string }>
  mappedChannelCount: number
  listingCount: number
  changedListingCount: number
  selectedListingCount: number
  state: 'ready' | 'blocked' | 'unchanged'
  children: GroupedListing[]
}

export interface SourceMappingSaveRequest {
  expected_source_version: number
  worksheet_mode: 'all' | 'selected'
  worksheet_name: string | null
  selected_worksheet_names: string[]
  data_start_row: number
  source_fields: Array<{ field: string; reference_type: ReferenceType; reference_value: string | null; required: boolean }>
  channel_mappings: Array<{
    channel_id: string
    worksheet_name: string | null
    enabled: boolean
    fields: Array<{ field: string; reference_type: ReferenceType; reference_value: string | null; required: boolean }>
  }>
  value_policy: Record<string, unknown>
  worksheet_rule_mode: 'shared' | 'per_worksheet'
  duplicate_product_policy: 'block' | 'last_sheet_wins'
  worksheet_rules: Array<{
    worksheet_name: string
    enabled: boolean
    data_start_row: number
    value_policy: Record<string, unknown>
    source_fields: Array<{ field: string; reference_type: ReferenceType; reference_value: string | null; required: boolean }>
    channel_mappings: Array<{
      channel_id: string
      worksheet_name: string | null
      enabled: boolean
      fields: Array<{ field: string; reference_type: ReferenceType; reference_value: string | null; required: boolean }>
    }>
  }>
  identity_policy_version: number
  identity_authority: {
    type: IdentityAuthorityType
    system_identifier: string | null
    display_label: string | null
  }
}

export interface DiscoveredColumn {
  id: string
  letter: string
  header: string
}

export interface DiscoveredWorksheet {
  name: string
  rowCount: number | null
  columns: DiscoveredColumn[]
}

export interface GroupedWorkspacePage {
  items: GroupedProduct[]
  total: number
  page: number
  pageSize: number
  view: string
  summary: { ready: number; blocked: number; unchanged: number; selected: number }
  draftVersion: number
  revisionId: string | null
  reviewId: string | null
  reviewStatus: string | null
  selectionChecksum: string | null
}
