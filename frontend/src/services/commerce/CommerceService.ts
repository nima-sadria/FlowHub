import type { CommerceChannel, CommerceRelationshipMap, CommerceSource, CommerceTypeOption } from '../types'

export interface ConnectionCheckResult {
  ok: boolean
  status: string
  message: string
  external_call_performed: boolean
  read_only: boolean
  runtime_write_blocked: boolean
  write_blocked: boolean
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
}

export interface CommerceConfigPayload {
  display_name: string
  enabled: boolean
  description?: string
  settings: Record<string, string | boolean>
  secrets: Record<string, string>
}

export interface CommerceSettingsResult {
  settings: Record<string, unknown>
  secrets: Record<string, { status: string; replaced_at: string | null }>
  read_only: boolean
  runtime_write_blocked: boolean
  write_blocked: boolean
}
