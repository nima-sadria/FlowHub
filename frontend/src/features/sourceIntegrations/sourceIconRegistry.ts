export const SOURCE_ICON_FALLBACK = '/static/logos/FlowHub%20favicon.png?v=4'

export const SOURCE_ICON_ASSETS = Object.freeze({
  digikala: '/static/win11-icon/brand/DIGIKALA.webp',
  microsoftOffice: '/static/win11-icon/brand/Microsoft%20Office.webp',
  nextcloud: '/static/win11-icon/brand/Nextcloud.webp',
  onlyoffice: '/static/win11-icon/brand/Onlyoffice.webp',
  snappshop: '/static/win11-icon/brand/Snapp%20Shop.webp',
  tapsishop: '/static/win11-icon/brand/Tapsi%20Shop.webp',
  technolife: '/static/win11-icon/brand/Technolife.webp',
  woocommerce: '/static/win11-icon/brand/WooCommerce.webp',
})

export interface SourceIconIdentity {
  provider?: string | null
  sourceType?: string | null
  fileName?: string | null
}

export type SourceIconIdentityInput = SourceIconIdentity | string | null | undefined

const SOURCE_ICON_ALIASES: Readonly<Record<string, keyof typeof SOURCE_ICON_ASSETS>> = Object.freeze({
  digikala: 'digikala',
  excel: 'microsoftOffice',
  imported_sheet: 'microsoftOffice',
  microsoft_office: 'microsoftOffice',
  nextcloud: 'nextcloud',
  nextcloud_excel: 'nextcloud',
  nextcloud_spreadsheet: 'nextcloud',
  office: 'microsoftOffice',
  onlyoffice: 'onlyoffice',
  onlyoffice_spreadsheet: 'onlyoffice',
  snapp_shop: 'snappshop',
  snappshop: 'snappshop',
  spreadsheet_import: 'microsoftOffice',
  tapsi_shop: 'tapsishop',
  tapsishop: 'tapsishop',
  technolife: 'technolife',
  woo_commerce: 'woocommerce',
  woocommerce: 'woocommerce',
  xlsx: 'microsoftOffice',
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
 * Resolve only explicitly supplied Source metadata to a local icon.
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
  return (
    value.startsWith('/static/logos/')
    || value.startsWith('/static/win11-icon/brand/')
  ) && !value.startsWith('//')
}
