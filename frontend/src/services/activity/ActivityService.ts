import type { ActivityEvent, PaginatedResult } from '../types'

export interface ActivityService {
  getEvents(opts: { page: number; pageSize: number }): Promise<PaginatedResult<ActivityEvent>>
}
