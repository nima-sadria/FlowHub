import { beforeEach, describe, expect, it } from 'vitest'
import { changeLocale } from '../../i18n'
import {
  canonicalStateLabel,
  deriveOverallDiagnosticState,
  diagnosticEvidenceDescription,
  diagnosticRecommendedAction,
  diagnosticStatePresentation,
  isEventDrivenScheduleMode,
  observationConfidenceDescription,
  observationConfidencePresentation,
  reconciliationPresentation,
  resolveDiagnosticState,
} from './diagnosticPresentation'

describe('diagnostic presentation semantics', () => {
  beforeEach(async () => { await changeLocale('en') })

  it('preserves all explicit states, including Coming Soon', () => {
    expect([
      'HEALTHY',
      'INFO',
      'COMING_SOON',
      'NOT_CHECKED',
      'NOT_APPLICABLE',
      'DISABLED',
      'WARNING',
      'ERROR',
    ].map(resolveDiagnosticState)).toEqual([
      'HEALTHY',
      'INFO',
      'COMING_SOON',
      'NOT_CHECKED',
      'NOT_APPLICABLE',
      'DISABLED',
      'WARNING',
      'ERROR',
    ])
  })

  it('presents Coming Soon as a non-actionable planned state', () => {
    expect(diagnosticStatePresentation('Coming Soon')).toMatchObject({
      state: 'COMING_SOON',
      label: 'Coming Soon',
      variant: 'neutral',
    })
    expect(diagnosticRecommendedAction({ state: 'COMING_SOON', is_actionable: false })).toBe('No action required')
  })

  it('fails closed for the legacy attempted-check failure label while preserving unknown evidence', () => {
    expect(resolveDiagnosticState('Unable to check')).toBe('ERROR')
    expect(resolveDiagnosticState('fail')).toBe('ERROR')
    expect(resolveDiagnosticState('warn')).toBe('WARNING')
    expect(resolveDiagnosticState('pass')).toBe('HEALTHY')
    expect(resolveDiagnosticState('skip')).toBe('NOT_CHECKED')
    expect(resolveDiagnosticState('unknown')).toBe('NOT_CHECKED')
    expect(diagnosticStatePresentation('unknown')).toMatchObject({
      state: 'NOT_CHECKED',
      label: 'Not checked yet',
      variant: 'neutral',
    })
  })

  it('does not let optional or intentionally disabled checks lower overall health', () => {
    expect(deriveOverallDiagnosticState([
      { state: 'HEALTHY' },
      { state: 'NOT_APPLICABLE' },
      { state: 'DISABLED' },
      { state: 'INFO' },
      { state: 'WARNING', is_actionable: false },
    ], { required: [{ state: 'HEALTHY' }] })).toBe('HEALTHY')
  })

  it('does not call missing required evidence healthy or warning', () => {
    expect(deriveOverallDiagnosticState([
      { state: 'HEALTHY' },
      { state: 'NOT_CHECKED' },
    ])).toBe('NOT_CHECKED')
  })

  it('counts verified healthy evidence even when no action is required', () => {
    expect(deriveOverallDiagnosticState([
      { state: 'HEALTHY', is_actionable: false },
      { state: 'HEALTHY', is_actionable: false },
    ])).toBe('HEALTHY')
  })

  it('gives verified actionable states priority', () => {
    expect(deriveOverallDiagnosticState([{ state: 'NOT_CHECKED' }, { state: 'WARNING' }])).toBe('WARNING')
    expect(deriveOverallDiagnosticState([{ state: 'WARNING' }, { state: 'ERROR' }])).toBe('ERROR')
    expect(deriveOverallDiagnosticState([{ state: 'HEALTHY' }], { disabled: true })).toBe('DISABLED')
  })

  it('translates reason and action codes while retaining safe prose fallback', () => {
    const evidence = {
      state: 'NOT_CHECKED',
      reason_code: 'credentials_not_checked',
      recommended_action: 'run_connection_test',
      is_actionable: true,
    }
    expect(diagnosticEvidenceDescription(evidence)).toBe('No credential verification has been recorded.')
    expect(diagnosticRecommendedAction(evidence)).toBe('Run connection test')
  })

  it('renders stale evidence with its exact age and configured freshness threshold', () => {
    const checkedAt = new Date(Date.now() - (4 * 24 * 60 * 60 * 1000)).toISOString()
    expect(diagnosticEvidenceDescription({
      state: 'WARNING',
      reason_code: 'product_sync_stale',
      checked_at: checkedAt,
      freshness_threshold_hours: 24,
    })).toBe('Last successful product sync was 4 days ago. Expected freshness: within 24 hours.')
  })

  it('localizes every canonical schedule mode, including the composed one', () => {
    expect(canonicalStateLabel('SCHEDULED')).toBe('Scheduled')
    expect(canonicalStateLabel('EVENT_DRIVEN')).toBe('Event driven')
    expect(canonicalStateLabel('EVENT_DRIVEN_WITH_RECONCILIATION')).toBe('Event driven with reconciliation')
    expect(canonicalStateLabel('NOT_SCHEDULED')).toBe('Not scheduled')
  })

  it('localizes the new pending background-job state', () => {
    expect(canonicalStateLabel('PENDING')).toBe('Pending work')
    expect(canonicalStateLabel('IDLE')).toBe('Idle')
  })

  it('recognizes both event-driven schedule modes', () => {
    expect(isEventDrivenScheduleMode('EVENT_DRIVEN')).toBe(true)
    expect(isEventDrivenScheduleMode('EVENT_DRIVEN_WITH_RECONCILIATION')).toBe(true)
    expect(isEventDrivenScheduleMode('SCHEDULED')).toBe(false)
    expect(isEventDrivenScheduleMode('NOT_SCHEDULED')).toBe(false)
    expect(isEventDrivenScheduleMode(undefined)).toBe(false)
  })

  it('presents reconciliation as its own fact with a timestamp only when scheduled', () => {
    const at = '2026-08-18T10:00:00Z'
    expect(reconciliationPresentation({ mode: 'SCHEDULED', nextReconciliationAt: at })).toEqual({
      mode: 'SCHEDULED', label: 'Scheduled', nextReconciliationAt: at,
    })
    expect(reconciliationPresentation({ mode: 'MANUAL', nextReconciliationAt: null })).toEqual({
      mode: 'MANUAL', label: 'Manual', nextReconciliationAt: null,
    })
    expect(reconciliationPresentation({ mode: 'DISABLED', nextReconciliationAt: null })).toEqual({
      mode: 'DISABLED', label: 'Disabled', nextReconciliationAt: null,
    })
  })

  it('defaults a missing reconciliation fact to disabled rather than inventing a schedule', () => {
    expect(reconciliationPresentation(undefined)).toEqual({
      mode: 'DISABLED', label: 'Disabled', nextReconciliationAt: null,
    })
  })
})

