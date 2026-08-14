import i18n, { translate } from './index'

function locale(): string {
  return i18n.resolvedLanguage ?? i18n.language ?? 'en'
}

export function formatNumber(value: number, options?: Intl.NumberFormatOptions): string {
  return new Intl.NumberFormat(locale(), options).format(value)
}

export function formatPercent(value: number, options?: Intl.NumberFormatOptions): string {
  return formatNumber(value, { style: 'percent', ...options })
}

export function formatDateTime(value: Date | string | number, options?: Intl.DateTimeFormatOptions): string {
  const date = value instanceof Date ? value : new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  return new Intl.DateTimeFormat(locale(), { dateStyle: 'medium', timeStyle: 'short', ...options }).format(date)
}

export function formatDate(value: Date | string | number, options?: Intl.DateTimeFormatOptions): string {
  const date = value instanceof Date ? value : new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  return new Intl.DateTimeFormat(locale(), { dateStyle: 'medium', ...options }).format(date)
}

export function formatRelativeTime(value: Date | string | number, now = Date.now()): string {
  const date = value instanceof Date ? value : new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  const seconds = Math.round((date.getTime() - now) / 1000)
  const formatter = new Intl.RelativeTimeFormat(locale(), { numeric: 'auto' })
  if (Math.abs(seconds) < 60) return formatter.format(seconds, 'second')
  const minutes = Math.round(seconds / 60)
  if (Math.abs(minutes) < 60) return formatter.format(minutes, 'minute')
  const hours = Math.round(minutes / 60)
  if (Math.abs(hours) < 24) return formatter.format(hours, 'hour')
  return formatter.format(Math.round(hours / 24), 'day')
}

export function formatPrice(value: number, currency: string, unit?: string): string {
  if (currency === 'IRT' || unit === 'TOMAN') return translate('common:units.tomanAmount', { value: formatNumber(value) })
  try { return new Intl.NumberFormat(locale(), { style: 'currency', currency }).format(value) }
  catch { return `${formatNumber(value)} ${currency}` }
}

/**
 * Canonical short currency label. `IRT` is a real FlowHub currency choice
 * (see settings:settings.currencyOption.IRT) but is not ISO 4217, so Intl
 * cannot resolve a symbol for it — translate it explicitly rather than
 * leaking the raw code. Every other code goes through Intl so the label
 * stays truthful to the persisted currency (never inferred/converted).
 */
export function formatCurrencyLabel(currency: string): string {
  const normalized = currency.trim().toUpperCase()
  if (normalized === 'IRT') return translate('settings:settings.toman')
  try {
    const parts = new Intl.NumberFormat(locale(), { style: 'currency', currency: normalized, currencyDisplay: 'symbol' }).formatToParts(1)
    return parts.find(part => part.type === 'currency')?.value ?? normalized
  } catch {
    return normalized
  }
}
