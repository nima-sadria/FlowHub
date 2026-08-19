/**
 * Pricing Matrix â€” pure presentation  validation helpers for the read-only
 * surfaces (UI Stage 2). No React, no fetch: unit-testable logic only.
 *
 * Everything here is driven by the callable contract (FRONTEND_CONTRACT.md) and
 * its "Claude UI Phase 1 Decisions" (PM-1 â€¦ PM-7). Unknown enum values and
 * malformed shapes fail closed via {@link ContractMismatchError} rather than
 * being coerced into a healthy/valid state.
 */

import { ApiError } from '../../api/client'
import type { BadgeVariant } from '../../components/Badge'
import type { IconName } from '../../components/Icon'
import type {
  ChannelPolicyHead,
  ChannelStatus,
  ExactInteger,
  LifecycleEvent,
  LifecycleEventKind,
  PolicyRevision,
  PolicyRuleView,
  PolicySummary,
  RateMode,
  RoundMode,
  RoundOrder,
  UnitDeclaration,
  UnitScope,
  UnitStatus,
} from './types'

// ---------------------------------------------------------------------------
// Exact integer formatting (PM-4)
// ---------------------------------------------------------------------------

/**
 * Render an {@link ExactInteger} as text without any arithmetic. String inputs
 * are returned verbatim (BigInt-safe). Number inputs are stringified as-is;
 * note that a JSON number already beyond `Number.MAX_SAFE_INTEGER` lost
 * precision at parse time — that limitation is upstream and is resolved by the
 * future response string-normalization noted in PM-4.
 */
export function formatExactInteger(value: ExactInteger | null | undefined): string {
  if (value === null || value === undefined) return ''
  return typeof value === 'string' ? value : String(value)
}

// ---------------------------------------------------------------------------
// Fail-closed enum guards
// ---------------------------------------------------------------------------

const CHANNEL_STATUSES: readonly ChannelStatus[] = ['active', 'inactive']
const EVENT_KINDS: readonly LifecycleEventKind[] = ['activate', 'deactivate']
const RATE_MODES: readonly RateMode[] = ['percent_bp', 'multiplier_ppm']
const ROUND_MODES: readonly RoundMode[] = ['floor', 'ceil', 'nearest']
const ROUND_ORDERS: readonly RoundOrder[] = ['round_then_surcharge', 'surcharge_then_round']
const UNIT_STATUSES: readonly UnitStatus[] = ['unresolved', 'resolved']
const UNIT_SCOPES: readonly UnitScope[] = ['global', 'source', 'channel']

const inSet = <T extends string>(set: readonly T[], v: unknown): v is T =>
  typeof v === 'string' && (set as readonly string[]).includes(v)

export const isChannelStatus = (v: unknown): v is ChannelStatus => inSet(CHANNEL_STATUSES, v)
export const isLifecycleEventKind = (v: unknown): v is LifecycleEventKind => inSet(EVENT_KINDS, v)
export const isRateMode = (v: unknown): v is RateMode => inSet(RATE_MODES, v)
export const isRoundMode = (v: unknown): v is RoundMode => inSet(ROUND_MODES, v)
export const isRoundOrder = (v: unknown): v is RoundOrder => inSet(ROUND_ORDERS, v)
export const isUnitStatus = (v: unknown): v is UnitStatus => inSet(UNIT_STATUSES, v)
export const isUnitScope = (v: unknown): v is UnitScope => inSet(UNIT_SCOPES, v)

// ---------------------------------------------------------------------------
// Domain status presentation (label key + Badge variant + icon)
// ---------------------------------------------------------------------------

export interface DomainPresentation {
  readonly variant: BadgeVariant
  readonly labelKey: string
  readonly icon: IconName
}

export function channelStatusPresentation(status: ChannelStatus): DomainPresentation {
  return status === 'active'
    ? { variant: 'success', labelKey: 'pricing:channelStatus.active', icon: 'success' }
    : { variant: 'neutral', labelKey: 'pricing:channelStatus.inactive', icon: 'info' }
}

