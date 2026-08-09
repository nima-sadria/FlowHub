import type { BusinessEventLifecycleTransition } from '../types'
import type { BusinessEventLifecycleResult, BusinessEventService } from './BusinessEventService'
import { apiFetch } from '../../api/client'
import { authFetch } from '../../api/authFetch'

interface RawLifecycleResult {
  status: string
  acknowledgedAt: string | null
  acknowledgedBy: string | null
  resolvedAt: string | null
  resolvedBy: string | null
}

interface RawTransition {
  id: number
  fromStatus: string | null
  toStatus: string
  actor: string
  occurredAt: string
  note: string | null
}

function mapResult(raw: RawLifecycleResult): BusinessEventLifecycleResult {
  return {
    status: raw.status as BusinessEventLifecycleResult['status'],
    acknowledgedAt: raw.acknowledgedAt ? new Date(raw.acknowledgedAt) : null,
    acknowledgedBy: raw.acknowledgedBy,
    resolvedAt: raw.resolvedAt ? new Date(raw.resolvedAt) : null,
    resolvedBy: raw.resolvedBy,
  }
}

export class ApiBusinessEventService implements BusinessEventService {
  async acknowledge(eventId: string, note?: string): Promise<BusinessEventLifecycleResult> {
    const raw = await apiFetch<RawLifecycleResult>(
      `/api/v2/business-events/${eventId}/acknowledge`,
      authFetch,
      { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ note: note ?? null }) },
    )
    return mapResult(raw)
  }

  async resolve(eventId: string, note?: string): Promise<BusinessEventLifecycleResult> {
    const raw = await apiFetch<RawLifecycleResult>(
      `/api/v2/business-events/${eventId}/resolve`,
      authFetch,
      { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ note: note ?? null }) },
    )
    return mapResult(raw)
  }

  async getLifecycle(eventId: string): Promise<BusinessEventLifecycleTransition[]> {
    const raw = await apiFetch<RawTransition[]>(
      `/api/v2/business-events/${eventId}/lifecycle`,
      authFetch,
    )
    return raw.map(item => ({
      id: item.id,
      fromStatus: item.fromStatus as BusinessEventLifecycleTransition['fromStatus'],
      toStatus: item.toStatus as BusinessEventLifecycleTransition['toStatus'],
      actor: item.actor,
      occurredAt: new Date(item.occurredAt),
      note: item.note,
    }))
  }
}
