import { translate } from '../../i18n'
import type { Source, SourceConfig, ConnectionTestResult } from '../types'
import type { SourceService } from './SourceService'

const delay = (ms: number) => new Promise<void>(r => setTimeout(r, ms))
const SESSION_KEY = 'wp_local_sources'

const DEFAULT_SOURCE: Source = {
  id: 'src-001',
  name: 'Nextcloud Price List',
  type: 'nextcloud_excel',
  displayUrl: 'cloud.example.com/Price_List.xlsx',
  status: 'active',
  lastSynced: new Date(Date.now() - 2 * 3600 * 1000),
  productCount: 12,
}

function loadSources(): Source[] {
  try {
    const raw = sessionStorage.getItem(SESSION_KEY)
    if (raw) {
      const parsed = JSON.parse(raw) as Array<Source & { lastSynced: string | null }>
      return parsed.map(s => ({ ...s, lastSynced: s.lastSynced ? new Date(s.lastSynced) : null }))
    }
  } catch { /* ignore */ }
  return [DEFAULT_SOURCE]
}

function saveSources(sources: Source[]): void {
  try {
    sessionStorage.setItem(SESSION_KEY, JSON.stringify(sources))
  } catch { /* ignore quota errors */ }
}

export class LocalSourceService implements SourceService {
  private sources: Source[] = loadSources()

  async getSources(): Promise<Source[]> {
    await delay(100)
    return [...this.sources]
  }

  async testConnection(_config: SourceConfig): Promise<ConnectionTestResult> {
    await delay(1500)
    return {
      success: true,
      message: translate('common:localSourceService.connectedSuccessfully12ProductsFound'),
      discoveredProductCount: 12,
    }
  }

  async createSource(config: SourceConfig): Promise<Source> {
    await delay(200)
    const url = new URL(config.url.startsWith('http') ? config.url : `https://${config.url}`)
    const newSource: Source = {
      id: `src-${Date.now()}`,
      name: config.name,
      type: config.type,
      displayUrl: `${url.hostname}${config.filePath}`,
      status: 'active',
      lastSynced: new Date(),
      productCount: 12,
    }
    this.sources = [...this.sources, newSource]
    saveSources(this.sources)
    return newSource
  }
}
