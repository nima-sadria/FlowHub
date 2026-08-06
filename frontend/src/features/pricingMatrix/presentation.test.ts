import { describe, it, expect } from 'vitest'
import { ApiError } from '../../api/client'
import {
  ContractMismatchError,
  channelStatusPresentation,
  classifyPricingError,
  derivePolicyChannelIds,
  formatExactInteger,
  isChannelStatus,
  isLifecycleEventKind,
  isRateMode,
  isUnitStatus,
  lifecycleEventPresentation,
  unitStatusPresentation,
  validateChannelHead,
  validateLifecycleEvent,
  validatePolicyRevision,
  validatePolicySummary,
  validateUnitDeclaration,
} from './presentation'
import type { PolicyRevision } from './types'

describe('formatExactInteger (PM-4)', () => {
  it('preserves a decimal string beyond JS safe integer range verbatim', () => {
    expect(formatExactInteger('9007199254740993000')).toBe('9007199254740993000')
  })
  it('stringifies a JSON number without arithmetic', () => {
    expect(formatExactInteger(1000)).toBe('1000')
    expect(formatExactInteger(0)).toBe('0')
  })
  it('renders null/undefined as empty text', () => {
    expect(formatExactInteger(null)).toBe('')
    expect(formatExactInteger(undefined)).toBe('')
  })
})

describe('fail-closed enum guards', () => {
  it('accepts documented values and rejects everything else', () => {
    expect(isChannelStatus('active')).toBe(true)
    expect(isChannelStatus('inactive')).toBe(true)
    expect(isChannelStatus('archived')).toBe(false)
    expect(isChannelStatus(undefined)).toBe(false)
    expect(isLifecycleEventKind('activate')).toBe(true)
    expect(isLifecycleEventKind('purge')).toBe(false)
    expect(isRateMode('percent_bp')).toBe(true)
    expect(isRateMode('flat')).toBe(false)
    expect(isUnitStatus('resolved')).toBe(true)
    expect(isUnitStatus('partial')).toBe(false)
  })
})

describe('domain presentation', () => {
  it('maps channel status to distinct variants and label keys', () => {
    expect(channelStatusPresentation('active')).toMatchObject({ variant: 'success', labelKey: 'pricing:channelStatus.active' })
    expect(channelStatusPresentation('inactive')).toMatchObject({ variant: 'neutral', labelKey: 'pricing:channelStatus.inactive' })
  })
  it('flags an unresolved unit as a warning, not a success', () => {
    expect(unitStatusPresentation('unresolved').variant).toBe('warning')
    expect(unitStatusPresentation('resolved').variant).toBe('success')
  })
  it('maps lifecycle event kinds', () => {
    expect(lifecycleEventPresentation('activate').labelKey).toBe('pricing:eventKind.activate')
    expect(lifecycleEventPresentation('deactivate').labelKey).toBe('pricing:eventKind.deactivate')
  })
})

describe('derivePolicyChannelIds', () => {
  it('returns distinct channel ids in first-seen order', () => {
    const policy = {
      rules: [
        { channelId: 'woocommerce:primary' },
        { channelId: 'tapsishop:main' },
        { channelId: 'woocommerce:primary' },
      ],
    } as unknown as PolicyRevision
    expect(derivePolicyChannelIds(policy)).toEqual(['woocommerce:primary', 'tapsishop:main'])
  })
})

describe('classifyPricingError', () => {
  it('keeps configuration, validation, contract, and transport faults distinct', () => {
    expect(classifyPricingError(new ApiError(403, 'no')).kind).toBe('permission_denied')
    expect(classifyPricingError(new ApiError(422, 'bad')).kind).toBe('validation_error')
    expect(classifyPricingError(new ApiError(500, 'down')).kind).toBe('unavailable')
    expect(classifyPricingError(new ContractMismatchError('head.status:weird')).kind).toBe('contract_mismatch')
    expect(classifyPricingError(new Error('network')).kind).toBe('unavailable')
  })
  it('carries the HTTP status for an unavailable transport fault', () => {
    expect(classifyPricingError(new ApiError(503, 'x'))).toMatchObject({ kind: 'unavailable', status: 503 })
  })
})

