import i18n, { translate } from '../../i18n'
import { formatDiagnosticMessage } from '../../i18n/display'
import { formatNumber, formatRelativeTime } from '../../i18n/format'
import type { IconName } from '../../components/Icon'
import type { BadgeVariant } from '../../components/Badge'

export const DIAGNOSTIC_STATES = [
  'HEALTHY',
  'INFO',
  'NOT_CHECKED',
  'NOT_APPLICABLE',
  'DISABLED',
  'WARNING',
  'ERROR',
] as const

export type DiagnosticState = (typeof DIAGNOSTIC_STATES)[number]

export interface DiagnosticEvidenceLike {
  state?: DiagnosticState | string | null
  status?: string | null
  reason_code?: string | null
  checked_at?: string | null
  evidence_source?: string | null
  is_actionable?: boolean | null
  recommended_action?: string | null
  freshness_threshold_hours?: number | null
  message?: string | null
}

export interface DiagnosticStatePresentation {
  state: DiagnosticState
  label: string
  variant: BadgeVariant
  icon: IconName
}

const PRESENTATION: Record<DiagnosticState, Omit<DiagnosticStatePresentation, 'state' | 'label'>> = {
  HEALTHY: { variant: 'success', icon: 'success' },
  INFO: { variant: 'info', icon: 'info' },
  NOT_CHECKED: { variant: 'neutral', icon: 'diagnostics' },
  NOT_APPLICABLE: { variant: 'neutral', icon: 'info' },
  DISABLED: { variant: 'neutral', icon: 'info' },
  WARNING: { variant: 'warning', icon: 'warning' },
  ERROR: { variant: 'error', icon: 'error' },
}

const LEGACY_STATES: Record<string, DiagnosticState> = {
  active: 'HEALTHY',
  completed: 'HEALTHY',
  connected: 'HEALTHY',
  healthy: 'HEALTHY',
  ok: 'HEALTHY',
  operational: 'HEALTHY',
  pass: 'HEALTHY',
  passed: 'HEALTHY',
  running: 'HEALTHY',
  success: 'HEALTHY',
  info: 'INFO',
  informational: 'INFO',
  pending: 'NOT_CHECKED',
  skip: 'NOT_CHECKED',
  skipped: 'NOT_CHECKED',
  not_checked: 'NOT_CHECKED',
  not_run: 'NOT_CHECKED',
  never_checked: 'NOT_CHECKED',
  unable_to_check: 'ERROR',
  unknown: 'NOT_CHECKED',
  not_applicable: 'NOT_APPLICABLE',
  unsupported: 'NOT_APPLICABLE',
  disabled: 'DISABLED',
  inactive: 'DISABLED',
  degraded: 'WARNING',
  stale: 'WARNING',
  warn: 'WARNING',
  warning: 'WARNING',
  authentication_failed: 'ERROR',
  error: 'ERROR',
  fail: 'ERROR',
  failed: 'ERROR',
  timeout: 'ERROR',
  unhealthy: 'ERROR',
}

function normalize(value: string | null | undefined): string {
  return String(value ?? '')
    .trim()
    .toLocaleLowerCase('en-US')
    .replace(/[.\s/-]+/g, '_')
    .replace(/^_+|_+$/g, '')
}

function translationKey(prefix: 'reason' | 'action', value: string): string {
  return `diagnostics:${prefix}.${normalize(value)}`
}

export function resolveDiagnosticState(
  evidence: DiagnosticEvidenceLike | DiagnosticState | string | null | undefined,
): DiagnosticState {
  const explicit = typeof evidence === 'object' && evidence !== null ? evidence.state : evidence
  const explicitState = String(explicit ?? '').trim().toUpperCase().replace(/[\s-]+/g, '_')
  if ((DIAGNOSTIC_STATES as readonly string[]).includes(explicitState)) {
    return explicitState as DiagnosticState
  }

  const legacy = typeof evidence === 'object' && evidence !== null ? evidence.status : evidence
  return LEGACY_STATES[normalize(legacy)] ?? 'NOT_CHECKED'
}

export function diagnosticStatePresentation(
  evidence: DiagnosticEvidenceLike | DiagnosticState | string | null | undefined,
): DiagnosticStatePresentation {
  const state = resolveDiagnosticState(evidence)
  return {
    state,
    label: translate(`diagnostics:state.${state.toLocaleLowerCase('en-US')}`),
    ...PRESENTATION[state],
  }
}

export function diagnosticEvidenceDescription(evidence: DiagnosticEvidenceLike): string {
  const reasonCode = evidence.reason_code?.trim()
  const staleContextKey: Record<string, string> = {
    product_sync_stale: 'productSync',
    order_sync_stale: 'orderSync',
    polling_stale: 'polling',
  }
  const staleContext = reasonCode ? staleContextKey[normalize(reasonCode)] : undefined
  if (staleContext && evidence.checked_at && evidence.freshness_threshold_hours != null) {
    return translate(`diagnostics:staleContext.${staleContext}`, {
      last: formatRelativeTime(evidence.checked_at),
      hours: formatNumber(evidence.freshness_threshold_hours),
    })
  }
  if (reasonCode) {
    const key = translationKey('reason', reasonCode)
    if (i18n.exists(key)) return translate(key)
  }
  if (evidence.message) return formatDiagnosticMessage(evidence.message)
  const state = resolveDiagnosticState(evidence)
  return translate(`diagnostics:stateDescription.${state.toLocaleLowerCase('en-US')}`)
}

export function diagnosticRecommendedAction(evidence: DiagnosticEvidenceLike): string {
  if (evidence.is_actionable === false) {
    return translate('diagnostics:action.no_action_required')
  }
  const action = evidence.recommended_action?.trim()
  if (action) {
    const key = translationKey('action', action)
    if (i18n.exists(key)) return translate(key)
    return formatDiagnosticMessage(action)
  }
  if (evidence.is_actionable === true) {
    return translate('diagnostics:action.review_diagnostic')
  }
  const state = resolveDiagnosticState(evidence)
  if (state === 'HEALTHY' || state === 'INFO' || state === 'NOT_APPLICABLE' || state === 'DISABLED') {
    return translate('diagnostics:action.no_action_required')
  }
  if (state === 'NOT_CHECKED') return translate('diagnostics:action.run_connection_test')
  return translate('diagnostics:action.review_diagnostic')
}

export function diagnosticEvidenceCheckedAt(evidence: DiagnosticEvidenceLike): string | null {
  return evidence.checked_at?.trim() || null
}

export function deriveOverallDiagnosticState(
  evidence: readonly DiagnosticEvidenceLike[],
  options: { disabled?: boolean; required?: readonly DiagnosticEvidenceLike[] } = {},
): DiagnosticState {
  if (options.disabled) return 'DISABLED'
  const actionableEvidence = evidence.filter(item => item.is_actionable !== false)
  const allStates = actionableEvidence.map(resolveDiagnosticState)
  if (allStates.includes('ERROR')) return 'ERROR'
  if (allStates.includes('WARNING')) return 'WARNING'

  const required = options.required ?? evidence.filter(item => {
    const state = resolveDiagnosticState(item)
    return state !== 'INFO' && state !== 'NOT_APPLICABLE' && state !== 'DISABLED'
  })
  if (required.length === 0) return 'NOT_CHECKED'
  if (required.every(item => resolveDiagnosticState(item) === 'HEALTHY')) return 'HEALTHY'
  if (required.some(item => resolveDiagnosticState(item) === 'NOT_CHECKED')) return 'NOT_CHECKED'
  return 'INFO'
}
