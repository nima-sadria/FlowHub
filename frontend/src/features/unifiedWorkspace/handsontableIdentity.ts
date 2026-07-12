import type Handsontable from 'handsontable'

export interface StableGridIdentity {
  listingId: string
}

export function sanitizeGridHtml(html: string): string {
  const text = new DOMParser().parseFromString(html, 'text/html').body.textContent ?? ''
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;')
}

export function sourceRecordAtVisualRow(
  hot: Handsontable | null | undefined,
  visualRow: number,
): StableGridIdentity | null {
  if (!hot) return null
  const physicalRow = hot.toPhysicalRow(visualRow)
  if (physicalRow === null || physicalRow < 0) return null
  const record = hot.getSourceDataAtRow(physicalRow) as Partial<StableGridIdentity> | undefined
  return typeof record?.listingId === 'string' && record.listingId
    ? { listingId: record.listingId }
    : null
}
