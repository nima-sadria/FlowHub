import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import PageShell from '../components/PageShell'
import Icon from '../components/Icon'
import { useNotification } from '../notifications/NotificationProvider'
import { sourceWorkspaceApi } from '../features/sourceWorkspace/api'

interface ImportPreview {
  filename: string
  sourceChecksum: string
  worksheets: string[]
  selectedWorksheet: string
  rowCount: number
  columnCount: number
  headers: string[]
  previewRows: Array<Array<string | number | null>>
}

async function base64(file: File): Promise<string> {
  const bytes = new Uint8Array(await file.arrayBuffer())
  let binary = ''
  const chunk = 0x8000
  for (let offset = 0; offset < bytes.length; offset += chunk) binary += String.fromCharCode(...bytes.subarray(offset, offset + chunk))
  return btoa(binary)
}

export default function SourceImportWizard() {
  const navigate = useNavigate()
  const notify = useNotification()
  const [file, setFile] = useState<File | null>(null)
  const [content, setContent] = useState('')
  const [preview, setPreview] = useState<ImportPreview | null>(null)
  const [worksheet, setWorksheet] = useState('')
  const [dataStartRow, setDataStartRow] = useState(2)
  const [busy, setBusy] = useState(false)

  async function inspect(selected: File) {
    setBusy(true)
    try {
      const encoded = await base64(selected)
      const result = await sourceWorkspaceApi.previewImport({ filename: selected.name, content_base64: encoded, worksheet_name: null }) as unknown as ImportPreview
      setFile(selected); setContent(encoded); setPreview(result); setWorksheet(result.selectedWorksheet)
    } catch (error) { notify.error({ title: 'Import preview failed', description: error instanceof Error ? error.message : 'Choose a valid XLSX or CSV file.' }) }
    finally { setBusy(false) }
  }

  async function create() {
    if (!file || !preview) return
    setBusy(true)
    try {
      const sheet = await sourceWorkspaceApi.importSheet({ name: file.name.replace(/\.(xlsx|csv)$/i, ''), filename: file.name, content_base64: content, worksheet_name: worksheet, expected_checksum: preview.sourceChecksum, data_start_row: dataStartRow })
      navigate(`/sources/${sheet.sourceId}`)
    } catch (error) { notify.error({ title: 'Import failed', description: error instanceof Error ? error.message : 'The original file was not changed.' }) }
    finally { setBusy(false) }
  }

  return <PageShell>
    <div className="fh-page-header"><div><h1 className="fh-page-title">Import spreadsheet</h1><p className="fh-page-subtitle">Preview an XLSX or CSV, then create an internal managed FlowHub Sheet.</p></div></div>
    <section className="fh-card fh-card-pad space-y-5">
      <label className="block rounded-xl border border-dashed border-border p-8 text-center"><Icon name="upload" className="mx-auto mb-3 h-8 w-8" /><span className="block font-medium text-text-base">Choose XLSX or CSV</span><span className="fh-text-caption block">The original file is read only and never modified.</span><input className="mt-4" type="file" accept=".xlsx,.csv" disabled={busy} onChange={event => { const selected = event.target.files?.[0]; if (selected) void inspect(selected) }} /></label>
      {preview && <>
        <div className="grid gap-4 sm:grid-cols-3"><label className="fh-field-label">Worksheet<select className="fh-input mt-1" value={worksheet} onChange={event => setWorksheet(event.target.value)}>{preview.worksheets.map(item => <option key={item}>{item}</option>)}</select></label><label className="fh-field-label">Data starts at row<input className="fh-input mt-1" type="number" min="1" value={dataStartRow} onChange={event => setDataStartRow(Number(event.target.value))} /></label><div><span className="fh-field-label">Detected</span><p className="mt-2 text-text-base">{preview.rowCount.toLocaleString()} rows · {preview.columnCount} columns</p></div></div>
        <div className="fh-grid-scroll"><table className="min-w-full border-collapse text-sm"><thead><tr>{preview.headers.map((header, index) => <th className="border border-border bg-bg-base p-2 text-start" key={`${header}-${index}`}>{header || `Column ${index + 1}`}</th>)}</tr></thead><tbody>{preview.previewRows.slice(1, 15).map((row, rowIndex) => <tr key={rowIndex}>{preview.headers.map((_header, columnIndex) => <td className="border border-border p-2" key={columnIndex}>{String(row[columnIndex] ?? '')}</td>)}</tr>)}</tbody></table></div>
        <div className="fh-alert fh-alert-info"><Icon name="info" /><span>After import, map Source Product fields and each enabled Channel explicitly. FlowHub does not infer business fields from headers.</span></div>
        <div className="flex justify-end"><button className="fh-button-primary" type="button" disabled={busy} onClick={() => void create()}><Icon name="apply" /> Create FlowHub Sheet</button></div>
      </>}
    </section>
  </PageShell>
}
