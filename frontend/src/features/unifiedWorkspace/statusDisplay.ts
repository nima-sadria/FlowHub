export type WorkspaceStatusKey =
  | 'unchanged' | 'edited' | 'draft_saved' | 'warning' | 'error' | 'ready'
  | 'applying' | 'applied' | 'failed' | 'read_only' | 'unavailable'
  | 'stale_review' | 'reconciliation_required'

export interface WorkspaceStatusDisplay {
  label: string
  icon: string
  critical: boolean
}
const STATUS_DISPLAY: Record<WorkspaceStatusKey, WorkspaceStatusDisplay> = {
  unchanged: { label: 'Unchanged', icon: '•', critical: false },
  edited: { label: 'Edited', icon: '✎', critical: false },
  draft_saved: { label: 'Draft Saved', icon: '✓', critical: false },
  warning: { label: 'Warning', icon: '!', critical: true },
  error: { label: 'Error', icon: '×', critical: true },
  ready: { label: 'Ready', icon: '✓', critical: false },
  applying: { label: 'Applying', icon: '↻', critical: false },
  applied: { label: 'Applied', icon: '✓', critical: false },
  failed: { label: 'Failed', icon: '×', critical: true },
  read_only: { label: 'Read-only', icon: '🔒', critical: false },
  unavailable: { label: 'Unavailable', icon: '—', critical: true },
  stale_review: { label: 'Stale Review', icon: '⟳', critical: true },
  reconciliation_required: { label: 'Reconciliation Required', icon: '⚠', critical: true },
}

export function describeWorkspaceStatus(value: string): WorkspaceStatusDisplay {
  return STATUS_DISPLAY[value as WorkspaceStatusKey] ?? {
    label: value.replace(/_/g, ' ') || 'Unknown',
    icon: '?',
    critical: true,
  }
}
