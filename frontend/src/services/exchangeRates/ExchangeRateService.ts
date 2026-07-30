import type { ExchangeRateAdminConfig, ExchangeRateDefinition, ExchangeRateDiagnostics, ExchangeRateSnapshotView } from '../types'

export interface ExchangeRateService {
  getSupported(): Promise<ExchangeRateDefinition[]>
  getLatest(): Promise<{ selections: string[]; rates: ExchangeRateSnapshotView[] }>
  updateSelections(selections: string[]): Promise<{ selections: string[]; rates: ExchangeRateSnapshotView[] }>
  getAdminConfig(): Promise<ExchangeRateAdminConfig>
  updateAdminConfig(patch: Record<string, unknown>): Promise<ExchangeRateAdminConfig>
  testConnection(): Promise<{ ok: boolean; status: string }>
  synchronizeUsage(): Promise<{ status: string; error_code?: string }>
  getDiagnostics(): Promise<ExchangeRateDiagnostics>
  refresh(): Promise<{ status: string; records: number }>
}
