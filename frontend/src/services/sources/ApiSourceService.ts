import type { Source } from '../types'
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
}
