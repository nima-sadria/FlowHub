import { apiFetch } from '../../api/client'
import { authFetch } from '../../api/authFetch'
import type { CommerceChannel, CommerceRelationshipMap, CommerceSource } from '../types'
import type { CommerceService, ConnectionCheckResult } from './CommerceService'

interface SourceResponse {
  items: CommerceSource[]
  relationship_map: CommerceRelationshipMap
}

interface ChannelResponse {
  items: CommerceChannel[]
}

export class ApiCommerceService implements CommerceService {
  async getSources(): Promise<SourceResponse> {
    return apiFetch<SourceResponse>('/api/v2/commerce/sources', authFetch)
  }

  async getChannels(): Promise<ChannelResponse> {
    return apiFetch<ChannelResponse>('/api/v2/commerce/channels', authFetch)
  }

  async testChannel(channelId: string): Promise<ConnectionCheckResult> {
    return apiFetch<ConnectionCheckResult>(`/api/v2/commerce/channels/${encodeURIComponent(channelId)}/test`, authFetch, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    })
  }
}
