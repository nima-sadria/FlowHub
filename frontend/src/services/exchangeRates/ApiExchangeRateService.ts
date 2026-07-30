import { apiFetch } from '../../api/client'
import { authFetch } from '../../api/authFetch'
import type { ExchangeRateAdminConfig, ExchangeRateDefinition, ExchangeRateDiagnostics, ExchangeRateSnapshotView } from '../types'
import type { ExchangeRateService } from './ExchangeRateService'

export class ApiExchangeRateService implements ExchangeRateService {
  async getSupported(): Promise<ExchangeRateDefinition[]> {
    const data = await apiFetch<{ items: ExchangeRateDefinition[] }>('/api/v2/exchange-rates/supported', authFetch)
    return data.items
  }

  async getLatest(): Promise<{ selections: string[]; rates: ExchangeRateSnapshotView[] }> {
    return apiFetch('/api/v2/exchange-rates/me', authFetch)
  }

  async updateSelections(selections: string[]): Promise<{ selections: string[]; rates: ExchangeRateSnapshotView[] }> {
    return apiFetch('/api/v2/exchange-rates/me', authFetch, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ selections }) })
  }

  async getAdminConfig(): Promise<ExchangeRateAdminConfig> {
    return apiFetch('/api/v2/exchange-rates/admin/config', authFetch)
  }

  async updateAdminConfig(patch: Record<string, unknown>): Promise<ExchangeRateAdminConfig> {
    return apiFetch('/api/v2/exchange-rates/admin/config', authFetch, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(patch) })
  }

  async testConnection(): Promise<{ ok: boolean; status: string }> {
    return apiFetch('/api/v2/exchange-rates/admin/test-connection', authFetch, { method: 'POST' })
  }

  async synchronizeUsage(): Promise<{ status: string; error_code?: string }> {
    return apiFetch('/api/v2/exchange-rates/admin/usage-sync', authFetch, { method: 'POST' })
  }

  async getDiagnostics(): Promise<ExchangeRateDiagnostics> {
    return apiFetch('/api/v2/exchange-rates/admin/diagnostics', authFetch)
  }

  async refresh(): Promise<{ status: string; records: number }> {
    return apiFetch('/api/v2/exchange-rates/admin/refresh', authFetch, { method: 'POST' })
  }
}
