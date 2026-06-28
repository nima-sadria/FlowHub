import type { SystemHealth } from '../types'
import type { HealthService } from './HealthService'

const delay = (ms: number) => new Promise<void>(r => setTimeout(r, ms))

export class MockHealthService implements HealthService {
  async getHealth(): Promise<SystemHealth> {
    await delay(80)
    return {
      status: 'ok',
      version: '0.1.0-dev',
      environment: 'beta',
      checkedAt: new Date(),
    }
  }
}
