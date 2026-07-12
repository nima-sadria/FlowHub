import { apiFetch } from '../../api/client'
import { authFetch } from '../../api/authFetch'
import type { UnifiedWorkspaceService } from './UnifiedWorkspaceService'
import type {
  ApplyResource,
  DraftChangeInput,
  DraftRevisionResource,
  ReviewResource,
  UnifiedWorkspaceResource,
  WorkspaceGridPage,
  WorkspacePreferences,
} from './types'

function json(method: 'POST' | 'PUT', body: unknown, headers?: Record<string, string>): RequestInit {
  return { method, headers: { 'Content-Type': 'application/json', ...headers }, body: JSON.stringify(body) }
}

export class ApiUnifiedWorkspaceService implements UnifiedWorkspaceService {
  createManual(name: string, selections: Array<{ connector_id: string; product_id: string }>): Promise<UnifiedWorkspaceResource> {
    return apiFetch('/api/v2/unified-workspaces/manual', authFetch, json('POST', { name, selections }))
  }

  getWorkspace(id: string): Promise<UnifiedWorkspaceResource> {
    return apiFetch(`/api/v2/unified-workspaces/${encodeURIComponent(id)}`, authFetch)
  }

  getGrid(id: string, page: number, pageSize: number, search?: string): Promise<WorkspaceGridPage> {
    const params = new URLSearchParams({ page: String(page), pageSize: String(pageSize), sort: 'name:asc' })
    if (search) params.set('search', search)
    return apiFetch(`/api/v2/unified-workspaces/${encodeURIComponent(id)}/grid?${params}`, authFetch)
  }

  saveDraft(id: string, expectedVersion: number, changes: DraftChangeInput[]): Promise<DraftRevisionResource> {
    return apiFetch(`/api/v2/unified-workspaces/${encodeURIComponent(id)}/draft/revisions`, authFetch, json('POST', { expected_version: expectedVersion, changes, metadata: { client: 'handsontable', action: 'save_draft' } }))
  }

  createReview(id: string, revisionId: string): Promise<ReviewResource> {
    return apiFetch(`/api/v2/unified-workspaces/${encodeURIComponent(id)}/reviews`, authFetch, json('POST', { draft_revision_id: revisionId }))
  }

  async saveSelection(id: string, reviewId: string, itemIds: string[]): Promise<void> {
    await apiFetch(`/api/v2/unified-workspaces/${encodeURIComponent(id)}/reviews/${encodeURIComponent(reviewId)}/selection`, authFetch, json('PUT', { review_item_ids: itemIds }))
  }

  applySelected(id: string, reviewId: string, idempotencyKey: string): Promise<ApplyResource> {
    return apiFetch(`/api/v2/unified-workspaces/${encodeURIComponent(id)}/apply`, authFetch, json('POST', { review_id: reviewId, confirmed: true }, { 'Idempotency-Key': idempotencyKey }))
  }

  getPreferences(): Promise<WorkspacePreferences> {
    return apiFetch('/api/v2/unified-workspaces/preferences/me', authFetch)
  }

  savePreferences(preferences: WorkspacePreferences): Promise<WorkspacePreferences> {
    return apiFetch('/api/v2/unified-workspaces/preferences/me', authFetch, json('PUT', { expected_version: preferences.version, visibleChannelIds: preferences.visibleChannelIds, channelOrder: preferences.channelOrder, visibleFields: preferences.visibleFields, displayNameSource: preferences.displayNameSource }))
  }
}
