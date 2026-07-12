import { describe, expect, it } from 'vitest'
import { formatMoney, formatMoneyInput, normalizeMoneyInteger, parseMoneyInput } from './price'

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
