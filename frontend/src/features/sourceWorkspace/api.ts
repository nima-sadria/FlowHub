import { apiFetch } from '../../api/client'
import { authFetch } from '../../api/authFetch'
import type {
  FlowHubSheetPage,
  GroupedWorkspacePage,
  SourceChannel,
  SourceMapping,
  SourceProfile,
  SourceLifecycleResult,
  SourceLifecycleImpact,
  SourcePreview,
  DataQualitySummary,
} from './types'
import type { ReviewResource } from '../../services/unifiedWorkspace/types'

export interface GroupedGridFilters {
  categoryId?: string
  productType?: 'simple' | 'variable' | 'variation'
  channelId?: string
  stockState?: 'in_stock' | 'out_of_stock'
}

const json = (method: 'POST' | 'PUT' | 'PATCH', body: unknown): RequestInit => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})

export const sourceWorkspaceApi = {
  listSources: () => apiFetch<{ items: SourceProfile[] }>('/api/v2/source-profiles', authFetch),
  channels: () => apiFetch<{ items: SourceChannel[] }>('/api/v2/source-profiles/channels', authFetch),
  source: (id: string) => apiFetch<SourceProfile & { mapping: SourceMapping | null }>(`/api/v2/sources/${encodeURIComponent(id)}/configuration`, authFetch),
  worksheets: (id: string) => apiFetch<{ sourceId: string; sourceRevisionId: string | null; items: Array<{ name: string; rowCount: number }> }>(`/api/v2/sources/${encodeURIComponent(id)}/worksheets`, authFetch),
  createSource: (payload: {
    name: string
    source_kind: 'external'
    external_source_id: string
    worksheet_mode: 'all' | 'selected'
    worksheet_name: string | null
    data_start_row: number
  }) => apiFetch<SourceProfile>('/api/v2/sources', authFetch, json('POST', payload)),
  createSheet: (name: string) => apiFetch<FlowHubSheetPage>('/api/v2/sheets', authFetch, json('POST', {
    name,
    columns: [
      { column_key: 'product-name', name: 'Product Name', position: 1, data_type: 'text' },
      { column_key: 'source-key', name: 'Source Key', position: 2, data_type: 'text' },
      { column_key: 'price', name: 'Price', position: 3, data_type: 'number' },
    ],
  })),
  getSheet: (id: string, page = 1, pageSize = 200, options: { search?: string; sortColumn?: string; sortDirection?: 'asc' | 'desc' } = {}) => {
    const params = new URLSearchParams({ page: String(page), pageSize: String(pageSize), sortDirection: options.sortDirection ?? 'asc' })
    if (options.search) params.set('search', options.search)
    if (options.sortColumn) params.set('sortColumn', options.sortColumn)
    return apiFetch<FlowHubSheetPage>(`/api/v2/sheets/${encodeURIComponent(id)}?${params}`, authFetch)
  },
  saveSheet: (sheet: FlowHubSheetPage, rows: Array<{ row_key: string; position: number; values: Record<string, string | null> }>) => apiFetch<FlowHubSheetPage>(`/api/v2/sheets/${encodeURIComponent(sheet.id)}/revisions`, authFetch, json('POST', {
    expected_version: sheet.version,
    columns: sheet.columns.map(column => ({ column_key: column.columnKey, name: column.name, position: column.position, data_type: column.dataType })),
    rows,
  })),
  patchSheet: (sheet: FlowHubSheetPage, changes: Array<{ row_key: string; column_key: string; value: string | null }>, columnNames: Record<string, string> = {}) => apiFetch<FlowHubSheetPage>(`/api/v2/sheets/${encodeURIComponent(sheet.id)}/revisions`, authFetch, json('PATCH', {
    expected_version: sheet.version,
    changes,
    column_names: columnNames,
  })),
  appendRows: (sheet: FlowHubSheetPage, count = 20) => apiFetch<FlowHubSheetPage>(`/api/v2/sheets/${encodeURIComponent(sheet.id)}/rows`, authFetch, json('POST', { expected_version: sheet.version, count })),
  saveMapping: (sourceId: string, payload: unknown) => apiFetch<SourceMapping>(`/api/v2/sources/${encodeURIComponent(sourceId)}/mappings`, authFetch, json('PUT', payload)),
  previewSource: (sourceId: string) => apiFetch<SourcePreview>(`/api/v2/sources/${encodeURIComponent(sourceId)}/preview?page=1&pageSize=100`, authFetch),
  previewImport: (payload: unknown) => apiFetch<Record<string, unknown>>('/api/v2/sheet-imports/preview', authFetch, json('POST', payload)),
  importSheet: (payload: unknown) => apiFetch<FlowHubSheetPage>('/api/v2/sheets/import', authFetch, json('POST', payload)),
  createWorkspace: (sourceId: string, name: string) => apiFetch<{ id: string }>('/api/v2/unified-workspaces/source', authFetch, json('POST', { source_id: sourceId, name })),
  deleteSource: (source: SourceProfile) => apiFetch<SourceLifecycleResult>(`/api/v2/sources/${encodeURIComponent(source.id)}`, authFetch, {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ expected_source_version: source.version, confirmation_name: source.name }),
  }),
  sourceLifecycle: (sourceId: string) => apiFetch<SourceLifecycleImpact>(`/api/v2/sources/${encodeURIComponent(sourceId)}/lifecycle`, authFetch),
  review: (workspaceId: string, reviewId: string) => apiFetch<ReviewResource>(`/api/v2/unified-workspaces/${encodeURIComponent(workspaceId)}/reviews/${encodeURIComponent(reviewId)}`, authFetch),
  groupedGrid: (workspaceId: string, page: number, view: string, search = '', filters: GroupedGridFilters = {}) => {
    const params = new URLSearchParams({ page: String(page), pageSize: '100', view })
    if (search) params.set('search', search)
    if (filters.categoryId) params.set('categoryId', filters.categoryId)
    if (filters.productType) params.set('productType', filters.productType)
    if (filters.channelId) params.set('channelId', filters.channelId)
    if (filters.stockState) params.set('stockState', filters.stockState)
    return apiFetch<GroupedWorkspacePage>(`/api/v2/unified-workspaces/${encodeURIComponent(workspaceId)}/grouped-grid?${params}`, authFetch)
  },
  dataQuality: (params: URLSearchParams) => apiFetch<{ items: Array<Record<string, unknown>>; counts: Record<string, number>; total: number; summary: DataQualitySummary }>(`/api/v2/data-quality?${params}`, authFetch),
  scanDataQuality: (sourceId?: string) => apiFetch<{ summary: DataQualitySummary }>('/api/v2/data-quality/scans', authFetch, json('POST', { source_id: sourceId || null })),
}
