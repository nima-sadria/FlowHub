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
    expect(sourceIconPath('woocommerce:primary')).toBe(SOURCE_ICON_ASSETS.woocommerce)
    expect(sourceIconPath('snappshop:main')).toBe(SOURCE_ICON_ASSETS.snappshop)
    expect(sourceIconPath('tapsishop:main')).toBe(SOURCE_ICON_ASSETS.tapsishop)
    expect(sourceIconPath('digikala:main')).toBe(SOURCE_ICON_ASSETS.digikala)
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
