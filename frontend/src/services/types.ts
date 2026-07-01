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
