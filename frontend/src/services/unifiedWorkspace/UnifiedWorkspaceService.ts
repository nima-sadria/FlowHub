import type {
  ApplyResource,
  DraftChangeInput,
  DraftRevisionResource,
  ReviewResource,
  ReviewSelectionResource,
  UnifiedWorkspaceResource,
  WorkspaceGridPage,
  WorkspacePreferences,
  WorkspaceGridQuery,
} from './types'

export interface UnifiedWorkspaceService {
  createManual(name: string, selections: Array<{ connector_id: string; product_id: string }>): Promise<UnifiedWorkspaceResource>
  getWorkspace(id: string): Promise<UnifiedWorkspaceResource>
  getGrid(id: string, page: number, pageSize: number, query?: WorkspaceGridQuery): Promise<WorkspaceGridPage>
  saveDraft(id: string, version: number, changes: DraftChangeInput[]): Promise<DraftRevisionResource>
  createReview(id: string, revisionId: string): Promise<ReviewResource>
  saveSelection(id: string, reviewId: string, itemIds: string[]): Promise<ReviewSelectionResource>
  applySelected(id: string, reviewId: string, selectionChecksum: string, idempotencyKey: string): Promise<ApplyResource>
  getPreferences(): Promise<WorkspacePreferences>
  savePreferences(preferences: WorkspacePreferences): Promise<WorkspacePreferences>
}
