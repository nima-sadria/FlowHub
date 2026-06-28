import type { SystemHealth } from '../types'

export interface HealthService {
  getHealth(): Promise<SystemHealth>
}
