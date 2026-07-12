import { describe, expect, it } from 'vitest'
import { buildGridDefinition, draftChangeFromEdit, key } from './gridModel'
import type { WorkspaceChannelDefinition, WorkspaceGridRow } from '../../services/unifiedWorkspace/types'

const CHANNELS: WorkspaceChannelDefinition[] = [
  { channelId: 'woocommerce:primary', readPrice: true, writePrice: true, readStock: true, writeStock: false, readStatus: true, writeStatus: false, supportsMultipleListings: false, maximumBatchSize: 100, rateLimitPerMinute: null, healthState: 'configured', primaryIdentifierType: 'woocommerce_product_id', supportedStatuses: [], currency: 'EUR', unit: 'EUR', writeAvailable: true, version: '1' },
  { channelId: 'snappshop:main', readPrice: true, writePrice: true, readStock: true, writeStock: true, readStatus: true, writeStatus: false, supportsMultipleListings: true, maximumBatchSize: 50, rateLimitPerMinute: null, healthState: 'configured', primaryIdentifierType: 'snappshop_product_number', supportedStatuses: ['active'], currency: 'IRR', unit: 'TOMAN', writeAvailable: true, version: '1' },
]

const ROW: WorkspaceGridRow = {
  rowId: 'row-1', canonicalProductId: 'product-1', canonicalName: 'Product', productType: 'simple',
  listingId: 'listing-1', listingLabel: 'Woo Listing', channelId: 'woocommerce:primary',
  externalPrimaryId: '101', externalIdType: 'product_id', sku: 'SKU', mappingState: 'resolved', mappingVersion: 1,
  fields: {
    price: { current: '100', target: '100', status: 'unchanged', readOnly: false, currency: 'EUR', unit: 'EUR' },
    stock: { current: '5', target: '5', status: 'read_only', readOnly: true, currency: null, unit: null },
    status: { current: 'publish', target: 'publish', status: 'read_only', readOnly: true, currency: null, unit: null },
  },
}

describe('Unified Workspace grid model', () => {
  it('creates dynamic grouped Current/Target columns without collapsing Listing identity', () => {
    const definition = buildGridDefinition([ROW], CHANNELS, CHANNELS.map(item => item.channelId))
    expect(definition.nestedHeaders[0]).toEqual([
      { label: 'Canonical Product / Listing', colspan: 5 },
      { label: 'woocommerce:primary', colspan: 7 },
      { label: 'snappshop:main', colspan: 7 },
    ])
    expect(definition.records[0].listingId).toBe('listing-1')
    expect(definition.records[0][key('woocommerce:primary', 'price', 'current')]).toBe('100')
    expect(definition.records[0][key('snappshop:main', 'price', 'current')]).toBeNull()
  })

  it('creates explicit currency/unit Draft edits only for the row Channel', () => {
    const definition = buildGridDefinition([ROW], CHANNELS, ['woocommerce:primary'])
    const prop = key('woocommerce:primary', 'price', 'target')
    const change = draftChangeFromEdit(ROW, definition.columnMeta.get(prop)!, '125', CHANNELS[0])
    expect(change).toEqual({ canonical_product_id: 'product-1', listing_id: 'listing-1', channel_id: 'woocommerce:primary', field: 'price', target_value: '125', currency: 'EUR', unit: 'EUR' })
  })

  it('never creates edits for variable parents or another Channel', () => {
    const definition = buildGridDefinition([ROW], CHANNELS, CHANNELS.map(item => item.channelId))
    const variable = { ...ROW, productType: 'variable' as const }
    expect(draftChangeFromEdit(variable, definition.columnMeta.get(key('woocommerce:primary', 'price', 'target'))!, '125', CHANNELS[0])).toBeNull()
    expect(draftChangeFromEdit(ROW, definition.columnMeta.get(key('snappshop:main', 'stock', 'target'))!, '5', CHANNELS[1])).toBeNull()
  })
})
