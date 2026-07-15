export type ReferenceType = 'column_letter' | 'header_name' | 'column_id' | 'disabled'

export interface SourceProfile {
  id: string
  name: string
  sourceKind: 'flowhub_sheet' | 'imported_sheet' | 'external'
  externalSourceId: string | null
  worksheetMode: 'all' | 'selected'
  worksheetName: string | null
  dataStartRow: number
  status: string
  version: number
  mappingVersion: number
  sheetId: string | null
  legacyMapping?: {
    primaryChannelId: string
    fields: FieldMapping[]
    requiresConfirmation: boolean
  } | null
}

export interface SourceChannel {
  channelId: string
  name: string
  connectorType: string
  capabilityVersion: string
  capabilities: Record<string, unknown>
  enabled: boolean
  implementationState: 'implemented' | 'coming_soon' | string
  available: boolean
}

export interface FieldMapping {
  field: string
  referenceType: ReferenceType
  referenceValue: string | null
  required?: boolean
}

export interface SourceMapping {
  id: string
  version: number
  checksum: string
  worksheetMode: 'all' | 'selected'
  worksheetName: string | null
  dataStartRow: number
  valuePolicy: Record<string, string>
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
}

export interface GroupedProduct {
  sourceProductId: string
  name: string
  sourceKey: string | null
  cost: string | null
  category: string | null
  brand: string | null
  productType: 'simple' | 'variable' | 'variation'
  mappedChannelCount: number
  listingCount: number
  changedListingCount: number
  selectedListingCount: number
  state: 'ready' | 'blocked' | 'unchanged'
  children: GroupedListing[]
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
