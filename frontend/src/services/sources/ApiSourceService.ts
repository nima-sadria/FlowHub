import type { Source, SourceConfig, ConnectionTestResult } from '../types'
import type { SourceService } from './SourceService'
import { apiFetch } from '../../api/client'
import { authFetch } from '../../api/authFetch'

interface RawSource {
  id: string
  name: string
  type: string
  displayUrl: string
  status: string
  lastSynced: string | null
  productCount: number
}

function mapSource(r: RawSource): Source {
  return {
    id: r.id,
    name: r.name,
    type: r.type as Source['type'],
    displayUrl: r.displayUrl,
    status: r.status as Source['status'],
    lastSynced: r.lastSynced ? new Date(r.lastSynced) : null,
    productCount: r.productCount,
  }
}

export class ApiSourceService implements SourceService {
  async getSources(): Promise<Source[]> {
    const data = await apiFetch<{ items: RawSource[] }>('/api/v2/sources', authFetch)
    return data.items.map(mapSource)
  }

  async testConnection(_config: SourceConfig): Promise<ConnectionTestResult> {
    // In BU5 connection testing is done inside Settings; this method is not used
    return { success: false, message: 'Use Settings to configure Nextcloud.' }
  }

  async createSource(_config: SourceConfig): Promise<Source> {
    // Write guard — sources are configured via Settings wizard in BU5
    throw new Error('Write operations are disabled in FlowHub Beta.')
  }
}
