import { describe, expect, it } from 'vitest'
import {
  buildDensePricingDefinition,
  cellIsReadOnly,
  cellProp,
  channelColumnKey,
  channelIdFromColumnKey,
  identityForCell,
  type DensePricingColumnMeta,
} from './densePricingGrid'
import type { GroupedListing, GroupedProduct, GroupedWorkspacePage } from './types'

describe('dense pricing grid model', () => {
  it('renders every simple and variation product as a continuously visible record without expansion state', () => {
    const definition = buildDensePricingDefinition(page([
      product('simple-product', 'Simple product', 'simple', [listing('simple-listing', 'woocommerce:primary')]),
      product('variation-product', 'Blue variation', 'variation', [listing('variation-listing', 'woocommerce:primary')]),
    ]), () => null)

    expect(definition.records.map(record => record.productId)).toEqual(['simple-product', 'variation-product'])
    expect(definition.records.map(record => record.productName)).toEqual(['Simple product', 'Blue variation'])
    expect(definition.records.every(record => !('expanded' in record) && !('children' in record))).toBe(true)
  })

  it('creates independent grouped columns and values for every Channel', () => {
    const definition = buildDensePricingDefinition(page([
      product('product-1', 'Cable', 'simple', [
        listing('woo-listing', 'woocommerce:primary', '100', '110'),
        listing('snapp-listing', 'snappshop:main', '200', '220'),
        listing('tapsi-listing', 'tapsishop:main', '300', '330'),
      ]),
    ]), () => null)
    const record = definition.records[0]

    expect(definition.channelIds).toHaveLength(3)
    expect(new Set(definition.channelIds)).toEqual(new Set(['woocommerce:primary', 'snappshop:main', 'tapsishop:main']))
    expect(record[cellProp('woocommerce:primary', 'price', 'target')]).toBe('110')
    expect(record[cellProp('snappshop:main', 'price', 'target')]).toBe('220')
    expect(record[cellProp('tapsishop:main', 'price', 'target')]).toBe('330')
    expect(definition.nestedHeaders[0]).toHaveLength(4)
  })

  it('uses collision-free reversible column keys for punctuation-distinct Channel identities', () => {
    const colonChannel = 'market:primary'
    const slashChannel = 'market/primary'
    const persianChannel = 'کانال:اصلی'
    const definition = buildDensePricingDefinition(page([
      product('product-1', 'Cable', 'simple', [
        listing('colon-listing', colonChannel, '100', '110'),
        listing('slash-listing', slashChannel, '200', '220'),
        listing('persian-listing', persianChannel, '300', '330'),
      ]),
    ]), () => null)
    const record = definition.records[0]
    const channelKeys = [colonChannel, slashChannel, persianChannel].map(channelColumnKey)

    expect(new Set(channelKeys).size).toBe(3)
    expect(channelKeys.map(channelIdFromColumnKey)).toEqual([colonChannel, slashChannel, persianChannel])
    expect(channelIdFromColumnKey('market_primary')).toBeNull()
    expect(cellProp(colonChannel, 'price', 'target')).not.toBe(cellProp(slashChannel, 'price', 'target'))
    expect(record[cellProp(colonChannel, 'price', 'target')]).toBe('110')
    expect(record[cellProp(slashChannel, 'price', 'target')]).toBe('220')
    expect(record[cellProp(persianChannel, 'price', 'target')]).toBe('330')
    expect(identityForCell(record, definition.columnMeta.get(cellProp(colonChannel, 'price', 'target')))?.channelId).toBe(colonChannel)
    expect(identityForCell(record, definition.columnMeta.get(cellProp(slashChannel, 'price', 'target')))?.channelId).toBe(slashChannel)
  })

  it('keeps a valid Price field eligible when only Stock blocks the Listing', () => {
    const mixedListing = listing('mixed-listing', 'woocommerce:primary', '100', '110')
    mixedListing.state = 'blocked'
    mixedListing.fields.stock = {
      ...mixedListing.fields.stock,
      status: 'blocked',
      readOnly: true,
    }
    const definition = buildDensePricingDefinition(page([
      product('product-1', 'Cable', 'simple', [mixedListing]),
    ]), () => null)
    const record = definition.records[0]
    const priceTarget = definition.columnMeta.get(cellProp('woocommerce:primary', 'price', 'target'))!
    const priceSelection = definition.columnMeta.get(cellProp('woocommerce:primary', 'price', 'selected'))!
    const stockTarget = definition.columnMeta.get(cellProp('woocommerce:primary', 'stock', 'target'))!
    const stockSelection = definition.columnMeta.get(cellProp('woocommerce:primary', 'stock', 'selected'))!

    expect(cellIsReadOnly(record, priceTarget)).toBe(false)
    expect(cellIsReadOnly(record, priceSelection)).toBe(false)
    expect(cellIsReadOnly(record, stockTarget)).toBe(true)
    expect(cellIsReadOnly(record, stockSelection)).toBe(true)
  })

  it('keeps all target and selection cells read-only for variable parent grouping rows', () => {
    const definition = buildDensePricingDefinition(page([
      product('variable-parent', 'Variable parent', 'variable', [listing('parent-listing', 'woocommerce:primary', '100', '110')]),
    ]), () => null)
    const record = definition.records[0]
    const target = definition.columnMeta.get(cellProp('woocommerce:primary', 'price', 'target'))!
    const selection = definition.columnMeta.get(cellProp('woocommerce:primary', 'price', 'selected'))!

    expect(cellIsReadOnly(record, target)).toBe(true)
    expect(cellIsReadOnly(record, selection)).toBe(true)
  })

  it('retains distinct immutable Listing identities when one product has multiple marketplace Listings', () => {
    const definition = buildDensePricingDefinition(page([
      product('product-1', 'Cable', 'simple', [
        listing('snapp-white', 'snappshop:main'),
        listing('snapp-black', 'snappshop:main'),
      ]),
    ]), () => null)
    const target = definition.columnMeta.get(cellProp('snappshop:main', 'price', 'target'))!
    const listingMeta = [...definition.columnMeta.values()].find(meta => meta.kind === 'listing' && meta.channelId === 'snappshop:main')!

    expect(definition.records).toHaveLength(2)
    expect(new Set(definition.records.map(record => record.rowKey)).size).toBe(2)
    expect(definition.records.map(record => identityForCell(record, target)?.listingId)).toEqual(['snapp-white', 'snapp-black'])
    expect(definition.records.map(record => record[listingMeta.prop])).toEqual([
      'snapp-white · external-snapp-white',
      'snapp-black · external-snapp-black',
    ])
  })

  it('keeps row bulk-selection identity stable when Listings reorder or a Listing is inserted', () => {
    const original = buildDensePricingDefinition(page([
      product('product-1', 'Cable', 'simple', [
        listing('listing-a', 'snappshop:main'),
        listing('listing-b', 'snappshop:main'),
      ]),
    ]), () => null)
    const reordered = buildDensePricingDefinition(page([
      product('product-1', 'Cable', 'simple', [
        listing('listing-b', 'snappshop:main'),
        listing('listing-a', 'snappshop:main'),
      ]),
    ]), () => null)
    const inserted = buildDensePricingDefinition(page([
      product('product-1', 'Cable', 'simple', [
        listing('listing-new', 'snappshop:main'),
        listing('listing-a', 'snappshop:main'),
        listing('listing-b', 'snappshop:main'),
      ]),
    ]), () => null)
    const target = original.columnMeta.get(cellProp('snappshop:main', 'price', 'target'))!
    const rowKeysByListing = (definition: typeof original) => new Map(definition.records.map(record => [
      identityForCell(record, target)?.listingId,
      record.rowKey,
    ]))
    const originalKeys = rowKeysByListing(original)
    const reorderedKeys = rowKeysByListing(reordered)
    const insertedKeys = rowKeysByListing(inserted)

    expect(reorderedKeys.get('listing-a')).toBe(originalKeys.get('listing-a'))
    expect(reorderedKeys.get('listing-b')).toBe(originalKeys.get('listing-b'))
    expect(insertedKeys.get('listing-a')).toBe(originalKeys.get('listing-a'))
    expect(insertedKeys.get('listing-b')).toBe(originalKeys.get('listing-b'))
    expect(insertedKeys.get('listing-new')).not.toBe(originalKeys.get('listing-a'))
  })

  it('resolves target and selection by stable Product, Listing, Channel, and Field identity', () => {
    const definition = buildDensePricingDefinition(page([
      product('product-1', 'Cable', 'simple', [listing('woo-listing', 'woocommerce:primary')]),
    ]), () => null)
    const record = definition.records[0]
    const target = definition.columnMeta.get(cellProp('woocommerce:primary', 'stock', 'target'))!
    const selection = definition.columnMeta.get(cellProp('woocommerce:primary', 'stock', 'selected'))!

    const expected = {
      productId: 'product-1',
      listingId: 'woo-listing',
      channelId: 'woocommerce:primary',
      field: 'stock',
    }
    expect(identityForCell(record, target)).toEqual(expected)
    expect(identityForCell(record, selection)).toEqual(expected)
    expect(identityForCell(record, definition.columnMeta.get('productName'))).toBeNull()
  })

  it('marks identity, current, and selection columns to be skipped by paste while retaining target columns', () => {
    const definition = buildDensePricingDefinition(page([
      product('product-1', 'Cable', 'simple', [listing('woo-listing', 'woocommerce:primary')]),
    ]), () => null)
    const columnByProp = new Map(definition.columns.map(column => [String(column.data), column]))

    for (const meta of definition.columnMeta.values()) {
      const column = columnByProp.get(meta.prop)
      expect(column, `missing column for ${meta.prop}`).toBeDefined()
      if (meta.kind === 'target') expect(column?.skipColumnOnPaste).not.toBe(true)
      else expect(column?.skipColumnOnPaste).toBe(true)
    }
  })

  it('does not resolve Current cells as editable identities', () => {
    const definition = buildDensePricingDefinition(page([
      product('product-1', 'Cable', 'simple', [listing('woo-listing', 'woocommerce:primary')]),
    ]), () => null)
    const current: DensePricingColumnMeta = definition.columnMeta.get(cellProp('woocommerce:primary', 'price', 'current'))!

    expect(identityForCell(definition.records[0], current)).toBeNull()
    expect(cellIsReadOnly(definition.records[0], current)).toBe(true)
  })
})

