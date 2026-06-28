import type { AppSettings } from '../types'

export interface SettingsService {
  getSettings(): Promise<AppSettings>
  updateSettings(patch: Partial<AppSettings>): Promise<AppSettings>
}
