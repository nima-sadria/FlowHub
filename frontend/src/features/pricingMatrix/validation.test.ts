import { describe, it, expect } from 'vitest'
import {
  findDuplicateMemberIndices,
  findDuplicateRuleScopeIndices,
  isSupportedCurrencyUnitPair,
  isValidExactIntegerInput,
  validateRuleTarget,
} from './validation'

describe('isValidExactIntegerInput', () => {
  it('accepts plain digit strings and zero', () => {
    expect(isValidExactIntegerInput('0')).toBe(true)
    expect(isValidExactIntegerInput('1000')).toBe(true)
  })
  it('rejects a large safe-but-huge value only on format, preserving it as text (PM-4)', () => {
    expect(isValidExactIntegerInput('9007199254740993000')).toBe(true)
  })
  it('rejects leading zeros, decimals, and non-digits', () => {
    expect(isValidExactIntegerInput('01')).toBe(false)
    expect(isValidExactIntegerInput('1.5')).toBe(false)
    expect(isValidExactIntegerInput('abc')).toBe(false)
    expect(isValidExactIntegerInput('')).toBe(false)
  })
  it('rejects a negative value unless explicitly allowed', () => {
    expect(isValidExactIntegerInput('-5')).toBe(false)
    expect(isValidExactIntegerInput('-5', { allowNegative: true })).toBe(true)
  })
})

describe('isSupportedCurrencyUnitPair (no magnitude inference)', () => {
  it('supports IRR only with an explicit RIAL or TOMAN choice', () => {
    expect(isSupportedCurrencyUnitPair('IRR', 'RIAL')).toBe(true)
    expect(isSupportedCurrencyUnitPair('IRR', 'TOMAN')).toBe(true)
    expect(isSupportedCurrencyUnitPair('IRR', '')).toBe(false)
    expect(isSupportedCurrencyUnitPair('IRR', 'USD')).toBe(false)
  })
  it('supports the documented non-IRR pairs and rejects mismatches', () => {
    expect(isSupportedCurrencyUnitPair('USD', 'USD')).toBe(true)
    expect(isSupportedCurrencyUnitPair('EUR', 'EUR')).toBe(true)
    expect(isSupportedCurrencyUnitPair('AED', 'AED')).toBe(true)
    expect(isSupportedCurrencyUnitPair('JPY', 'JPY')).toBe(true)
  })
  it('rejects an unsupported currency/unit pair', () => {
    expect(isSupportedCurrencyUnitPair('GBP', 'GBP')).toBe(false)
    expect(isSupportedCurrencyUnitPair('USD', 'EUR')).toBe(false)
  })
})

describe('validateRuleTarget', () => {
  it('allows product_ref alone', () => {
    expect(validateRuleTarget({ product_ref: 'p1', product_group_revision_id: null })).toBeNull()
  })
  it('allows product_group_revision_id alone', () => {
    expect(validateRuleTarget({ product_ref: null, product_group_revision_id: 'g1' })).toBeNull()
  })
  it('allows neither (channel default)', () => {
    expect(validateRuleTarget({ product_ref: null, product_group_revision_id: null })).toBeNull()
  })
  it('rejects both set at once', () => {
    expect(validateRuleTarget({ product_ref: 'p1', product_group_revision_id: 'g1' })).toBe('both_targets_set')
  })
})

describe('findDuplicateRuleScopeIndices', () => {
  it('flags a repeated (channel, target) scope', () => {
    const rules = [
      { channel_id: 'c1', product_ref: 'p1', product_group_revision_id: null },
      { channel_id: 'c1', product_ref: 'p2', product_group_revision_id: null },
      { channel_id: 'c1', product_ref: 'p1', product_group_revision_id: null },
    ]
    expect(findDuplicateRuleScopeIndices(rules)).toEqual([2])
  })
  it('does not confuse a channel-default rule with a targeted one', () => {
    const rules = [
      { channel_id: 'c1', product_ref: null, product_group_revision_id: null },
      { channel_id: 'c1', product_ref: 'p1', product_group_revision_id: null },
    ]
    expect(findDuplicateRuleScopeIndices(rules)).toEqual([])
  })
})

describe('findDuplicateMemberIndices', () => {
  it('flags a repeated non-empty member and ignores blanks', () => {
    expect(findDuplicateMemberIndices(['a', '', 'b', 'a'])).toEqual([3])
  })
})
