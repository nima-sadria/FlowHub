const CHANNEL_TYPE_LABELS: Record<string, string> = {
  woocommerce: 'WooCommerce',
  snappshop: 'SnappShop',
  tapsishop: 'TapsiShop',
  shopify: 'Shopify',
}

function humanize(value: string): string {
  return value
    .replace(/[_-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/\b\w/g, character => character.toUpperCase())
}

export interface ChannelDisplayMetadata {
  displayName?: string | null
  instanceLabel?: string | null
}

/** Convert an internal channel identity into a stable, readable UI label. */
export function formatChannelDisplayName(
  channelId: string,
  metadata: ChannelDisplayMetadata = {},
): string {
  const configured = metadata.displayName?.trim()
  if (configured) return configured

  const [rawType, ...rawInstanceParts] = channelId.split(':')
  const type = rawType.trim().toLowerCase()
  const base = CHANNEL_TYPE_LABELS[type] ?? (humanize(rawType) || translate('common:labels.channel'))
  const instance = metadata.instanceLabel?.trim() || humanize(rawInstanceParts.join(':'))
  if (!instance || ['primary', 'main'].includes(instance.toLowerCase())) return base
  return `${base} — ${instance}`
}
import { translate } from '../../i18n'
