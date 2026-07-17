import type { ActivityEvent, PaginatedResult } from '../types'
import type { ActivityService } from './ActivityService'
import { apiFetch } from '../../api/client'
import { authFetch } from '../../api/authFetch'

interface RawEvent {
  id: string
  timestamp: string
  kind: string
  level: string
  category: string
  actor: string
  action: string
  detail: string | null
}

interface RawPage {
  items: RawEvent[]
  total: number
  page: number
  pageSize: number
}

function mapEvent(r: RawEvent): ActivityEvent {
  return {
    id: r.id,
    timestamp: new Date(r.timestamp),
    kind: r.kind as ActivityEvent['kind'],
    level: r.level as ActivityEvent['level'],
    category: r.category,
    actor: r.actor,
    action: r.action,
    detail: r.detail,
  }
}

export class ApiActivityService implements ActivityService {
  async getEvents(opts: Parameters<ActivityService['getEvents']>[0]): Promise<PaginatedResult<ActivityEvent>> {
    const params = new URLSearchParams({
      page: String(opts.page),
      pageSize: String(opts.pageSize),
    })
    if (opts.search) params.set('search', opts.search)
    if (opts.username) params.set('username', opts.username)
    if (opts.category) params.set('category', opts.category)
    if (opts.severity) params.set('severity', opts.severity)
    if (opts.dateFrom) params.set('dateFrom', opts.dateFrom)
    if (opts.dateTo) params.set('dateTo', opts.dateTo)
    if (opts.source) params.set('source', opts.source)
    if (opts.channel) params.set('channel', opts.channel)
    if (opts.includeDebug) params.set('includeDebug', 'true')
    const data = await apiFetch<RawPage>(`/api/v2/activity?${params}`, authFetch)
    return {
      items: data.items.map(mapEvent),
      total: data.total,
      page: data.page,
      pageSize: data.pageSize,
    }
  }
}
