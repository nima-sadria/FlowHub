import { afterEach, describe, expect, it } from 'vitest'
import { changeLocale } from '../../i18n'
import { formatChannelDisplayName } from './channelDisplayName'

describe('formatChannelDisplayName', () => {
  afterEach(async () => { await changeLocale('en') })

  it('uses friendly names for configured channels', () => {
    expect(formatChannelDisplayName('woocommerce:primary')).toBe('WooCommerce')
    expect(formatChannelDisplayName('snappshop:main')).toBe('SnappShop')
  })

  it('localizes known channel brand names for the Persian locale but leaves unknown types alone', async () => {
    await changeLocale('fa')
    expect(formatChannelDisplayName('woocommerce:primary')).toBe('ووکامرس')
    expect(formatChannelDisplayName('snappshop:main')).toBe('اسنپ شاپ')
    expect(formatChannelDisplayName('tapsishop:main')).toBe('تپ‌سی شاپ')
    expect(formatChannelDisplayName('future_market:west_1')).toBe('Future Market — West 1')
    await changeLocale('en')
    expect(formatChannelDisplayName('woocommerce:primary')).toBe('WooCommerce')
  })

  it('keeps multiple instances distinguishable', () => {
    expect(formatChannelDisplayName('woocommerce:store_eu')).toBe('WooCommerce — Store Eu')
    expect(formatChannelDisplayName('snappshop:main', { instanceLabel: 'Tehran' })).toBe('SnappShop — Tehran')
    expect(formatChannelDisplayName('woocommerce:primary', { showInstance: true })).toBe('WooCommerce — Primary')
  })

  it('provides safe readable fallbacks for unknown or incomplete metadata', () => {
    expect(formatChannelDisplayName('future_market:west_1')).toBe('Future Market — West 1')
    expect(formatChannelDisplayName('')).toBe('Channel')
    expect(formatChannelDisplayName('shopify:primary', { displayName: 'Shopify Production' })).toBe('Shopify Production')
  })

  it('treats legacy Persian system defaults as locale labels but preserves Owner custom names', async () => {
    expect(formatChannelDisplayName('woocommerce:primary', { displayName: 'ووکامرس' })).toBe('WooCommerce')
    expect(formatChannelDisplayName('snappshop:main', { displayName: 'اسنپ شاپ' })).toBe('SnappShop')
    expect(formatChannelDisplayName('tapsishop:main', { displayName: 'تپ‌سی شاپ' })).toBe('TapsiShop')
    expect(formatChannelDisplayName('technolife:main', { displayName: 'تکنولایف' })).toBe('Technolife')
    expect(formatChannelDisplayName('snappshop:main', {
      displayName: 'اسنپ شاپ',
      displayNameCustom: true,
    })).toBe('اسنپ شاپ')
    expect(formatChannelDisplayName('snappshop:main', { displayName: 'فروشگاه تهران' })).toBe('فروشگاه تهران')

    await changeLocale('fa')
    expect(formatChannelDisplayName('snappshop:main', { displayName: 'SnappShop' })).toBe('اسنپ شاپ')
    expect(formatChannelDisplayName('snappshop:main', { displayName: 'فروشگاه تهران' })).toBe('فروشگاه تهران')
  })
})
