import type { ColumnSettings } from 'handsontable/settings'
import type {
  DraftChangeInput,
  WorkspaceChannelDefinition,
  WorkspaceGridRow,
} from '../../services/unifiedWorkspace/types'

export interface GridRecord extends Record<string, string | number | boolean | null | undefined> {
  rowId: string
  canonicalName: string
  productType: string
  listingLabel: string
  listingId: string
  channelId: string
  sku: string
  mappingState: string
  selected: boolean
}

export interface GridColumnMeta {
  key: string
  channelId?: string
  field?: 'price' | 'stock' | 'status'
  kind: 'identity' | 'current' | 'target' | 'readonly'
}

export interface GridDefinition {
  records: GridRecord[]
  columns: ColumnSettings[]
  nestedHeaders: Array<Array<string | { label: string; colspan: number }>>
  columnMeta: Map<string, GridColumnMeta>
}

const FIELD_LABELS = { price: 'Price', stock: 'Stock', status: 'Status' } as const

export function buildGridDefinition(
  rows: WorkspaceGridRow[],
  channels: WorkspaceChannelDefinition[],
  visibleChannelIds: string[],
): GridDefinition {
  const visible = channels.filter(channel => visibleChannelIds.includes(channel.channelId))
  const records: GridRecord[] = rows.map(row => {
    const record: GridRecord = {
      rowId: row.rowId,
      canonicalName: row.displayName ?? row.canonicalName ?? 'Unresolved product',
      productType: row.productType ?? 'unresolved',
      listingLabel: row.listingLabel ?? 'Unresolved listing',
      listingId: row.listingId ?? '',
      channelId: row.channelId ?? '',
      sku: row.sku ?? '',
      mappingState: row.mappingState ?? 'unresolved',
      selected: false,
    }
    for (const channel of visible) {
      for (const field of Object.keys(FIELD_LABELS) as Array<keyof typeof FIELD_LABELS>) {
        const cell = row.channelId === channel.channelId ? row.fields?.[field] : undefined
        record[key(channel.channelId, field, 'current')] = cell?.current ?? null
        record[key(channel.channelId, field, 'target')] = cell?.target ?? null
        record[key(channel.channelId, field, 'status')] = cell?.status ?? 'unavailable'
      }
      record[key(channel.channelId, 'sku', 'current')] = row.channelId === channel.channelId ? row.sku ?? '' : null
    }
    return record
  })
  const columns: ColumnSettings[] = [
    { data: 'selected', type: 'checkbox', readOnly: false, width: 44 },
    { data: 'canonicalName', readOnly: true, width: 220 },
    { data: 'productType', readOnly: true, width: 90 },
    { data: 'listingLabel', readOnly: true, width: 190 },
    { data: 'mappingState', readOnly: true, width: 100 },
  ]
  const columnMeta = new Map<string, GridColumnMeta>([
    ['selected', { key: 'selected', kind: 'identity' }],
    ['canonicalName', { key: 'canonicalName', kind: 'identity' }],
    ['productType', { key: 'productType', kind: 'identity' }],
    ['listingLabel', { key: 'listingLabel', kind: 'identity' }],
    ['mappingState', { key: 'mappingState', kind: 'identity' }],
  ])
  const secondHeader: string[] = ['Select', 'Product', 'Type', 'Listing', 'Mapping']
  const topHeader: Array<string | { label: string; colspan: number }> = [{ label: 'Canonical Product / Listing', colspan: 5 }]
  for (const channel of visible) {
    topHeader.push({ label: channel.channelId, colspan: 7 })
    for (const field of Object.keys(FIELD_LABELS) as Array<keyof typeof FIELD_LABELS>) {
      const currentKey = key(channel.channelId, field, 'current')
      const targetKey = key(channel.channelId, field, 'target')
      columns.push({ data: currentKey, readOnly: true, width: 100 })
      columns.push({
        data: targetKey,
        readOnly: !canWrite(channel, field),
        type: field === 'price' || field === 'stock' ? 'numeric' : 'text',
        width: 110,
        allowInvalid: false,
      })
      secondHeader.push(`${FIELD_LABELS[field]} Current`, `${FIELD_LABELS[field]} Target`)
      columnMeta.set(currentKey, { key: currentKey, channelId: channel.channelId, field, kind: 'current' })
      columnMeta.set(targetKey, { key: targetKey, channelId: channel.channelId, field, kind: 'target' })
    }
    const skuKey = key(channel.channelId, 'sku', 'current')
    columns.push({ data: skuKey, readOnly: true, width: 120 })
    secondHeader.push('SKU')
    columnMeta.set(skuKey, { key: skuKey, channelId: channel.channelId, kind: 'readonly' })
  }
  return { records, columns, nestedHeaders: [topHeader, secondHeader], columnMeta }
}

export function draftChangeFromEdit(
  row: WorkspaceGridRow,
  meta: GridColumnMeta,
  value: unknown,
  channel: WorkspaceChannelDefinition,
): DraftChangeInput | null {
  if (meta.kind !== 'target' || !meta.channelId || !meta.field || !row.listingId || !row.canonicalProductId) return null
  if (row.channelId !== meta.channelId || row.productType === 'variable' || row.mappingState !== 'resolved') return null
  const target = String(value ?? '').trim()
  if (!target) return null
  return {
    canonical_product_id: row.canonicalProductId,
    listing_id: row.listingId,
    channel_id: meta.channelId,
    field: meta.field,
    target_value: target,
    currency: meta.field === 'price' ? channel.currency : null,
    unit: meta.field === 'price' ? channel.unit : null,
  }
}

export function key(channelId: string, field: string, state: string): string {
  return `${channelId.replace(/[^a-z0-9]/gi, '_')}__${field}__${state}`
}

function canWrite(channel: WorkspaceChannelDefinition, field: keyof typeof FIELD_LABELS): boolean {
  return channel.writeAvailable && {
    price: channel.writePrice,
    stock: channel.writeStock,
    status: channel.writeStatus,
  }[field]
}
