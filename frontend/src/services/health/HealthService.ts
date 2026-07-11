import type { ChannelHealthResponse, SystemHealth } from '../types'

export interface HealthService {
  getHealth(): Promise<SystemHealth>
  getChannelHealth(): Promise<ChannelHealthResponse>
  refreshChannelHealth(channelId?: string): Promise<ChannelHealthResponse>
}
