import type { WorkspaceSourceBinding, WorkspaceSourceReference, WorkspaceState, WorkspacePreview } from '../types'

export interface WorkspaceService {
  getState(): Promise<WorkspaceState>
  getSourceBinding(): Promise<WorkspaceSourceBinding>
  bindSource(sourceId: string): Promise<WorkspaceSourceReference>
  startPreview(sourceId: string): Promise<WorkspacePreview>
  cancelPreview(previewId: string): Promise<void>
}
