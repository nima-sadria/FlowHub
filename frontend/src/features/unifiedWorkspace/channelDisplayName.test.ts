import { describe, expect, it } from 'vitest'
import { formatChannelDisplayName } from './channelDisplayName'

describe('formatChannelDisplayName', () => {
  it('uses friendly names for configured channels', () => {
    expect(formatChannelDisplayName('woocommerce:primary')).toBe('WooCommerce')
    expect(formatChannelDisplayName('snappshop:main')).toBe('SnappShop')
  })

  it('keeps multiple instances distinguishable', () => {
    expect(formatChannelDisplayName('woocommerce:store_eu')).toBe('WooCommerce — Store Eu')
    expect(formatChannelDisplayName('snappshop:main', { instanceLabel: 'Tehran' })).toBe('SnappShop — Tehran')
  })

  it('provides safe readable fallbacks for unknown or incomplete metadata', () => {
    expect(formatChannelDisplayName('future_market:west_1')).toBe('Future Market — West 1')
    expect(formatChannelDisplayName('')).toBe('Channel')
    expect(formatChannelDisplayName('shopify:primary', { displayName: 'Shopify Production' })).toBe('Shopify Production')
  })
})