describe('validators fail closed on unknown shapes and enums', () => {
  it('accepts a well-formed policy summary', () => {
    const summary = validatePolicySummary({
      id: 'rev-1', policyId: 'pol-1', revisionNumber: 1, name: 'Retail EUR',
      computationCurrency: 'EUR', basisStrategy: 'min', roundOrder: 'surcharge_then_round',
      maxQuoteAgeDays: 30, minQuoteCount: 1, evaluationTimezone: 'UTC',
      arithmeticVersion: 'a1', unitRegistryVersion: 'u1', checksum: 'abc', createdAt: '2026-08-05T00:00:00Z',
    })
    expect(summary.roundOrder).toBe('surcharge_then_round')
  })
  it('rejects an unknown roundOrder enum', () => {
    expect(() => validatePolicySummary({ id: 'r', policyId: 'p', name: 'n', computationCurrency: 'EUR', roundOrder: 'sideways' }))
      .toThrow(ContractMismatchError)
  })
  it('rejects a missing id', () => {
    expect(() => validatePolicySummary({ policyId: 'p', name: 'n', computationCurrency: 'EUR', roundOrder: 'floor' as unknown }))
      .toThrow(ContractMismatchError)
  })
  it('validates a policy revision and its rules', () => {
    const revision = validatePolicyRevision({
      id: 'rev-1', policyId: 'pol-1', revisionNumber: 1, name: 'Retail', computationCurrency: 'EUR',
      basisStrategy: 'min', roundOrder: 'surcharge_then_round', maxQuoteAgeDays: 30, minQuoteCount: 1,
      evaluationTimezone: 'UTC', arithmeticVersion: 'a1', unitRegistryVersion: 'u1', checksum: 'abc', createdAt: '2026-08-05T00:00:00Z',
      rules: [{
        channelId: 'woocommerce:primary', productRef: null, productGroupRevisionId: null,
        rateMode: 'percent_bp', rateValue: 1000, fixedAddendMinor: 0, roundMode: 'floor',
        roundStepMinor: 100, surchargeMinor: 0, guards: {},
      }],
    })
    expect(revision.rules).toHaveLength(1)
    expect(revision.rules[0].channelId).toBe('woocommerce:primary')
  })
  it('rejects a rule with an unknown rateMode', () => {
    expect(() => validatePolicyRevision({
      id: 'r', policyId: 'p', name: 'n', computationCurrency: 'EUR', roundOrder: 'floor',
      rules: [{ channelId: 'c', rateMode: 'flat', roundMode: 'floor' }],
    })).toThrow(ContractMismatchError)
  })
  it('validates head nullability for an inactive channel (PM-5)', () => {
    const head = validateChannelHead({
      channelId: 'woocommerce:primary', headVersion: 0, currentEventId: null,
      effectiveActivationId: null, status: 'inactive', policyRevisionId: null,
      channelConfigRevisionId: null, updatedAt: '2026-08-05T00:00:00Z',
    })
    expect(head.status).toBe('inactive')
    expect(head.effectiveActivationId).toBeNull()
  })
  it('rejects a head with an unknown status', () => {
    expect(() => validateChannelHead({ channelId: 'c', headVersion: 1, status: 'paused' }))
      .toThrow(ContractMismatchError)
  })
  it('validates a lifecycle event', () => {
    const event = validateLifecycleEvent({
      id: 'ev-1', channelId: 'c', eventKind: 'activate', predecessorEventId: null,
      effectiveActivationId: 'act-1', policyRevisionId: 'rev-1', channelConfigRevisionId: 'cfg-1',
      supersedesActivationId: null, actorUserId: 'admin', reason: 'go', occurredAt: '2026-08-05T00:00:00Z',
    })
    expect(event.eventKind).toBe('activate')
  })
  it('distinguishes unresolved and resolved unit declarations', () => {
    const unresolved = validateUnitDeclaration({ scope: 'channel', scopeReference: 'c', status: 'unresolved', currency: null, unit: null })
    expect(unresolved).toMatchObject({ status: 'unresolved', currency: null, unit: null })
    const resolved = validateUnitDeclaration({
      scope: 'channel', scopeReference: 'c', status: 'resolved', canonicalCurrency: 'IRR',
      canonicalUnit: 'RIAL', canonicalFactor: '10', currencyProfileId: 'cp-1', version: 'v1',
    })
    expect(resolved).toMatchObject({ status: 'resolved', canonicalCurrency: 'IRR', canonicalUnit: 'RIAL', canonicalFactor: '10' })
  })
  it('treats a resolved response as resolved even without a status field, and formats a numeric version as text (UI Stage 6 browser evidence)', () => {
    // Real backend response observed in browser verification: no `status`
    // key at all, and `version`/`canonicalFactor` as JSON numbers.
    const resolved = validateUnitDeclaration({
      scope: 'channel', scopeReference: 'woocommerce:primary', currency: 'IRR', unit: 'RIAL',
      canonicalCurrency: 'IRR', canonicalUnit: 'RIAL', canonicalFactor: 1,
      currencyProfileId: 'cp-1', version: 1, channelConfigRevisionId: 'cfg-1',
    })
    expect(resolved).toMatchObject({ status: 'resolved', canonicalFactor: '1', version: '1' })
  })
  it('rejects a unit declaration with an unknown status', () => {
    expect(() => validateUnitDeclaration({ scope: 'channel', scopeReference: 'c', status: 'maybe' }))
      .toThrow(ContractMismatchError)
  })
})
