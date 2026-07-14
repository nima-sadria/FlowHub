import { useEffect, useMemo, useRef, useState, type ClipboardEvent } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import PageShell from '../components/PageShell'
import Icon from '../components/Icon'
import { useNotification } from '../notifications/NotificationProvider'
import { sourceWorkspaceApi } from '../features/sourceWorkspace/api'
import type { FlowHubSheetPage } from '../features/sourceWorkspace/types'
import { sheetWindow } from '../features/sourceWorkspace/sheetWindow'

const ROW_HEIGHT = 38
const VIEWPORT_HEIGHT = 520
const OVERSCAN = 6

export default function FlowHubSheet() {
  const { sheetId = '' } = useParams()
  const navigate = useNavigate()
  const notify = useNotification()
  const [sheet, setSheet] = useState<FlowHubSheetPage | null>(null)
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [sortColumn, setSortColumn] = useState('')
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('asc')
  const [scrollTop, setScrollTop] = useState(0)
  const [changes, setChanges] = useState<Record<string, string>>({})
  const [columnNames, setColumnNames] = useState<Record<string, string>>({})
  const [selected, setSelected] = useState<{ rowKey: string; columnKey: string } | null>(null)
  const viewport = useRef<HTMLDivElement>(null)

  useEffect(() => {
    let current = true
    sourceWorkspaceApi.getSheet(sheetId, page, 200, { search, sortColumn, sortDirection }).then(result => { if (current) setSheet(result) })
    return () => { current = false }
  }, [sheetId, page, search, sortColumn, sortDirection])
  const windowed = useMemo(() => {
    if (!sheet) return { start: 0, end: 0, rows: [] as FlowHubSheetPage['rows'] }
    const { start, end } = sheetWindow(sheet.rows.length, scrollTop, VIEWPORT_HEIGHT, ROW_HEIGHT, OVERSCAN)
    return { start, end, rows: sheet.rows.slice(start, end) }
  }, [sheet, scrollTop])
  const cellKey = (rowKey: string, columnKey: string) => `${rowKey}:${columnKey}`
  const valueAt = (rowKey: string, columnKey: string) => {
    const key = cellKey(rowKey, columnKey)
    if (key in changes) return changes[key]
    const row = sheet?.rows.find(item => item.rowKey === rowKey)
    return row?.cells[columnKey]?.raw ?? row?.cells[columnKey]?.value ?? ''
  }

  function paste(event: ClipboardEvent<HTMLInputElement>, rowIndex: number, columnIndex: number) {
    if (!sheet) return
    const matrix = event.clipboardData.getData('text/plain').replace(/\r/g, '').split('\n').filter((line, index, items) => line || index < items.length - 1).map(line => line.split('\t'))
    if (!matrix.length) return
    event.preventDefault()
    setChanges(current => {
      const next = { ...current }
      matrix.forEach((values, rowOffset) => values.forEach((value, columnOffset) => {
        const row = sheet.rows[rowIndex + rowOffset]
        const column = sheet.columns[columnIndex + columnOffset]
        if (row && column) next[cellKey(row.rowKey, column.columnKey)] = value
      }))
      return next
    })
  }

  function fillDown() {
    if (!sheet || !selected) return
    const source = valueAt(selected.rowKey, selected.columnKey)
    const sourceIndex = sheet.rows.findIndex(row => row.rowKey === selected.rowKey)
    setChanges(current => {
      const next = { ...current }
      for (const row of sheet.rows.slice(sourceIndex + 1)) next[cellKey(row.rowKey, selected.columnKey)] = source
      return next
    })
  }

  async function save() {
    if (!sheet || (Object.keys(changes).length === 0 && Object.keys(columnNames).length === 0)) return
    const payload = Object.entries(changes).map(([identity, value]) => {
      const separator = identity.indexOf(':')
      return { row_key: identity.slice(0, separator), column_key: identity.slice(separator + 1), value }
    })
    try {
      const updated = await sourceWorkspaceApi.patchSheet(sheet, payload, columnNames)
      setSheet(updated); setChanges({}); setColumnNames({})
      notify.success({ title: 'Sheet revision saved', description: `Revision ${updated.version} is immutable and ready for Snapshot creation.` })
    } catch (error) { notify.error({ title: 'Sheet was not saved', description: error instanceof Error ? error.message : 'Try again.' }) }
  }

  async function appendRows() {
    if (!sheet) return
    const updated = await sourceWorkspaceApi.appendRows(sheet)
    setSheet(updated); setChanges({})
  }

  if (!sheet) return <PageShell><div className="fh-card fh-card-pad">Loading FlowHub Sheet...</div></PageShell>
  const pageCount = Math.max(1, Math.ceil(sheet.total / sheet.pageSize))
  return <PageShell>
    <div className="fh-page-header"><div><h1 className="fh-page-title">{sheet.name}</h1><p className="fh-page-subtitle">FlowHub Sheet · Revision {sheet.version} · {sheet.total.toLocaleString()} rows</p></div><div className="flex gap-2"><button className="fh-button-secondary" type="button" onClick={() => navigate(`/sources/${sheet.sourceId}`)}><Icon name="settings" /> Configure Mapping</button><button className="fh-button-primary" type="button" disabled={!Object.keys(changes).length && !Object.keys(columnNames).length} onClick={() => void save()}><Icon name="save" /> Save Revision</button></div></div>
    <section className="fh-card" aria-label="FlowHub Sheet editor">
      <div className="fh-panel-header"><div><p className="fh-section-title">Product and pricing sheet</p><p className="fh-text-caption">Formulas are calculated by the deterministic FlowHub formula engine. Arbitrary scripts and external functions are not supported.</p></div><div className="flex flex-wrap gap-2"><input className="fh-input fh-button-sm" type="search" value={search} onChange={event => { setSearch(event.target.value); setPage(1) }} placeholder="Filter rows" aria-label="Filter Sheet rows" /><select className="fh-input fh-button-sm" value={sortColumn} onChange={event => { setSortColumn(event.target.value); setPage(1) }} aria-label="Sort Sheet by column"><option value="">Row order</option>{sheet.columns.map(column => <option value={column.columnKey} key={column.columnKey}>{column.name}</option>)}</select><button className="fh-button-secondary fh-button-sm" type="button" disabled={!sortColumn} onClick={() => setSortDirection(value => value === 'asc' ? 'desc' : 'asc')}>Sort {sortDirection}</button><button className="fh-button-secondary fh-button-sm" type="button" disabled={!selected} onClick={fillDown}>Fill down</button><button className="fh-button-secondary fh-button-sm" type="button" onClick={() => void appendRows()}><Icon name="add" /> Add 20 rows</button></div></div>
      <div className="fh-sheet-scroll" role="region" aria-label="Virtualized FlowHub Sheet">
        <div className="fh-sheet-header" style={{ gridTemplateColumns: `64px repeat(${sheet.columns.length}, minmax(160px, 1fr))` }}><span>#</span>{sheet.columns.map(column => <input className="fh-sheet-column-name" aria-label={`Column name ${column.name}`} key={column.columnKey} value={columnNames[column.columnKey] ?? column.name} onChange={event => setColumnNames(current => ({ ...current, [column.columnKey]: event.target.value }))} />)}</div>
        <div ref={viewport} className="fh-sheet-viewport" style={{ height: VIEWPORT_HEIGHT }} onScroll={event => setScrollTop(event.currentTarget.scrollTop)}>
          <div className="relative" style={{ height: sheet.rows.length * ROW_HEIGHT, minWidth: Math.max(800, sheet.columns.length * 160 + 64) }}>
            {windowed.rows.map((row, index) => {
              const physicalIndex = windowed.start + index
              return <div className="fh-sheet-row absolute inset-x-0" style={{ top: physicalIndex * ROW_HEIGHT, height: ROW_HEIGHT, gridTemplateColumns: `64px repeat(${sheet.columns.length}, minmax(160px, 1fr))` }} key={row.rowKey} data-row-key={row.rowKey}><span className="fh-sheet-row-number">{row.position}</span>{sheet.columns.map((column, columnIndex) => {
                const cell = row.cells[column.columnKey]
                return <input key={column.columnKey} className={`fh-sheet-cell ${cell?.error ? 'fh-sheet-cell-error' : ''}`} aria-label={`Row ${row.position}, ${column.name}`} title={cell?.error ?? cell?.formula ?? ''} value={valueAt(row.rowKey, column.columnKey)} onFocus={() => setSelected({ rowKey: row.rowKey, columnKey: column.columnKey })} onChange={event => setChanges(current => ({ ...current, [cellKey(row.rowKey, column.columnKey)]: event.target.value }))} onPaste={event => paste(event, physicalIndex, columnIndex)} />
              })}</div>
            })}
          </div>
        </div>
      </div>
      <div className="flex items-center justify-between border-t border-border p-4"><span className="fh-text-caption">{Object.keys(changes).length} unsaved cells · {Object.keys(columnNames).length} renamed columns · Page {page} of {pageCount}</span><div className="flex gap-2"><button className="fh-button-secondary fh-button-sm" type="button" disabled={page <= 1 || Object.keys(changes).length > 0 || Object.keys(columnNames).length > 0} onClick={() => setPage(value => value - 1)}>Previous</button><button className="fh-button-secondary fh-button-sm" type="button" disabled={page >= pageCount || Object.keys(changes).length > 0 || Object.keys(columnNames).length > 0} onClick={() => setPage(value => value + 1)}>Next</button></div></div>
    </section>
  </PageShell>
}
