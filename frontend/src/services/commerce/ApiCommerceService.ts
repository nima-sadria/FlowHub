import { apiFetch } from '../../api/client'
import { authFetch } from '../../api/authFetch'
import type { CommerceChannel, CommerceRelationshipMap, CommerceSource, CommerceTypeOption } from '../types'
import type {
  CommerceConfigPayload,
  CommerceService,
  CommerceSettingsResult,
  ConnectionCheckResult,
  NextcloudBrowseRequest,
  NextcloudBrowseResult,
  SourceReadResult,
} from './CommerceService'

interface SourceResponse {
  items: CommerceSource[]
  relationship_map: CommerceRelationshipMap
}

interface ChannelResponse {
  items: CommerceChannel[]
}

interface TypeResponse {
  items: CommerceTypeOption[]
}

export class ApiCommerceService implements CommerceService {
  async getSources(): Promise<SourceResponse> {
    return apiFetch<SourceResponse>('/api/v2/commerce/sources', authFetch)
  }

  async getChannels(): Promise<ChannelResponse> {
    return apiFetch<ChannelResponse>('/api/v2/commerce/channels', authFetch)
  }

  async getSourceTypes(): Promise<TypeResponse> {
    return apiFetch<TypeResponse>('/api/v2/commerce/source-types', authFetch)
  }

  async getChannelTypes(): Promise<TypeResponse> {
    return apiFetch<TypeResponse>('/api/v2/commerce/channel-types', authFetch)
  }

  async saveSource(sourceId: string, payload: CommerceConfigPayload): Promise<CommerceSettingsResult> {
    return apiFetch<CommerceSettingsResult>(`/api/v2/commerce/sources/${encodeURIComponent(sourceId)}/settings`, authFetch, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
  }

  async saveChannel(channelId: string, payload: CommerceConfigPayload): Promise<CommerceSettingsResult> {
    return apiFetch<CommerceSettingsResult>(`/api/v2/commerce/channels/${encodeURIComponent(channelId)}/settings`, authFetch, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
  }

  async testSource(sourceId: string): Promise<ConnectionCheckResult> {
    return apiFetch<ConnectionCheckResult>(`/api/v2/commerce/sources/${encodeURIComponent(sourceId)}/test`, authFetch, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    })
  }

  async testChannel(channelId: string): Promise<ConnectionCheckResult> {
    return apiFetch<ConnectionCheckResult>(`/api/v2/commerce/channels/${encodeURIComponent(channelId)}/test`, authFetch, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    })
  }

  async readSource(sourceId: string): Promise<SourceReadResult> {
    return apiFetch<SourceReadResult>(`/api/v2/commerce/sources/${encodeURIComponent(sourceId)}/read`, authFetch, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    })
  }

  async browseNextcloud(sourceId: string, payload: NextcloudBrowseRequest): Promise<NextcloudBrowseResult> {
    return apiFetch<NextcloudBrowseResult>(`/api/v2/commerce/sources/${encodeURIComponent(sourceId)}/browse`, authFetch, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
  }
}
