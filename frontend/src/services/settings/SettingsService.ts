import type { AppSettings, RateLimitSettings } from '../types'

export interface SettingsService {
  getSettings(): Promise<AppSettings>
  updateSettings(patch: Partial<AppSettings>): Promise<AppSettings>
  getRateLimits(): Promise<RateLimitSettings>
  updateRateLimits(patch: Pick<RateLimitSettings, 'read_requests_per_minute' | 'write_requests_per_minute'>): Promise<RateLimitSettings>
}