export function channelPolicyStatePresentation(head: ChannelPolicyHead): DomainPresentation {
  if (!head.policyRevisionId && !head.channelConfigRevisionId && !head.effectiveActivationId) {
    return { variant: 'warning', labelKey: 'pricing:channels.head.policyState.noActive', icon: 'warning' }
  }
  if (head.status === 'inactive') {
    return { variant: 'neutral', labelKey: 'pricing:channels.head.policyState.configured', icon: 'info' }
  }
  if (!head.policyRevisionId || !head.effectiveActivationId) {
    return { variant: 'warning', labelKey: 'pricing:channels.head.policyState.staleOrInvalid', icon: 'warning' }
  }
  return { variant: 'success', labelKey: 'pricing:channels.head.policyState.active', icon: 'success' }
}

export function unitStatusPresentation(status: UnitStatus): DomainPresentation {
  return status === 'resolved'
    ? { variant: 'success', labelKey: 'pricing:unitStatus.resolved', icon: 'success' }
    : { variant: 'warning', labelKey: 'pricing:unitStatus.unresolved', icon: 'warning' }
}

export function lifecycleEventPresentation(kind: LifecycleEventKind): DomainPresentation {
  return kind === 'activate'
    ? { variant: 'success', labelKey: 'pricing:eventKind.activate', icon: 'success' }
    : { variant: 'neutral', labelKey: 'pricing:eventKind.deactivate', icon: 'info' }
}

export const rateModeLabelKey = (mode: RateMode): string => `pricing:rateMode.${mode}`
export const roundModeLabelKey = (mode: RoundMode): string => `pricing:roundMode.${mode}`
export const roundOrderLabelKey = (order: RoundOrder): string => `pricing:roundOrder.${order}`

// ---------------------------------------------------------------------------
// Derive channel identities (strictly from pricing-matrix data)
// ---------------------------------------------------------------------------

/** Distinct, order-preserving channel IDs referenced by a policy's rules. */
export function derivePolicyChannelIds(policy: PolicyRevision): string[] {
  const seen = new Set<string>()
  const ids: string[] = []
  for (const rule of policy.rules) {
    if (typeof rule.channelId === 'string' && rule.channelId && !seen.has(rule.channelId)) {
      seen.add(rule.channelId)
      ids.push(rule.channelId)
    }
  }
  return ids
}

// ---------------------------------------------------------------------------
// Contract-mismatch (fail closed)
// ---------------------------------------------------------------------------

export class ContractMismatchError extends Error {
  constructor(public readonly detail: string) {
    super(`pricing_contract_mismatch: ${detail}`)
    this.name = 'ContractMismatchError'
  }
}

const isRecord = (v: unknown): v is Record<string, unknown> =>
  typeof v === 'object' && v !== null && !Array.isArray(v)

const mismatch = (detail: string): never => {
  throw new ContractMismatchError(detail)
}

const requireString = (v: unknown, field: string): string =>
  typeof v === 'string' && v.length > 0 ? v : mismatch(`missing_or_invalid:${field}`)

const optionalString = (v: unknown): string => (typeof v === 'string' ? v : '')
const nullableString = (v: unknown): string | null => (typeof v === 'string' ? v : null)
const optionalNumber = (v: unknown): number => (typeof v === 'number' && Number.isFinite(v) ? v : 0)
const exactOr = (v: unknown): ExactInteger =>
  typeof v === 'string' || typeof v === 'number' ? v : '0'

// ---------------------------------------------------------------------------
// Runtime validators — return typed values or fail closed
// ---------------------------------------------------------------------------

export function validatePolicySummary(value: unknown): PolicySummary {
  if (!isRecord(value)) return mismatch('policy_summary_not_object')
  if (!isRoundOrder(value.roundOrder)) return mismatch(`policy.roundOrder:${String(value.roundOrder)}`)
  return {
    id: requireString(value.id, 'policy.id'),
    policyId: requireString(value.policyId, 'policy.policyId'),
    revisionNumber: optionalNumber(value.revisionNumber),
    name: requireString(value.name, 'policy.name'),
    computationCurrency: requireString(value.computationCurrency, 'policy.computationCurrency'),
    basisStrategy: optionalString(value.basisStrategy),
    roundOrder: value.roundOrder,
    maxQuoteAgeDays: optionalNumber(value.maxQuoteAgeDays),
    minQuoteCount: optionalNumber(value.minQuoteCount),
    evaluationTimezone: optionalString(value.evaluationTimezone),
    arithmeticVersion: optionalString(value.arithmeticVersion),
    unitRegistryVersion: optionalString(value.unitRegistryVersion),
    checksum: optionalString(value.checksum),
    createdAt: optionalString(value.createdAt),
  }
}

