import i18n, { translate } from '../../i18n'
import { formatDiagnosticMessage } from '../../i18n/display'
import { formatNumber, formatRelativeTime } from '../../i18n/format'
import type { IconName } from '../../components/Icon'
import type { BadgeVariant } from '../../components/Badge'

export const DIAGNOSTIC_STATES = [
  'HEALTHY',
  'INFO',
  'COMING_SOON',
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
  COMING_SOON: { variant: 'neutral', icon: 'info' },
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
  coming_soon: 'COMING_SOON',
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
  // Degraded provider evidence may include a sanitized provider lifecycle
  // status. Keep that concrete evidence visible instead of replacing it with
  // the generic warning translation.
  if (normalize(reasonCode) === 'external_api_degraded' && evidence.message) {
    return formatDiagnosticMessage(evidence.message)
  }
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
  if (state === 'HEALTHY' || state === 'INFO' || state === 'COMING_SOON' || state === 'NOT_APPLICABLE' || state === 'DISABLED') {
    return translate('diagnostics:action.no_action_required')
  }
  if (state === 'NOT_CHECKED') return translate('diagnostics:action.run_connection_test')
  return translate('diagnostics:action.review_diagnostic')
}

export function diagnosticEvidenceCheckedAt(evidence: DiagnosticEvidenceLike): string | null {
  return evidence.checked_at?.trim() || null
}

/**
 * Canonical projection values (schedule modes, freshness, outcomes, runner
 * states, readiness) all localize through the same `diagnostics:canonicalState.*`
 * namespace. The backend owns the value; the frontend only names it.
 */
export function canonicalStateLabel(value: string | null | undefined): string {
  const key = String(value ?? '').trim()
  if (!key) return translate('diagnostics:canonicalState.UNKNOWN')
  return translate(`diagnostics:canonicalState.${key}`)
}

export const EVENT_DRIVEN_SCHEDULE_MODES = ['EVENT_DRIVEN', 'EVENT_DRIVEN_WITH_RECONCILIATION'] as const

export function isEventDrivenScheduleMode(mode: string | null | undefined): boolean {
  return (EVENT_DRIVEN_SCHEDULE_MODES as readonly string[]).includes(String(mode ?? ''))
}

export interface ReconciliationLike {
  mode?: string | null
  nextReconciliationAt?: string | null
}

/**
 * Reconciliation is its own row, not a value squeezed into "Next scheduled".
 * Returns the localized mode label plus the raw timestamp (formatting is the
 * caller's concern, so this stays locale-format agnostic and testable).
 */
export function reconciliationPresentation(
  reconciliation: ReconciliationLike | null | undefined,
): { mode: string; label: string; nextReconciliationAt: string | null } {
  const mode = String(reconciliation?.mode ?? 'DISABLED')
  return {
    mode,
    label: canonicalStateLabel(mode),
    nextReconciliationAt: reconciliation?.nextReconciliationAt?.trim() || null,
  }
}

// -- Observation Confidence ------------------------------------------------
//
// Distinct axis from diagnosticStatePresentation/FreshnessState above --
// "do we currently trust this channel's cached prices" vs. "has any read
// completed recently". See ADR_CHANNEL_READ_ARCHITECTURE.md. Owner-facing
// language stays plain (never the raw enum, never PostgreSQL/queue/lease
// terminology) per the Diagnostics UI contract.

export type ObservationConfidenceValue = 'CONFIRMED' | 'LIKELY_FRESH' | 'STALE' | 'UNKNOWN' | 'RECOVERY_REQUIRED'

export interface ObservationConfidenceLike {
  value?: ObservationConfidenceValue | string | null
  reasonCode?: string | null
  recoveryRequiredCount?: number | null
  computedAt?: string | null
}

const OBSERVATION_CONFIDENCE_PRESENTATION: Record<ObservationConfidenceValue, Omit<DiagnosticStatePresentation, 'state' | 'label'>> = {
  // CONFIRMED and LIKELY_FRESH are both "trustworthy" from an owner's
  // perspective; the resolver-internal distinction (a live targeted read
  // vs. a still-within-TTL channel-scope read) is Advanced Evidence, not a
  // separate owner-facing concept.
  CONFIRMED: { variant: 'success', icon: 'success' },
  LIKELY_FRESH: { variant: 'success', icon: 'success' },
  STALE: { variant: 'warning', icon: 'warning' },
  UNKNOWN: { variant: 'neutral', icon: 'diagnostics' },
  RECOVERY_REQUIRED: { variant: 'error', icon: 'error' },
}

function resolveObservationConfidenceValue(
  evidence: ObservationConfidenceLike | ObservationConfidenceValue | string | null | undefined,
): ObservationConfidenceValue {
  const raw = typeof evidence === 'object' && evidence !== null ? evidence.value : evidence
  const normalized = String(raw ?? '').trim().toUpperCase()
  if (normalized in OBSERVATION_CONFIDENCE_PRESENTATION) {
    return normalized as ObservationConfidenceValue
  }
  return 'UNKNOWN'
}

export function observationConfidencePresentation(
  evidence: ObservationConfidenceLike | ObservationConfidenceValue | string | null | undefined,
): DiagnosticStatePresentation & { value: ObservationConfidenceValue } {
  const value = resolveObservationConfidenceValue(evidence)
  return {
    state: value === 'RECOVERY_REQUIRED' ? 'ERROR' : value === 'STALE' ? 'WARNING' : value === 'UNKNOWN' ? 'NOT_CHECKED' : 'HEALTHY',
    value,
    label: translate(`diagnostics:observationConfidence.${value}`),
    ...OBSERVATION_CONFIDENCE_PRESENTATION[value],
  }
}

export function observationConfidenceDescription(evidence: ObservationConfidenceLike): string {
  const value = resolveObservationConfidenceValue(evidence)
  if (value === 'RECOVERY_REQUIRED' && evidence.recoveryRequiredCount) {
    // `count` is intentionally avoided: i18next reserves it for plural-form
    // selection (typed as a raw number), and this message has no plural
    // variants -- a differently-named, pre-formatted interpolation value
    // avoids fighting that typing for no behavioral benefit.
    return translate('diagnostics:observationConfidenceDescription.RECOVERY_REQUIRED_WITH_COUNT', {
      productCount: formatNumber(evidence.recoveryRequiredCount),
    })
  }
  return translate(`diagnostics:observationConfidenceDescription.${value}`)
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
    return state !== 'INFO' && state !== 'COMING_SOON' && state !== 'NOT_APPLICABLE' && state !== 'DISABLED'
  })
  if (required.length === 0) return 'NOT_CHECKED'
  if (required.every(item => resolveDiagnosticState(item) === 'HEALTHY')) return 'HEALTHY'
  if (required.some(item => resolveDiagnosticState(item) === 'NOT_CHECKED')) return 'NOT_CHECKED'
  return 'INFO'
}
