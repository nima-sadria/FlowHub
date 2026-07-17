import type { ActivityEvent, PaginatedResult } from '../types'

export interface ActivityService {
  getEvents(opts: {
    page: number
    pageSize: number
    search?: string
    username?: string
    category?: string
    severity?: string
    dateFrom?: string
    dateTo?: string
    source?: string
    channel?: string
    includeDebug?: boolean
  }): Promise<PaginatedResult<ActivityEvent>>
}
