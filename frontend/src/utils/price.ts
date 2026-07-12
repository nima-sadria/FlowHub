export type MoneyValue = number | bigint | string | null | undefined

export interface MoneyFormatOptions {
  currency?: string | null
  unit?: string | null
  position?: 'prefix' | 'suffix'
  empty?: string
}

const MONEY_TEXT = /^([+-]?)(\d+)(?:\.(\d+))?$/

/** Format money without converting integer strings through floating point. */
export function formatMoney(value: MoneyValue, options: MoneyFormatOptions = {}): string {
  const numeric = normalizeMoneyText(value)
  if (numeric === null) return options.empty ?? '-'
  const match = MONEY_TEXT.exec(numeric)
  if (!match) return options.empty ?? '-'
  const [, sign, integer, fraction] = match
  const grouped = `${sign}${integer.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}${fraction ? `.${fraction}` : ''}`
  const label = String(options.unit ?? options.currency ?? '').trim()
  if (!label) return grouped
  return options.position === 'prefix' ? `${label} ${grouped}` : `${grouped} ${label}`
}

/** Normalize a human-formatted integer for API submission. */
export function normalizeMoneyInteger(value: MoneyValue): string | null {
  if (value === null || value === undefined) return null
  if (typeof value === 'bigint') return value.toString()
  if (typeof value === 'number') {
    return Number.isSafeInteger(value) ? String(value) : null
  }
  const normalized = normalizeDigits(value).trim().replace(/,/g, '')
  if (!/^[+-]?\d+$/.test(normalized)) return null
  const negative = normalized.startsWith('-')
  const digits = normalized.replace(/^[+-]/, '').replace(/^0+(?=\d)/, '') || '0'
  return `${negative ? '-' : ''}${digits}`
}

export function parseMoneyInput(value: string): number | null {
  const normalized = normalizeMoneyInteger(value)
  if (normalized === null) return null
  const parsed = Number(normalized)
  return Number.isSafeInteger(parsed) ? parsed : null
}

export function formatMoneyInput(value: MoneyValue): string {
  const normalized = normalizeMoneyInteger(value)
  return normalized === null ? '' : formatMoney(normalized, { empty: '' })
}

/** Backward-compatible price formatter used by legacy tools. */
export function fmtPrice(p: string | null | undefined): string {
  return formatMoney(p)
}

function normalizeMoneyText(value: MoneyValue): string | null {
  if (value === null || value === undefined || value === '') return null
  if (typeof value === 'bigint') return value.toString()
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) return null
    return String(value)
  }
  const normalized = normalizeDigits(value).trim().replace(/,/g, '')
  return MONEY_TEXT.test(normalized) ? normalized : null
}

function normalizeDigits(value: string): string {
  return value
    .replace(/[\u06F0-\u06F9]/g, digit => String(digit.charCodeAt(0) - 0x06F0))
    .replace(/[\u0660-\u0669]/g, digit => String(digit.charCodeAt(0) - 0x0660))
}

/** Round per emergency price formula:
 *  price <= 20,000,000 -> nearest 10,000; price > 20,000,000 -> nearest 50,000 */
export function emergencyRound(price: number): number {
  const unit = price > 20_000_000 ? 50_000 : 10_000
  return Math.round(price / unit) * unit
}

/** Compute new price from an emergency operation + value, then round. */
export function applyEmergencyOp(
  oldPrice: number,
  operation: 'pct_increase' | 'pct_decrease' | 'fixed_increase' | 'fixed_decrease',
  value: number,
): number {
  let raw: number
  switch (operation) {
    case 'pct_increase':  raw = oldPrice * (1 + value / 100); break
    case 'pct_decrease':  raw = oldPrice * (1 - value / 100); break
    case 'fixed_increase': raw = oldPrice + value; break
    case 'fixed_decrease': raw = oldPrice - value; break
    default: raw = oldPrice
  }
  return raw <= 0 ? 0 : emergencyRound(raw)
}
