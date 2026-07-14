import { translate } from '../i18n'
import { formatNumber } from '../i18n/format'
import { localizedApiError } from '../i18n/errors'
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
    } catch (error) { notify.error({ title: translate('sources:sourceImportWizard.importPreviewFailed'), description: localizedApiError(error, 'sources:sourceImportWizard.chooseAValidXlsxOrCsvFile') }) }
    finally { setBusy(false) }
  }

  async function create() {
    if (!file || !preview) return
    setBusy(true)
    try {
      const sheet = await sourceWorkspaceApi.importSheet({ name: file.name.replace(/\.(xlsx|csv)$/i, ''), filename: file.name, content_base64: content, worksheet_name: worksheet, expected_checksum: preview.sourceChecksum, data_start_row: dataStartRow })
      navigate(`/sources/${sheet.sourceId}`)
    } catch (error) { notify.error({ title: translate('sources:sourceImportWizard.importFailed'), description: localizedApiError(error, 'sources:sourceImportWizard.theOriginalFileWasNotChanged') }) }
    finally { setBusy(false) }
  }

  return <PageShell>
    <div className="fh-page-header"><div><h1 className="fh-page-title">{translate('sources:sourceCenter.importSpreadsheet')}</h1><p className="fh-page-subtitle">{translate('sources:sourceImportWizard.previewAnXlsxOrCsvThenCreate')}</p></div></div>
    <section className="fh-card fh-card-pad space-y-5">
      <label className="block rounded-xl border border-dashed border-border p-8 text-center"><Icon name="upload" className="mx-auto mb-3 h-8 w-8" /><span className="block font-medium text-text-base">{translate('sources:sourceImportWizard.chooseXlsxOrCsv')}</span><span className="fh-text-caption block">{translate('sources:sourceImportWizard.theOriginalFileIsReadOnlyAnd')}</span><input className="mt-4" type="file" accept=".xlsx,.csv" disabled={busy} onChange={event => { const selected = event.target.files?.[0]; if (selected) void inspect(selected) }} /></label>
      {preview && <>
        <div className="grid gap-4 sm:grid-cols-3"><label className="fh-field-label">{translate('sources:sourceConfiguration.worksheet')}<select className="fh-input mt-1" value={worksheet} onChange={event => setWorksheet(event.target.value)}>{preview.worksheets.map(item => <option key={item}>{item}</option>)}</select></label><label className="fh-field-label">{translate('sources:sourceConfiguration.dataStartsAtRow')}<input className="fh-input mt-1" type="number" min="1" value={dataStartRow} onChange={event => setDataStartRow(Number(event.target.value))} /></label><div><span className="fh-field-label">{translate('sources:sourceImportWizard.detected')}</span><p className="mt-2 text-text-base">{formatNumber(preview.rowCount)} {translate('sources:sourceImportWizard.rows')} {formatNumber(preview.columnCount)} {translate('sources:sourceImportWizard.columns')}</p></div></div>
        <div className="fh-grid-scroll"><table className="min-w-full border-collapse text-sm"><thead><tr>{preview.headers.map((header, index) => <th className="border border-border bg-bg-base p-2 text-start" key={`${header}-${index}`}>{header || translate('sources:sourceImportWizard.column', { value1: index + 1 })}</th>)}</tr></thead><tbody>{preview.previewRows.slice(1, 15).map((row, rowIndex) => <tr key={rowIndex}>{preview.headers.map((_header, columnIndex) => <td className="border border-border p-2" key={columnIndex}>{String(row[columnIndex] ?? '')}</td>)}</tr>)}</tbody></table></div>
        <div className="fh-alert fh-alert-info"><Icon name="info" /><span>{translate('sources:sourceImportWizard.afterImportMapSourceProductFieldsAnd')}</span></div>
        <div className="flex justify-end"><button className="fh-button-primary" type="button" disabled={busy} onClick={() => void create()}><Icon name="apply" /> {translate('sources:sourceImportWizard.createFlowhubSheet')}</button></div>
      </>}
    </section>
  </PageShell>
}
