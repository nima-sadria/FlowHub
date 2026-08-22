/**
 * Pricing Matrix — client-side validation for the editable configuration
 * surfaces (UI Stage 3). Pure logic, no React. Mirrors documented contract
 * constraints only (docs/development/contracts/FRONTEND_CONTRACT.md); never invents a rule the backend
 * does not state. Server-side domain validation (422) remains authoritative —
 * these checks exist to give fast feedback and cannot replace it.
 */

import type { PolicyRuleInput } from './types'

/** Integer string per docs/development/contracts/FRONTEND_CONTRACT.md (`-?(0|[1-9][0-9]*)`), PM-4 safe. */
const EXACT_INTEGER_PATTERN = /^-?(0|[1-9][0-9]*)$/

export function isValidExactIntegerInput(value: string, { allowNegative = false }: { allowNegative?: boolean } = {}): boolean {
  if (!EXACT_INTEGER_PATTERN.test(value)) return false
  if (!allowNegative && value.startsWith('-')) return false
  return true
}

/** Supported non-IRR currency/unit pairs, verbatim from docs/development/contracts/FRONTEND_CONTRACT.md. */
export const SUPPORTED_NON_IRR_PAIRS: ReadonlyArray<{ currency: string; unit: string }> = [
  { currency: 'USD', unit: 'USD' },
  { currency: 'EUR', unit: 'EUR' },
  { currency: 'AED', unit: 'AED' },
  { currency: 'JPY', unit: 'JPY' },
]

export const IRR_UNITS = ['RIAL', 'TOMAN'] as const
export type IrrUnit = typeof IRR_UNITS[number]

export const SUPPORTED_CURRENCIES = ['IRR', ...SUPPORTED_NON_IRR_PAIRS.map(pair => pair.currency)] as const

/**
 * Whether a currency/unit pair is one FlowHub currently supports. For IRR the
 * unit must be an EXPLICIT choice of RIAL or TOMAN — this never infers a unit,
 * it only validates that the user's explicit choice is one of the two
 * supported units.
 */
export function isSupportedCurrencyUnitPair(currency: string, unit: string): boolean {
  if (currency === 'IRR') return (IRR_UNITS as readonly string[]).includes(unit)
  return SUPPORTED_NON_IRR_PAIRS.some(pair => pair.currency === currency && pair.unit === unit)
}

export type RuleTargetError = 'both_targets_set'

/** A rule may target product_ref XOR product_group_revision_id, never both. */
export function validateRuleTarget(rule: Pick<PolicyRuleInput, 'product_ref' | 'product_group_revision_id'>): RuleTargetError | null {
  if (rule.product_ref && rule.product_group_revision_id) return 'both_targets_set'
  return null
}

/** Scope key used for duplicate detection: (channel_id, product_ref, product_group_revision_id). */
export function ruleScopeKey(rule: Pick<PolicyRuleInput, 'channel_id' | 'product_ref' | 'product_group_revision_id'>): string {
  return JSON.stringify([rule.channel_id, rule.product_ref || null, rule.product_group_revision_id || null])
}

/** Returns the zero-based indices of rules that duplicate an earlier rule's scope. */
export function findDuplicateRuleScopeIndices(rules: readonly Pick<PolicyRuleInput, 'channel_id' | 'product_ref' | 'product_group_revision_id'>[]): number[] {
  const seen = new Set<string>()
  const duplicates: number[] = []
  rules.forEach((rule, index) => {
    const key = ruleScopeKey(rule)
    if (seen.has(key)) duplicates.push(index)
    else seen.add(key)
  })
  return duplicates
}

/** Returns the zero-based indices of canonical_product_ids that repeat an earlier entry. */
export function findDuplicateMemberIndices(ids: readonly string[]): number[] {
  const seen = new Set<string>()
  const duplicates: number[] = []
  ids.forEach((id, index) => {
    const trimmed = id.trim()
    if (!trimmed) return
    if (seen.has(trimmed)) duplicates.push(index)
    else seen.add(trimmed)
  })
  return duplicates
}

export function isNonEmpty(value: string): boolean {
  return value.trim().length > 0
}