function page(items: GroupedProduct[]): GroupedWorkspacePage {
  return {
    items,
    total: items.length,
    page: 1,
    pageSize: 100,
    view: 'all',
    summary: { ready: items.length, blocked: 0, unchanged: 0, selected: 0 },
    draftVersion: 0,
    revisionId: null,
    reviewId: null,
    reviewStatus: null,
    selectionChecksum: null,
  }
}

function product(
  sourceProductId: string,
  name: string,
  productType: GroupedProduct['productType'],
  children: GroupedListing[],
): GroupedProduct {
  return {
    sourceProductId,
    name,
    sourceKey: `key-${sourceProductId}`,
    cost: null,
    category: null,
    brand: null,
    productType,
    mappedChannelCount: new Set(children.map(item => item.channelId)).size,
    listingCount: children.length,
    changedListingCount: children.filter(item => item.changedFields.length > 0).length,
    selectedListingCount: children.filter(item => item.selected).length,
    state: 'ready',
    children,
  }
}

function listing(
  listingId: string,
  channelId: string,
  currentPrice = '100',
  targetPrice = '110',
): GroupedListing {
  return {
    listingId,
    channelId,
    listingLabel: listingId,
    externalId: `external-${listingId}`,
    externalIdType: 'product_id',
    sku: `sku-${listingId}`,
    mappingState: 'resolved',
    cacheFreshness: 'fresh',
    state: 'ready',
    changedFields: ['price'],
    selected: true,
    reviewItemIds: [],
    fields: {
      price: groupedField(currentPrice, targetPrice),
      stock: groupedField('5', '7'),
      status: groupedField('draft', 'publish'),
    },
  }
}

function groupedField(current: string, target: string): GroupedListing['fields']['price'] {
  return {
    current,
    target,
    changed: current !== target,
    readOnly: false,
    status: 'ready',
    currency: 'IRR',
    unit: 'IRR',
  }
}