describe('observation confidence presentation (distinct axis from freshness)', () => {
  beforeEach(async () => { await changeLocale('en') })

  it('presents CONFIRMED and LIKELY_FRESH both as the plain owner concept "Up to date"', () => {
    expect(observationConfidencePresentation({ value: 'CONFIRMED' })).toMatchObject({
      value: 'CONFIRMED', label: 'Up to date', variant: 'success', state: 'HEALTHY',
    })
    expect(observationConfidencePresentation({ value: 'LIKELY_FRESH' })).toMatchObject({
      value: 'LIKELY_FRESH', label: 'Up to date', variant: 'success', state: 'HEALTHY',
    })
  })

  it('presents STALE as "Delayed" with a warning variant', () => {
    expect(observationConfidencePresentation({ value: 'STALE' })).toMatchObject({
      value: 'STALE', label: 'Delayed', variant: 'warning', state: 'WARNING',
    })
  })

  it('presents UNKNOWN as "Needs verification", never the raw enum', () => {
    expect(observationConfidencePresentation({ value: 'UNKNOWN' })).toMatchObject({
      value: 'UNKNOWN', label: 'Needs verification', variant: 'neutral', state: 'NOT_CHECKED',
    })
  })

  it('presents RECOVERY_REQUIRED as an actionable error, the most severe owner concept', () => {
    expect(observationConfidencePresentation({ value: 'RECOVERY_REQUIRED' })).toMatchObject({
      value: 'RECOVERY_REQUIRED', label: 'Recovery required', variant: 'error', state: 'ERROR',
    })
  })

  it('falls back to UNKNOWN for an unrecognized or missing value rather than throwing', () => {
    expect(observationConfidencePresentation(undefined)).toMatchObject({ value: 'UNKNOWN' })
    expect(observationConfidencePresentation({ value: 'SOMETHING_NEW' })).toMatchObject({ value: 'UNKNOWN' })
  })

  it('accepts a bare string, matching the other presentation helpers', () => {
    expect(observationConfidencePresentation('STALE')).toMatchObject({ value: 'STALE', label: 'Delayed' })
  })

  it('describes RECOVERY_REQUIRED with the affected product count when known', () => {
    expect(observationConfidenceDescription({ value: 'RECOVERY_REQUIRED', recoveryRequiredCount: 3 })).toBe(
      'FlowHub tried and failed to confirm current prices for 3 product(s). Manual review is recommended.',
    )
  })

  it('describes RECOVERY_REQUIRED generically when no count is known', () => {
    expect(observationConfidenceDescription({ value: 'RECOVERY_REQUIRED', recoveryRequiredCount: 0 })).toBe(
      'FlowHub tried and failed to confirm current prices for some products. Manual review is recommended.',
    )
  })

  it('describes every value in plain language without PostgreSQL/queue/lease terminology', () => {
    expect(observationConfidenceDescription({ value: 'CONFIRMED' })).toBe('Prices were confirmed by a live, targeted read.')
    expect(observationConfidenceDescription({ value: 'STALE' })).toBe(
      'The last confirmed read is older than the expected freshness window.',
    )
    for (const description of [
      observationConfidenceDescription({ value: 'CONFIRMED' }),
      observationConfidenceDescription({ value: 'LIKELY_FRESH' }),
      observationConfidenceDescription({ value: 'STALE' }),
      observationConfidenceDescription({ value: 'UNKNOWN' }),
      observationConfidenceDescription({ value: 'RECOVERY_REQUIRED', recoveryRequiredCount: 1 }),
    ]) {
      expect(description.toLowerCase()).not.toMatch(/postgres|lease|queue|skip locked|dl_channel_entity_work/)
    }
  })
})
