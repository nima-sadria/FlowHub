import { describe, expect, it } from 'vitest'
import { formatMoney, formatMoneyInput, formatPercentageDelta, normalizeMoneyInteger, parseMoneyInput } from './price'

describe('money formatting', () => {
  it.each([
    [1000, '1,000'],
    [25000, '25,000'],
    [1250000, '1,250,000'],
    [987654321, '987,654,321'],
    [0, '0'],
    [-1250000, '-1,250,000'],
    ['900719925474099312345', '900,719,925,474,099,312,345'],
  ])('formats %s with stable thousands separators', (value, expected) => {
    expect(formatMoney(value)).toBe(expected)
  })

  it('handles null and invalid values safely', () => {
    expect(formatMoney(null)).toBe('-')
    expect(formatMoney(undefined)).toBe('-')
    expect(formatMoney('not-money')).toBe('-')
  })

  it('keeps Rial and Toman units explicit', () => {
    expect(formatMoney(1250000, { unit: 'Rial' })).toBe('1,250,000 Rial')
    expect(formatMoney(125000, { unit: 'Toman' })).toBe('125,000 Toman')
  })

  it('parses formatted inputs without floating-point normalization', () => {
    expect(normalizeMoneyInteger('1,250,000')).toBe('1250000')
    expect(normalizeMoneyInteger('۱٬۲۵۰٬۰۰۰'.replace(/٬/g, ','))).toBe('1250000')
    expect(parseMoneyInput('1,250,000')).toBe(1250000)
    expect(parseMoneyInput('1,250.50')).toBeNull()
    expect(formatMoneyInput('001250000')).toBe('1,250,000')
  })
})

describe('percentage delta formatting', () => {
  it('rounds to two decimals and trims trailing zeros', () => {
    expect(formatPercentageDelta('25.00')).toBe('25')
    expect(formatPercentageDelta('-4.9285714285714')).toBe('4.93')
    expect(formatPercentageDelta('0.25')).toBe('0.25')
  })

  it('never shows a misleading 0% for a nonzero magnitude', () => {
    expect(formatPercentageDelta('0.001')).toBe('<0.01')
    expect(formatPercentageDelta('-0.004')).toBe('<0.01')
  })

  it('shows an exact 0 only for a genuine zero delta', () => {
    expect(formatPercentageDelta('0')).toBe('0')
  })

  it('returns null when there is no numeric percentage (comparison from a zero base)', () => {
    expect(formatPercentageDelta(null)).toBeNull()
    expect(formatPercentageDelta(undefined)).toBeNull()
  })
})
