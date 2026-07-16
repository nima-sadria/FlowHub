import type { ColumnSettings } from 'handsontable/settings'
import { translate } from '../../i18n'
import { formatField } from '../../i18n/display'
import { formatChannelDisplayName } from '../unifiedWorkspace/channelDisplayName'
import type { GroupedListing, GroupedProduct, GroupedWorkspacePage } from './types'

export type PricingField = 'price' | 'stock' | 'status'

export interface DenseCellIdentity {
  productId: string
  listingId: string
  channelId: string
  field: PricingField
}

export interface DensePricingRecord extends Record<string, string | number | boolean | null | undefined> {
  rowKey: string
  productId: string
  productName: string
  sourceKey: string
  productType: string
}

export interface DensePricingColumnMeta {
  prop: string
  kind: 'identity' | 'listing' | 'current' | 'target' | 'selection'
  channelId?: string
  field?: PricingField
}

export interface DensePricingDefinition {
  records: DensePricingRecord[]
  columns: ColumnSettings[]
  nestedHeaders: Array<Array<string | { label: string; colspan: number }>>
  columnMeta: Map<string, DensePricingColumnMeta>
  channelIds: string[]
}

interface OverlayValue {
  targetValue: string
  selected: boolean
}

const FIELDS: PricingField[] = ['price', 'stock', 'status']

export function buildDensePricingDefinition(
  page: GroupedWorkspacePage,
  overlayFor: (identity: DenseCellIdentity) => OverlayValue | null,
): DensePricingDefinition {
  const channelIds = orderedChannelIds(page.items)
  const records = page.items.flatMap(product => productRecords(product, channelIds, overlayFor))
  const columns: ColumnSettings[] = [
    { data: 'productName', readOnly: true, skipColumnOnPaste: true, width: 220 },
    { data: 'sourceKey', readOnly: true, skipColumnOnPaste: true, width: 125 },
    { data: 'productType', readOnly: true, skipColumnOnPaste: true, width: 92 },
  ]
  const columnMeta = new Map<string, DensePricingColumnMeta>([
    ['productName', { prop: 'productName', kind: 'identity' }],
    ['sourceKey', { prop: 'sourceKey', kind: 'identity' }],
    ['productType', { prop: 'productType', kind: 'identity' }],
  ])
  const topHeader: Array<string | { label: string; colspan: number }> = [
    { label: translate('workspace:densePricing.productIdentity'), colspan: 3 },
  ]
  const secondHeader = [
    translate('workspace:gridModel.product'),
    translate('workspace:densePricing.sourceKey'),
    translate('workspace:gridModel.type'),
  ]

  for (const channelId of channelIds) {
    const listingProp = listingDisplayProp(channelId)
    topHeader.push({ label: formatChannelDisplayName(channelId), colspan: 1 + FIELDS.length * 3 })
    columns.push({ data: listingProp, readOnly: true, skipColumnOnPaste: true, width: 155 })
    secondHeader.push(translate('workspace:gridModel.listing'))
    columnMeta.set(listingProp, { prop: listingProp, kind: 'listing', channelId })
    for (const field of FIELDS) {
      const currentProp = cellProp(channelId, field, 'current')
      const targetProp = cellProp(channelId, field, 'target')
      const selectionProp = cellProp(channelId, field, 'selected')
      columns.push(
        { data: currentProp, readOnly: true, skipColumnOnPaste: true, width: field === 'status' ? 105 : 112 },
        { data: targetProp, type: field === 'status' ? 'text' : 'numeric', width: field === 'status' ? 110 : 118, allowInvalid: false },
        { data: selectionProp, type: 'checkbox', skipColumnOnPaste: true, width: 52 },
      )
      secondHeader.push(
        translate('workspace:gridModel.currentField', { field: formatField(field) }),
        translate('workspace:gridModel.targetField', { field: formatField(field) }),
        translate('workspace:densePricing.selectField', { field: formatField(field) }),
      )
      columnMeta.set(currentProp, { prop: currentProp, kind: 'current', channelId, field })
      columnMeta.set(targetProp, { prop: targetProp, kind: 'target', channelId, field })
      columnMeta.set(selectionProp, { prop: selectionProp, kind: 'selection', channelId, field })
    }
  }

  return { records, columns, nestedHeaders: [topHeader, secondHeader], columnMeta, channelIds }
}

export function identityForCell(
  record: DensePricingRecord | undefined,
  meta: DensePricingColumnMeta | undefined,
): DenseCellIdentity | null {
  if (!record || !meta?.channelId || !meta.field || meta.kind === 'identity' || meta.kind === 'current') return null
  const listingId = String(record[listingMetaProp(meta.channelId)] ?? '')
  if (!listingId) return null
  return {
    productId: record.productId,
    listingId,
    channelId: meta.channelId,
    field: meta.field,
  }
}

export function cellIsReadOnly(record: DensePricingRecord, meta: DensePricingColumnMeta): boolean {
  if (meta.kind === 'identity' || meta.kind === 'current') return true
  if (!meta.channelId || !meta.field) return true
  if (Boolean(record[readOnlyMetaProp(meta.channelId, meta.field)])) return true
  if (meta.kind === 'selection') return !Boolean(record[changedMetaProp(meta.channelId, meta.field)])
  return false
}

export function cellStatus(record: DensePricingRecord, meta: DensePricingColumnMeta): string {
  if (!meta.channelId || !meta.field) return 'unchanged'
  return String(record[statusMetaProp(meta.channelId, meta.field)] ?? 'unavailable')
}

