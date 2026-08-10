import { describe, expect, it } from 'vitest'
import {
  isLocalSourceIconPath,
  SOURCE_ICON_ASSETS,
  SOURCE_ICON_FALLBACK,
  sourceIconPath,
} from './sourceIconRegistry'

describe('Source icon registry', () => {
  it('resolves Nextcloud from explicit provider identities', () => {
    expect(sourceIconPath('nextcloud')).toBe(SOURCE_ICON_ASSETS.nextcloud)
    expect(sourceIconPath({ provider: 'nextcloud:primary' })).toBe(SOURCE_ICON_ASSETS.nextcloud)
    expect(sourceIconPath({ sourceType: 'nextcloud_spreadsheet' })).toBe(SOURCE_ICON_ASSETS.nextcloud)
  })

  it('resolves the local OnlyOffice asset from explicit Source metadata', () => {
    expect(sourceIconPath({ provider: 'onlyoffice:primary' })).toBe(SOURCE_ICON_ASSETS.onlyoffice)
    expect(sourceIconPath({ sourceType: 'onlyoffice_spreadsheet' })).toBe(SOURCE_ICON_ASSETS.onlyoffice)
  })

  it('keeps configured marketplace brands distinct', () => {
    expect(sourceIconPath('snappshop:main')).toBe(SOURCE_ICON_ASSETS.snappshop)
    expect(sourceIconPath('snapp-shop:main')).toBe(SOURCE_ICON_ASSETS.snappshop)
    expect(sourceIconPath('tapsishop:main')).toBe(SOURCE_ICON_ASSETS.tapsishop)
    expect(sourceIconPath('tapsi-shop:main')).toBe(SOURCE_ICON_ASSETS.tapsishop)
    expect(sourceIconPath('technolife:main')).toBe(SOURCE_ICON_ASSETS.technolife)
    expect(sourceIconPath('digikala:main')).toBe(SOURCE_ICON_ASSETS.digikala)
  })

  it('resolves WooCommerce from its exact connector_type/channel_id identifiers', () => {
    expect(sourceIconPath('woocommerce:primary')).toBe(SOURCE_ICON_ASSETS.woocommerce)
    expect(sourceIconPath({ provider: 'woocommerce:primary' })).toBe(SOURCE_ICON_ASSETS.woocommerce)
    expect(sourceIconPath('woo-commerce')).toBe(SOURCE_ICON_ASSETS.woocommerce)
    expect(sourceIconPath('woo_commerce')).toBe(SOURCE_ICON_ASSETS.woocommerce)
  })

  it('falls back for recognized channel types with no matching local brand asset', () => {
    // Shopify is a recognized future channel type but static/logos/brands/
    // has no matching file for it; per policy this must fall back rather
    // than invent or hotlink a logo.
    expect(sourceIconPath('shopify:primary')).toBe(SOURCE_ICON_FALLBACK)
    expect(SOURCE_ICON_ASSETS).not.toHaveProperty('shopify')
    // "woo" alone is not a real FlowHub provider/channel identity value
    // (only an unrelated error-message substring check), so it must not
    // resolve to the WooCommerce asset.
    expect(sourceIconPath('woo')).toBe(SOURCE_ICON_FALLBACK)
  })

  it('resolves the newly registered brand set from static/logos/brands', () => {
    expect(sourceIconPath('amazon')).toBe(SOURCE_ICON_ASSETS.amazon)
    expect(sourceIconPath('bale')).toBe(SOURCE_ICON_ASSETS.bale)
    expect(sourceIconPath('digishahr')).toBe(SOURCE_ICON_ASSETS.digishahr)
    expect(sourceIconPath('divar')).toBe(SOURCE_ICON_ASSETS.divar)
    expect(sourceIconPath('emalls')).toBe(SOURCE_ICON_ASSETS.emalls)
    expect(sourceIconPath('flowhub')).toBe(SOURCE_ICON_ASSETS.flowhub)
    expect(sourceIconPath('magento')).toBe(SOURCE_ICON_ASSETS.magento)
    expect(sourceIconPath('noon')).toBe(SOURCE_ICON_ASSETS.noon)
    expect(sourceIconPath('odoo')).toBe(SOURCE_ICON_ASSETS.odoo)
    expect(sourceIconPath('telegram')).toBe(SOURCE_ICON_ASSETS.telegram)
    expect(sourceIconPath('torob')).toBe(SOURCE_ICON_ASSETS.torob)
    expect(sourceIconPath('whatsapp')).toBe(SOURCE_ICON_ASSETS.whatsapp)
    expect(sourceIconPath('zoomit')).toBe(SOURCE_ICON_ASSETS.zoomit)
  })

  it('uses the Microsoft Office asset only for explicit spreadsheet identities', () => {
    expect(sourceIconPath({ sourceType: 'xlsx' })).toBe(SOURCE_ICON_ASSETS.microsoftOffice)
    expect(sourceIconPath({ fileName: 'daily-prices.XLSX' })).toBe(SOURCE_ICON_ASSETS.microsoftOffice)
    expect(sourceIconPath({ sourceType: 'csv' })).toBe(SOURCE_ICON_FALLBACK)
    expect(sourceIconPath({ sourceType: 'imported_sheet' })).toBe(SOURCE_ICON_ASSETS.microsoftOffice)
  })

  it('falls back without deriving a brand from missing or unknown metadata', () => {
    expect(sourceIconPath(undefined)).toBe(SOURCE_ICON_FALLBACK)
    expect(sourceIconPath({ provider: 'future-source' })).toBe(SOURCE_ICON_FALLBACK)
  })

  it('contains only local static asset paths', () => {
    for (const asset of [...Object.values(SOURCE_ICON_ASSETS), SOURCE_ICON_FALLBACK]) {
      expect(isLocalSourceIconPath(asset)).toBe(true)
      expect(asset).not.toMatch(/^https?:/)
    }
  })
})