export function validatePolicyRuleView(value: unknown): PolicyRuleView {
  if (!isRecord(value)) return mismatch('rule_not_object')
  if (!isRateMode(value.rateMode)) return mismatch(`rule.rateMode:${String(value.rateMode)}`)
  if (!isRoundMode(value.roundMode)) return mismatch(`rule.roundMode:${String(value.roundMode)}`)
  return {
    channelId: requireString(value.channelId, 'rule.channelId'),
    productRef: nullableString(value.productRef),
    productGroupRevisionId: nullableString(value.productGroupRevisionId),
    rateMode: value.rateMode,
    rateValue: exactOr(value.rateValue),
    fixedAddendMinor: exactOr(value.fixedAddendMinor),
    roundMode: value.roundMode,
    roundStepMinor: exactOr(value.roundStepMinor),
    surchargeMinor: exactOr(value.surchargeMinor),
    guards: isRecord(value.guards) ? value.guards : {},
  }
}

export function validatePolicyRevision(value: unknown): PolicyRevision {
  const summary = validatePolicySummary(value)
  const rawRules = (value as Record<string, unknown>).rules
  if (!Array.isArray(rawRules)) return mismatch('policy.rules_not_array')
  return { ...summary, rules: rawRules.map(validatePolicyRuleView) }
}

export function validateChannelHead(value: unknown): ChannelPolicyHead {
  if (!isRecord(value)) return mismatch('head_not_object')
  if (!isChannelStatus(value.status)) return mismatch(`head.status:${String(value.status)}`)
  return {
    channelId: requireString(value.channelId, 'head.channelId'),
    headVersion: exactOr(value.headVersion),
    currentEventId: nullableString(value.currentEventId),
    effectiveActivationId: nullableString(value.effectiveActivationId),
    status: value.status,
    policyRevisionId: nullableString(value.policyRevisionId),
    channelConfigRevisionId: nullableString(value.channelConfigRevisionId),
    updatedAt: optionalString(value.updatedAt),
  }
}

export function validateLifecycleEvent(value: unknown): LifecycleEvent {
  if (!isRecord(value)) return mismatch('event_not_object')
  if (!isLifecycleEventKind(value.eventKind)) return mismatch(`event.eventKind:${String(value.eventKind)}`)
  return {
    id: requireString(value.id, 'event.id'),
    channelId: requireString(value.channelId, 'event.channelId'),
    eventKind: value.eventKind,
    predecessorEventId: nullableString(value.predecessorEventId),
    effectiveActivationId: nullableString(value.effectiveActivationId),
    policyRevisionId: nullableString(value.policyRevisionId),
    channelConfigRevisionId: nullableString(value.channelConfigRevisionId),
    supersedesActivationId: nullableString(value.supersedesActivationId),
    actorUserId: nullableString(value.actorUserId),
    reason: nullableString(value.reason),
    occurredAt: optionalString(value.occurredAt),
  }
}

export function validateUnitDeclaration(value: unknown): UnitDeclaration {
  if (!isRecord(value)) return mismatch('unit_not_object')
  if (!isUnitScope(value.scope)) return mismatch(`unit.scope:${String(value.scope)}`)
  const scopeReference = requireString(value.scopeReference, 'unit.scopeReference')
  if (value.status === 'unresolved') {
    return { scope: value.scope, scopeReference, status: 'unresolved', currency: null, unit: null }
  }
  // UI Stage 6 browser evidence: the real backend's resolved response omits
  // `status` entirely (only the unresolved example in FRONTEND_CONTRACT.md
  // carries `status: "unresolved"`). Detect "resolved" by the absence of the
  // unresolved marker rather than requiring a literal `status: "resolved"`
  // the backend never sends. An explicit, unrecognized status still fails
  // closed as a contract mismatch.
  if (value.status !== undefined && !isUnitStatus(value.status)) {
    return mismatch(`unit.status:${String(value.status)}`)
  }
  const resolved = {
    scope: value.scope,
    scopeReference,
    status: 'resolved' as const,
    canonicalCurrency: optionalString(value.canonicalCurrency),
    canonicalUnit: optionalString(value.canonicalUnit),
    canonicalFactor: formatExactInteger(value.canonicalFactor as ExactInteger | null | undefined),
    currencyProfileId: optionalString(value.currencyProfileId),
    // `version` is an ExactInteger on the wire (observed as a JSON number in
    // the real response), not always a string — format it the same way as
    // other exact identifiers instead of silently discarding a number.
    version: formatExactInteger(value.version as ExactInteger | null | undefined),
    ...(typeof value.channelConfigRevisionId === 'string'
      ? { channelConfigRevisionId: value.channelConfigRevisionId }
      : {}),
  }
  return resolved
}

