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
}

export interface WorkspacePreview {
  id: string
  sourceId: string
  sourceName: string
  state: WorkspaceState
  totalChanges: number
  changes: PriceChange[]
  startedAt: Date
  duplicateWarnings?: string[]
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
