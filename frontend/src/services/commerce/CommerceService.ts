import type { CommerceChannel, CommerceRelationshipMap, CommerceSource, CommerceTypeOption } from '../types'

export interface ConnectionCheckResult {
  ok: boolean
  status: string
  message: string
  external_call_performed: boolean
  read_only: boolean
  runtime_write_blocked: boolean
  write_blocked: boolean
  webdav_reachable?: boolean
  spreadsheet_found?: boolean | null
  normalized_base_url?: string
  normalized_webdav_url?: string
  checked_at?: string
}

export interface CommerceService {
  getSources(): Promise<{ items: CommerceSource[]; relationship_map: CommerceRelationshipMap }>
  getChannels(): Promise<{ items: CommerceChannel[] }>
  getSourceTypes(): Promise<{ items: CommerceTypeOption[] }>
  getChannelTypes(): Promise<{ items: CommerceTypeOption[] }>
  saveSource(sourceId: string, payload: CommerceConfigPayload): Promise<CommerceSettingsResult>
  saveChannel(channelId: string, payload: CommerceConfigPayload): Promise<CommerceSettingsResult>
  testSource(sourceId: string): Promise<ConnectionCheckResult>
  testChannel(channelId: string): Promise<ConnectionCheckResult>
  refreshChannelCache(channelId: string): Promise<ChannelCacheRefreshResult>
  readSource(sourceId: string): Promise<SourceReadResult>
  browseNextcloud(sourceId: string, payload: NextcloudBrowseRequest): Promise<NextcloudBrowseResult>
}

export interface ChannelCacheRefreshResult {
  ok: boolean
  status: 'completed' | 'completed_with_warnings' | 'failed'
  products_read: number
  variable_products_read: number
  variations_read: number
  cache_rows_upserted: number
  warnings: string[]
  errors: string[]
  started_at: string
  completed_at: string
  read_only: boolean
  external_write: boolean
  stock_write: boolean
  source_write: boolean
  dry_run_created: boolean
  approval_created: boolean
  apply_executed: boolean
  credentials_returned: boolean
}

export interface CommerceConfigPayload {
  display_name: string
  enabled: boolean
  description?: string
  settings: Record<string, unknown>
  secrets: Record<string, string>
}

export interface CommerceSettingsResult {
  settings: Record<string, unknown>
  secrets: Record<string, { status: string; replaced_at: string | null }>
  read_only: boolean
  runtime_write_blocked: boolean
  write_blocked: boolean
}

export interface NextcloudBrowseRequest {
  path: string
  settings: Record<string, string | boolean>
  secrets: Record<string, string>
}

export interface NextcloudBrowseItem {
  name: string
  path: string
  type: 'directory' | 'file'
  extension: string
  modified_at: string | null
  size: number | null
  supported: boolean
}

export interface NextcloudBrowseResult {
  path: string
  directories: NextcloudBrowseItem[]
  files: NextcloudBrowseItem[]
  read_only: boolean
  write_blocked: boolean
  external_call_performed: boolean
  credentials_returned: boolean
}

export interface SourceReadResult {
  ok: boolean
  rows_read: number
  valid_rows: number
  warning_rows: number
  error_rows: number
  last_read_at: string
  remaining_reads_today: number
  reads_used_last_24h: number
  reads_remaining: number
  reset_at: string | null
  warnings: string[]
  errors: string[]
  source_id: string
  source_type: string
  spreadsheet_path: string
  external_call_performed: boolean
  read_only: boolean
  source_write: boolean
  write_blocked: boolean
}
