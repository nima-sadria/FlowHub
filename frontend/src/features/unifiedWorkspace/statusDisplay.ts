import { translate } from '../../i18n'

export type WorkspaceStatusKey =
  | 'unchanged' | 'edited' | 'draft_saved' | 'warning' | 'error' | 'ready'
  | 'applying' | 'applied' | 'failed' | 'read_only' | 'unavailable'
  | 'stale_review' | 'reconciliation_required'

export interface WorkspaceStatusDisplay {
  label: string
  icon: string
  critical: boolean
}

const STATUS_DISPLAY: Record<WorkspaceStatusKey, { labelKey: string; icon: string; critical: boolean }> = {
  unchanged: { labelKey: 'workspace:statusDisplay.unchanged', icon: '\u2022', critical: false },
  edited: { labelKey: 'workspace:statusDisplay.edited', icon: '\u270e', critical: false },
  draft_saved: { labelKey: 'workspace:statusDisplay.draftSaved', icon: '\u2713', critical: false },
  warning: { labelKey: 'workspace:statusDisplay.warning', icon: '!', critical: true },
  error: { labelKey: 'workspace:statusDisplay.error', icon: '\u00d7', critical: true },
  ready: { labelKey: 'workspace:statusDisplay.ready', icon: '\u2713', critical: false },
  applying: { labelKey: 'workspace:statusDisplay.applying', icon: '\u21bb', critical: false },
  applied: { labelKey: 'workspace:statusDisplay.applied', icon: '\u2713', critical: false },
  failed: { labelKey: 'workspace:statusDisplay.failed', icon: '\u00d7', critical: true },
  read_only: { labelKey: 'workspace:statusDisplay.readOnly', icon: '\ud83d\udd12', critical: false },
  unavailable: { labelKey: 'workspace:statusDisplay.unavailable', icon: '\u2014', critical: true },
  stale_review: { labelKey: 'workspace:statusDisplay.staleReview', icon: '\u27f3', critical: true },
  reconciliation_required: { labelKey: 'workspace:statusDisplay.reconciliationRequired', icon: '\u26a0', critical: true },
}

export function describeWorkspaceStatus(value: string): WorkspaceStatusDisplay {
  const display = STATUS_DISPLAY[value as WorkspaceStatusKey]
  if (display) return { label: translate(display.labelKey), icon: display.icon, critical: display.critical }
  return {
    label: value.replace(/_/g, ' ') || translate('common:status.unknown'),
    icon: '?',
    critical: true,
  }
}
