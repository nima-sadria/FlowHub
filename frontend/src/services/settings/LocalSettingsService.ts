import type { AppSettings } from '../types'
import type { SettingsService } from './SettingsService'

const delay = (ms: number) => new Promise<void>(r => setTimeout(r, ms))
const SESSION_KEY = 'wp_local_settings'

const DEFAULTS: AppSettings = {
  woocommerceUrl: 'https://shop.example.com',
  nextcloudUrl: 'https://cloud.example.com',
  syncIntervalMinutes: 60,
  timezone: 'UTC',
  currency: 'EUR',
  environment: 'production',
}

function loadSettings(): AppSettings {
  try {
    const raw = sessionStorage.getItem(SESSION_KEY)
    if (raw) return { ...DEFAULTS, ...(JSON.parse(raw) as Partial<AppSettings>) }
  } catch { /* ignore */ }
  return { ...DEFAULTS }
}

export class LocalSettingsService implements SettingsService {
  private settings: AppSettings = loadSettings()

  async getSettings(): Promise<AppSettings> {
    await delay(100)
    return { ...this.settings }
  }

  async updateSettings(patch: Partial<AppSettings>): Promise<AppSettings> {
    await delay(150)
    this.settings = { ...this.settings, ...patch }
    try {
      sessionStorage.setItem(SESSION_KEY, JSON.stringify(this.settings))
    } catch { /* ignore */ }
    return { ...this.settings }
  }
}