export function cellProp(channelId: string, field: PricingField, suffix: 'current' | 'target' | 'selected'): string {
  return `${channelColumnKey(channelId)}__${field}__${suffix}`
}

/**
 * Handsontable data properties must be safe flat object keys. Encoding every
 * UTF-8 byte keeps the key collision-free (unlike punctuation replacement)
 * while retaining an exact, reversible Channel identity.
 */
export function channelColumnKey(channelId: string): string {
  const encoded = Array.from(new TextEncoder().encode(channelId), byte => byte.toString(16).padStart(2, '0')).join('')
  return `channel_${encoded}`
}

export function channelIdFromColumnKey(key: string): string | null {
  const encoded = key.startsWith('channel_') ? key.slice('channel_'.length) : ''
  if (!key.startsWith('channel_') || encoded.length % 2 !== 0 || !/^[0-9a-f]*$/i.test(encoded)) return null
  const bytes = Uint8Array.from(encoded.match(/.{2}/g)?.map(value => Number.parseInt(value, 16)) ?? [])
  try {
    return new TextDecoder('utf-8', { fatal: true }).decode(bytes)
  } catch {
    return null
  }
}

function productRecords(
  product: GroupedProduct,
  channelIds: string[],
  overlayFor: (identity: DenseCellIdentity) => OverlayValue | null,
): DensePricingRecord[] {
  const byChannel = new Map(channelIds.map(channelId => [
    channelId,
    product.children.filter(listing => listing.channelId === channelId),
  ]))
  const rowCount = Math.max(1, ...[...byChannel.values()].map(listings => listings.length))
  return Array.from({ length: rowCount }, (_, slot) => {
    const continuation = slot > 0
    const rowListings = channelIds.flatMap(channelId => {
      const listing = byChannel.get(channelId)?.[slot]
      return listing ? [{ channelId, listingId: listing.listingId }] : []
    })
    const record: DensePricingRecord = {
      rowKey: denseRowKey(product.sourceProductId, rowListings),
      productId: product.sourceProductId,
      productName: continuation
        ? translate('workspace:densePricing.additionalListing', { product: product.name, number: slot + 1 })
        : product.name,
      sourceKey: product.sourceKey ?? '',
      productType: product.productType,
    }
    for (const channelId of channelIds) {
      writeListing(record, product, byChannel.get(channelId)?.[slot], channelId, overlayFor)
    }
    return record
  })
}

function writeListing(
  record: DensePricingRecord,
  product: GroupedProduct,
  listing: GroupedListing | undefined,
  channelId: string,
  overlayFor: (identity: DenseCellIdentity) => OverlayValue | null,
) {
  record[listingMetaProp(channelId)] = listing?.listingId ?? ''
  record[listingDisplayProp(channelId)] = listing
    ? [listing.listingLabel, listing.externalId].filter(Boolean).join(' · ')
    : ''
  for (const field of FIELDS) {
    const cell = listing?.fields[field]
    const identity = listing ? { productId: product.sourceProductId, listingId: listing.listingId, channelId, field } : null
    const overlay = identity ? overlayFor(identity) : null
    const current = cell?.current ?? null
    const target = overlay?.targetValue ?? cell?.target ?? current
    const changed = Boolean(overlay) || (cell?.changed ?? false)
    const readOnly = !listing || product.productType === 'variable' || Boolean(cell?.readOnly) || cell?.status === 'blocked'
    record[cellProp(channelId, field, 'current')] = current
    record[cellProp(channelId, field, 'target')] = target
    record[cellProp(channelId, field, 'selected')] = overlay?.selected ?? (changed && listing?.selected === true)
    record[readOnlyMetaProp(channelId, field)] = readOnly
    record[changedMetaProp(channelId, field)] = changed
    record[statusMetaProp(channelId, field)] = overlay ? 'edited' : cell?.status ?? 'unavailable'
  }
}

function orderedChannelIds(products: GroupedProduct[]): string[] {
  const result: string[] = []
  for (const product of products) {
    for (const listing of product.children) {
      if (!result.includes(listing.channelId)) result.push(listing.channelId)
    }
  }
  return result.sort((left, right) => formatChannelDisplayName(left).localeCompare(formatChannelDisplayName(right)))
}

function denseRowKey(productId: string, listings: Array<{ channelId: string; listingId: string }>): string {
  const identities = listings
    .map(listing => [listing.channelId, listing.listingId] as const)
    .sort(([leftChannel, leftListing], [rightChannel, rightListing]) => (
      leftChannel.localeCompare(rightChannel) || leftListing.localeCompare(rightListing)
    ))
  return `dense-row:${JSON.stringify([productId, identities])}`
}

function listingMetaProp(channelId: string): string {
  return `${channelColumnKey(channelId)}__listing_id`
}

function listingDisplayProp(channelId: string): string {
  return `${channelColumnKey(channelId)}__listing_display`
}

function readOnlyMetaProp(channelId: string, field: PricingField): string {
  return `${channelColumnKey(channelId)}__${field}__read_only`
}

function changedMetaProp(channelId: string, field: PricingField): string {
  return `${channelColumnKey(channelId)}__${field}__changed`
}

function statusMetaProp(channelId: string, field: PricingField): string {
  return `${channelColumnKey(channelId)}__${field}__status`
}