// ---------------------------------------------------------------------------
// Error classification → read-only load states
// ---------------------------------------------------------------------------

export type PricingErrorKind =
  | 'unauthenticated'
  | 'permission_denied'
  | 'not_found'
  | 'stale_state'
  | 'validation_error'
  | 'contract_mismatch'
  | 'unavailable'

export interface PricingErrorState {
  readonly kind: PricingErrorKind
  readonly status?: number
  readonly detail?: string
}

/**
 * Map any thrown error into a distinct state. Auth (401/403), a missing
 * reference (404), an unexpected lifecycle/head conflict (409 — never
 * silently retried), request validation (422), contract mismatches, and
 * transport failures are never collapsed into a single "error".
 */
export function classifyPricingError(error: unknown): PricingErrorState {
  if (error instanceof ContractMismatchError) return { kind: 'contract_mismatch', detail: error.detail }
  if (error instanceof ApiError) {
    if (error.status === 401) return { kind: 'unauthenticated', status: 401 }
    if (error.status === 403) return { kind: 'permission_denied', status: 403 }
    if (error.status === 404) return { kind: 'not_found', status: 404, detail: error.code }
    if (error.status === 409) return { kind: 'stale_state', status: 409, detail: error.code }
    if (error.status === 422) return { kind: 'validation_error', status: 422, detail: error.code }
    return { kind: 'unavailable', status: error.status, detail: error.code }
  }
  return { kind: 'unavailable' }
}

/** Centralized label/tone mapping for every {@link PricingErrorKind} — one place to change copy or tone. */
export interface PricingErrorPresentation {
  readonly testId: string
  readonly variant: 'warning' | 'error'
  readonly titleKey: string
  readonly messageKey: string
  /** Whether a generic "retry the same request" action makes sense for this kind. */
  readonly retryable: boolean
}

export const PRICING_ERROR_PRESENTATION: Record<PricingErrorKind, PricingErrorPresentation> = {
  unauthenticated: { testId: 'pricing-unauthenticated', variant: 'warning', titleKey: 'pricing:state.unauthenticated.title', messageKey: 'pricing:state.unauthenticated.message', retryable: false },
  permission_denied: { testId: 'pricing-permission-denied', variant: 'warning', titleKey: 'pricing:state.permissionDenied.title', messageKey: 'pricing:state.permissionDenied.message', retryable: false },
  not_found: { testId: 'pricing-not-found', variant: 'warning', titleKey: 'pricing:state.notFound.title', messageKey: 'pricing:state.notFound.message', retryable: false },
  stale_state: { testId: 'pricing-stale-state', variant: 'warning', titleKey: 'pricing:state.staleState.title', messageKey: 'pricing:state.staleState.message', retryable: false },
  validation_error: { testId: 'pricing-validation-error', variant: 'warning', titleKey: 'pricing:state.validationError.title', messageKey: 'pricing:state.validationError.message', retryable: false },
  contract_mismatch: { testId: 'pricing-contract-mismatch', variant: 'error', titleKey: 'pricing:state.contractMismatch.title', messageKey: 'pricing:state.contractMismatch.message', retryable: false },
  unavailable: { testId: 'pricing-unavailable', variant: 'error', titleKey: 'pricing:state.unavailable.title', messageKey: 'pricing:state.unavailable.message', retryable: true },
}