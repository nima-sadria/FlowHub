import i18n, { translate } from '../../i18n'

const KNOWN_CHANNEL_TYPES = ['woocommerce', 'snappshop', 'tapsishop', 'digikala', 'technolife', 'magento', 'shopify']

const SYSTEM_CHANNEL_NAME_ALIASES: Record<string, ReadonlySet<string>> = {
  woocommerce: new Set(['woocommerce', 'ووکامرس']),
  snappshop: new Set(['snappshop', 'snapp shop', 'اسنپ شاپ']),
  tapsishop: new Set(['tapsishop', 'tapsi shop', 'تپ‌سی شاپ']),
  digikala: new Set(['digikala', 'دیجی‌کالا']),
  technolife: new Set(['technolife', 'تکنولایف']),
  shopify: new Set(['shopify', 'شاپیفای']),
}

/** Locale-aware label for a known connector/channel type, or null for anything else. */
function channelTypeLabel(type: string): string | null {
  if (!KNOWN_CHANNEL_TYPES.includes(type)) return null
  const key = `common:channelType.${type}`
  return i18n.exists(key) ? translate(key) : null
}

function humanize(value: string): string {
  return value
    .replace(/[_-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/\b\w/g, character => character.toUpperCase())
}

function isSystemChannelName(type: string, value: string): boolean {
  return SYSTEM_CHANNEL_NAME_ALIASES[type]?.has(value.trim().toLocaleLowerCase()) ?? false
}

export interface ChannelDisplayMetadata {
  displayName?: string | null
  displayNameCustom?: boolean
  instanceLabel?: string | null
  showInstance?: boolean
}

/** Convert an internal channel identity into a stable, readable UI label. */
export function formatChannelDisplayName(
  channelId: string,
  metadata: ChannelDisplayMetadata = {},
): string {
  const [rawType, ...rawInstanceParts] = channelId.split(':')
  const type = rawType.trim().toLowerCase()
  const base = channelTypeLabel(type) ?? (humanize(rawType) || translate('common:labels.channel'))
  const instance = metadata.instanceLabel?.trim() || humanize(rawInstanceParts.join(':'))
  const configured = metadata.displayName?.trim()
  if (configured && (metadata.displayNameCustom || !isSystemChannelName(type, configured))) {
    if (metadata.showInstance && instance && !configured.toLowerCase().includes(instance.toLowerCase())) {
      return `${configured} — ${instance}`
    }
    return configured
  }
  if (!instance || (!metadata.showInstance && ['primary', 'main'].includes(instance.toLowerCase()))) return base
  return `${base} — ${instance}`
}

/**
 * Locale-aware display name for a known connector/channel id, falling back to
 * the given name verbatim for anything else (e.g. Source types, whose curated
 * names like "ERP / API Import" must not be re-humanized from the raw id).
 */
export function localizedChannelName(
  channelId: string,
  fallbackName: string,
  displayNameCustom = false,
): string {
  const [rawType] = channelId.split(':')
  if (!KNOWN_CHANNEL_TYPES.includes(rawType.trim().toLowerCase())) return fallbackName
  return formatChannelDisplayName(channelId, {
    displayName: fallbackName,
    displayNameCustom,
  })
}
