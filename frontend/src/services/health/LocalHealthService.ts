import type { SystemHealth } from '../types'
import type { HealthService } from './HealthService'

const delay = (ms: number) => new Promise<void>(r => setTimeout(r, ms))

export class LocalHealthService implements HealthService {
  async getHealth(): Promise<SystemHealth> {
    await delay(80)
    return {
      status: 'ok',
      version: '1.0.0',
      environment: 'production',
      checkedAt: new Date(),
    }
  }
}
