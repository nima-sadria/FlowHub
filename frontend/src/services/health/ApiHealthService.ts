import type { SystemHealth } from '../types'
import type { HealthService } from './HealthService'
import { apiFetch } from '../../api/client'
import { authFetch } from '../../api/authFetch'

export class ApiHealthService implements HealthService {
  async getHealth(): Promise<SystemHealth> {
    const data = await apiFetch<{ status: string; version: string; env: string }>(
      '/api/health',
      authFetch,
    )
    return {
      status: data.status as SystemHealth['status'],
      version: data.version,
      environment: data.env,
      checkedAt: new Date(),
    }
  }
}
