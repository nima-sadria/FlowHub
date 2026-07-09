import type { AppSettings, RateLimitSettings } from '../types'
import type { SettingsService } from './SettingsService'
import { apiFetch } from '../../api/client'
import { authFetch } from '../../api/authFetch'

interface RawSettings {
  woocommerceUrl: string
  nextcloudUrl: string
  syncIntervalMinutes: number
  timezone: string
  currency: string
  environment: string
  wcConfigured?: boolean
  ncConfigured?: boolean
}

export class ApiSettingsService implements SettingsService {
  async getSettings(): Promise<AppSettings> {
    const data = await apiFetch<RawSettings>('/api/v2/settings', authFetch)
    return {
      woocommerceUrl: data.woocommerceUrl,
      nextcloudUrl: data.nextcloudUrl,
      syncIntervalMinutes: data.syncIntervalMinutes,
      timezone: data.timezone,
      currency: data.currency,
      environment: data.environment,
      wcConfigured: data.wcConfigured ?? false,
      ncConfigured: data.ncConfigured ?? false,
    }
  }

  async updateSettings(patch: Partial<AppSettings>): Promise<AppSettings> {
    await apiFetch<unknown>('/api/v2/settings', authFetch, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        timezone: patch.timezone,
        currency: patch.currency,
        syncIntervalMinutes: patch.syncIntervalMinutes,
      }),
    })
    return this.getSettings()
  }

  async getRateLimits(): Promise<RateLimitSettings> {
    return apiFetch<RateLimitSettings>('/api/v2/settings/rate-limits', authFetch)
  }

  async updateRateLimits(patch: Pick<RateLimitSettings, 'read_requests_per_minute' | 'write_requests_per_minute'>): Promise<RateLimitSettings> {
    return apiFetch<RateLimitSettings>('/api/v2/settings/rate-limits', authFetch, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(patch),
    })
  }
}
