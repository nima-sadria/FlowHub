import type { ActivityEvent, PaginatedResult } from '../types'
import type { ActivityService } from './ActivityService'
import { apiFetch } from '../../api/client'
import { authFetch } from '../../api/authFetch'

interface RawEvent {
  id: string
  timestamp: string
  kind: string
  level: string
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
    actor: r.actor,
    action: r.action,
    detail: r.detail,
  }
}

export class ApiActivityService implements ActivityService {
  async getEvents(opts: { page: number; pageSize: number }): Promise<PaginatedResult<ActivityEvent>> {
    const params = new URLSearchParams({
      page: String(opts.page),
      pageSize: String(opts.pageSize),
    })
    const data = await apiFetch<RawPage>(`/api/v2/activity?${params}`, authFetch)
    return {
      items: data.items.map(mapEvent),
      total: data.total,
      page: data.page,
      pageSize: data.pageSize,
    }
  }
}
