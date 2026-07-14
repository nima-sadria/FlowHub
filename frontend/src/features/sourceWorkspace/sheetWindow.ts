export interface SheetWindow {
  start: number
  end: number
}

export function sheetWindow(
  totalRows: number,
  scrollTop: number,
  viewportHeight: number,
  rowHeight: number,
  overscan: number,
): SheetWindow {
  if (totalRows <= 0 || rowHeight <= 0 || viewportHeight <= 0) return { start: 0, end: 0 }
  const start = Math.max(0, Math.floor(Math.max(scrollTop, 0) / rowHeight) - Math.max(overscan, 0))
  const end = Math.min(totalRows, Math.ceil((Math.max(scrollTop, 0) + viewportHeight) / rowHeight) + Math.max(overscan, 0))
  return { start, end }
}
