import i18n, { translate } from './index'

const statusAliases: Record<string, string> = {
  draft_saved: 'draftSaved',
  in_progress: 'inProgress',
  not_configured: 'notConfigured',
  read_only: 'readOnly',
  reconciliation_required: 'reconciliationRequired',
  stale_review: 'staleReview',
  unable_to_check: 'unableToCheck',
}

export function formatRole(value: string | null | undefined): string {
  if (!value) return '-'
  const normalized = value.trim().replace(/[-_]+(.)/g, (_, character: string) => character.toUpperCase())
  const key = `common:role.${normalized}`
  return i18n.exists(key) ? translate(key) : value
}

export function formatStatus(value: string | null | undefined): string {
  if (!value) return translate('common:status.unknown')
  const normalized = value.trim().toLowerCase().replace(/[\s-]+/g, '_')
  const key = `common:status.${statusAliases[normalized] ?? normalized}`
  if (i18n.exists(key)) return translate(key)
  return value.replace(/[_-]+/g, ' ').replace(/\b\w/g, character => character.toUpperCase())
}

export function formatField(value: string): string {
  const key = `common:field.${value.toLowerCase()}`
  return i18n.exists(key) ? translate(key) : value
}
