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
