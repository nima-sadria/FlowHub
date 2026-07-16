import { beforeEach, describe, expect, it } from 'vitest'
import { changeLocale } from '../../i18n'
import {
  deriveOverallDiagnosticState,
  diagnosticEvidenceDescription,
  diagnosticRecommendedAction,
  diagnosticStatePresentation,
  resolveDiagnosticState,
} from './diagnosticPresentation'

describe('diagnostic presentation semantics', () => {
  beforeEach(async () => { await changeLocale('en') })

  it('preserves all seven explicit states', () => {
    expect([
      'HEALTHY',
      'INFO',
      'NOT_CHECKED',
      'NOT_APPLICABLE',
      'DISABLED',
      'WARNING',
      'ERROR',
    ].map(resolveDiagnosticState)).toEqual([
      'HEALTHY',
      'INFO',
      'NOT_CHECKED',
      'NOT_APPLICABLE',
      'DISABLED',
      'WARNING',
      'ERROR',
    ])
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
})
