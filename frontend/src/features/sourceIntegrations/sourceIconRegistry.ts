// FlowHub's ONE centralized brand/provider/channel icon registry.
//
// Canonical asset source: static/logos/brands/ (mounted at /static/logos/brands/,
// see app/flowhub/app.py). That directory is the sole authoritative local
// source for brand icons — never hotlink, invent, or duplicate a brand logo
// elsewhere. This registry is reused for both Sources and Channels; do not
// create a second brand-icon registry (consumed via BrandIcon/SourceIcon by
// OperationalResourceCard, ChannelDetail, CommerceHub, SourceConfiguration,
// and WorksheetRuleEditor).
//
// Every brand ships both a .png and a .webp in static/logos/brands/. This
// registry resolves to the .webp as the preferred runtime asset; the .png
// stays on disk as the canonical high-quality/fallback source and is not
// referenced here directly.
//
// If a provider has no matching file in static/logos/brands/, it is
// intentionally absent from SOURCE_ICON_ASSETS below so lookups fall through
// to SOURCE_ICON_FALLBACK — never an invented icon or a remote logo.

const BRANDS_DIR = '/static/logos/brands'

export const SOURCE_ICON_FALLBACK = '/static/logos/FlowHub%20Transparent%20WebP%20%20Logo.webp?v=1'

export const SOURCE_ICON_ASSETS = Object.freeze({
  amazon: `${BRANDS_DIR}/amazon.webp`,
  bale: `${BRANDS_DIR}/bale.webp`,
  digikala: `${BRANDS_DIR}/digikala.webp`,
  digishahr: `${BRANDS_DIR}/digishahr.webp`,
  divar: `${BRANDS_DIR}/divar.webp`,
  emalls: `${BRANDS_DIR}/emalls.webp`,
  flowhub: `${BRANDS_DIR}/flowhub.webp`,
  magento: `${BRANDS_DIR}/magento.webp`,
  // Owner decision: Microsoft Office does not need its own brand asset.
  // The Excel mark stands in for the whole spreadsheet/Office identity
  // family. This is icon presentation only — it does not change provider
  // or domain semantics.
  microsoftOffice: `${BRANDS_DIR}/excel.webp`,
  nextcloud: `${BRANDS_DIR}/nextcloud.webp`,
  noon: `${BRANDS_DIR}/noon.webp`,
  odoo: `${BRANDS_DIR}/odoo.webp`,
  onlyoffice: `${BRANDS_DIR}/onlyoffice.webp`,
  snappshop: `${BRANDS_DIR}/snapp-shop.webp`,
  tapsishop: `${BRANDS_DIR}/tapsi-shop.webp`,
  technolife: `${BRANDS_DIR}/technolife.webp`,
  telegram: `${BRANDS_DIR}/telegram.webp`,
  torob: `${BRANDS_DIR}/torob.webp`,
  whatsapp: `${BRANDS_DIR}/whatsapp.webp`,
  woocommerce: `${BRANDS_DIR}/woocommerce.webp`,
  zoomit: `${BRANDS_DIR}/zoomit.webp`,
  // NOTE: "shopify" is a recognized future channel type (see
  // features/unifiedWorkspace/channelDisplayName.ts) with no matching file
  // in static/logos/brands/. Deliberately absent here rather than pointed
  // at an invented asset; sourceIconPath() falls back to
  // SOURCE_ICON_FALLBACK for it today.
})

export interface SourceIconIdentity {
  provider?: string | null
  sourceType?: string | null
  fileName?: string | null
}

export type SourceIconIdentityInput = SourceIconIdentity | string | null | undefined

const SOURCE_ICON_ALIASES: Readonly<Record<string, keyof typeof SOURCE_ICON_ASSETS>> = Object.freeze({
  amazon: 'amazon',
  bale: 'bale',
  digikala: 'digikala',
  digishahr: 'digishahr',
  divar: 'divar',
  emalls: 'emalls',
  excel: 'microsoftOffice',
  flowhub: 'flowhub',
  imported_sheet: 'microsoftOffice',
  magento: 'magento',
  // Compatibility for old identity strings that expected a dedicated
  // "microsoft-office" asset (now normalized to microsoft_office); both
  // resolve to the Excel mark, per Owner decision.
  microsoft_office: 'microsoftOffice',
  nextcloud: 'nextcloud',
  nextcloud_excel: 'nextcloud',
  nextcloud_spreadsheet: 'nextcloud',
  noon: 'noon',
  odoo: 'odoo',
  office: 'microsoftOffice',
  onlyoffice: 'onlyoffice',
  onlyoffice_spreadsheet: 'onlyoffice',
  snapp_shop: 'snappshop',
  snappshop: 'snappshop',
  spreadsheet_import: 'microsoftOffice',
  tapsi_shop: 'tapsishop',
  tapsishop: 'tapsishop',
  technolife: 'technolife',
  telegram: 'telegram',
  torob: 'torob',
  whatsapp: 'whatsapp',
  // "woocommerce" is the exact, exclusively-used connector_type/channel_id
  // identifier throughout app/flowhub (registry.py, gateway.py,
  // settings_routes.py). "woo_commerce" also covers the hyphenated
  // "woo-commerce" spelling, since normalizedIdentity() maps hyphens to
  // underscores before this lookup. A bare "woo" alias was deliberately
  // not added: it only appears as an error-message substring check
  // (security/upstream_errors.py) and an unrelated search-input test
  // fixture, never as a provider/channel identity value. The misspelled
  // "woocomerce"/"woocomercce" asset-filename typos were never found used
  // as a persisted identifier anywhere in the codebase, so no compatibility
  // alias is registered for them.
  woo_commerce: 'woocommerce',
  woocommerce: 'woocommerce',
  xlsx: 'microsoftOffice',
  zoomit: 'zoomit',
})

function normalizedIdentity(value: string | null | undefined): string {
  return (value ?? '')
    .trim()
    .toLocaleLowerCase('en-US')
    .split(':', 1)[0]
    .replace(/[.\s-]+/g, '_')
}

function fileExtension(fileName: string | null | undefined): string {
  const normalized = (fileName ?? '').trim().toLocaleLowerCase('en-US')
  const separator = normalized.lastIndexOf('.')
  return separator >= 0 ? normalized.slice(separator + 1) : ''
}

/**
 * Resolve only explicitly supplied Source/Channel metadata to a local icon.
 * Unknown providers and ambiguous imported Sources intentionally use FlowHub's
 * own mark rather than guessing a brand from a user-editable display name.
 */
export function sourceIconPath(identity: SourceIconIdentityInput): string {
  const candidates = typeof identity === 'string'
    ? [normalizedIdentity(identity)]
    : [
        normalizedIdentity(identity?.provider),
        normalizedIdentity(identity?.sourceType),
        normalizedIdentity(fileExtension(identity?.fileName)),
      ]

  for (const candidate of candidates) {
    const asset = SOURCE_ICON_ALIASES[candidate]
    if (asset) return SOURCE_ICON_ASSETS[asset]
  }
  return SOURCE_ICON_FALLBACK
}

export function isLocalSourceIconPath(value: string): boolean {
  return value.startsWith('/static/logos/') && !value.startsWith('//')
}
