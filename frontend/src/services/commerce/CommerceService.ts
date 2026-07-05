import type { CommerceChannel, CommerceRelationshipMap, CommerceSource } from '../types'

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
  testChannel(channelId: string): Promise<ConnectionCheckResult>
}
