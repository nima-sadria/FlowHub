import type { WorkspaceState, WorkspacePreview } from '../types'

export interface WorkspaceService {
  getState(): Promise<WorkspaceState>
  startPreview(sourceId: string): Promise<WorkspacePreview>
  cancelPreview(previewId: string): Promise<void>
}
