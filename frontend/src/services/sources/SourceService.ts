import type { Source, SourceConfig, ConnectionTestResult } from '../types'

export interface SourceService {
  getSources(): Promise<Source[]>
  testConnection(config: SourceConfig): Promise<ConnectionTestResult>
  createSource(config: SourceConfig): Promise<Source>
}
