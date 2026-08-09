import type { BusinessEventLifecycleTransition, BusinessEventStatus } from '../types'

export interface BusinessEventLifecycleResult {
  status: BusinessEventStatus
  acknowledgedAt: Date | null
  acknowledgedBy: string | null
  resolvedAt: Date | null
  resolvedBy: string | null
}

export interface BusinessEventService {
  acknowledge(eventId: string, note?: string): Promise<BusinessEventLifecycleResult>
  resolve(eventId: string, note?: string): Promise<BusinessEventLifecycleResult>
  getLifecycle(eventId: string): Promise<BusinessEventLifecycleTransition[]>
}
