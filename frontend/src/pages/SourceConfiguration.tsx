import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import PageShell from '../components/PageShell'
import Icon from '../components/Icon'
import { useNotification } from '../notifications/NotificationProvider'
import { formatChannelDisplayName } from '../features/unifiedWorkspace/channelDisplayName'
import { sourceWorkspaceApi } from '../features/sourceWorkspace/api'
import type { FieldMapping, ReferenceType, SourceChannel, SourceMapping, SourceProfile } from '../features/sourceWorkspace/types'

const SOURCE_FIELDS = [
  ['name', 'Source Product Name', true],
  ['source_key', 'Source Product Key', false],
  ['category', 'Category', false],
  ['brand', 'Brand', false],
  ['cost', 'Cost', false],
] as const
const CHANNEL_FIELDS = [
  ['external_id', 'External Listing ID'],
  ['price', 'Price'],
  ['stock', 'Stock'],
  ['status', 'Status'],
] as const
const DEFAULT_VALUE_POLICY: Record<string, string> = { blank: 'no_change', x: 'unavailable', dash: 'no_change', zero: 'explicit_zero', formula: 'calculated_value', invalid: 'blocked' }
const POLICY_OPTIONS: Record<string, Array<[string, string]>> = {
  blank: [['no_change', 'No target change'], ['blocked', 'Blocked issue']],
  x: [['unavailable', 'No listing / unavailable'], ['no_change', 'No target change'], ['blocked', 'Blocked issue']],
  dash: [['no_change', 'No target change'], ['unavailable', 'Unavailable'], ['blocked', 'Blocked issue']],
  zero: [['explicit_zero', 'Explicit zero'], ['no_change', 'No target change'], ['blocked', 'Blocked issue']],
  formula: [['calculated_value', 'Use evaluated result'], ['blocked', 'Blocked issue']],
  invalid: [['blocked', 'Blocked issue']],
}

interface SourcePreview {
  items: Array<{ rowKey: string; rowNumber: number; recognized: boolean; sourceProduct: Record<string, string | null>; channels: Array<{ channelId: string; fields: Record<string, string | null> }> }>
  recognized: number
  ignored: number
  issues: Array<{ category: string; severity: string; channelId: string | null; count: number }>
}

const emptyMapping = (field: string, required = false): FieldMapping => ({ field, referenceType: 'disabled', referenceValue: null, required })

function MappingControl({ mapping, onChange }: { mapping: FieldMapping; onChange: (value: FieldMapping) => void }) {
  return <div className="grid min-w-0 gap-2 sm:grid-cols-[160px_minmax(0,1fr)]">
    <select className="fh-input" aria-label={`${mapping.field} reference type`} value={mapping.referenceType} onChange={event => onChange({ ...mapping, referenceType: event.target.value as ReferenceType, referenceValue: event.target.value === 'disabled' ? null : mapping.referenceValue })}>
      <option value="disabled">Not configured</option>
      <option value="column_letter">Column letter</option>
      <option value="header_name">Exact header</option>
      <option value="column_id">Internal column</option>
    </select>
    <input className="fh-input" aria-label={`${mapping.field} column reference`} disabled={mapping.referenceType === 'disabled'} value={mapping.referenceValue ?? ''} onChange={event => onChange({ ...mapping, referenceValue: event.target.value })} placeholder={mapping.referenceType === 'column_letter' ? 'Example: C' : 'Exact column reference'} />
  </div>
}

export default function SourceConfiguration() {
  const { sourceId = '' } = useParams()
  const navigate = useNavigate()
  const notify = useNotification()
  const [source, setSource] = useState<(SourceProfile & { mapping: SourceMapping | null }) | null>(null)
  const [channels, setChannels] = useState<SourceChannel[]>([])
  const [sourceFields, setSourceFields] = useState<FieldMapping[]>(SOURCE_FIELDS.map(([field, _label, required]) => emptyMapping(field, required)))
  const [channelFields, setChannelFields] = useState<Record<string, FieldMapping[]>>({})
  const [channelWorksheets, setChannelWorksheets] = useState<Record<string, string>>({})
  const [selectedChannels, setSelectedChannels] = useState<string[]>([])
  const [worksheetMode, setWorksheetMode] = useState<'all' | 'selected'>('selected')
  const [dataStartRow, setDataStartRow] = useState(1)
  const [worksheetName, setWorksheetName] = useState('Sheet1')
  const [valuePolicy, setValuePolicy] = useState<Record<string, string>>(DEFAULT_VALUE_POLICY)
  const [preview, setPreview] = useState<SourcePreview | null>(null)
  const [previewing, setPreviewing] = useState(false)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    Promise.all([sourceWorkspaceApi.source(sourceId), sourceWorkspaceApi.channels()]).then(([loaded, available]) => {
      setSource(loaded); setChannels(available.items); setDataStartRow(loaded.mapping?.dataStartRow ?? loaded.dataStartRow); setWorksheetMode(loaded.mapping?.worksheetMode ?? loaded.worksheetMode); setWorksheetName(loaded.mapping?.worksheetName ?? loaded.worksheetName ?? 'Sheet1'); setValuePolicy({ ...DEFAULT_VALUE_POLICY, ...loaded.mapping?.valuePolicy })
      if (loaded.mapping) {
        setSourceFields(SOURCE_FIELDS.map(([field, _label, required]) => loaded.mapping!.sourceFields.find(item => item.field === field) ?? emptyMapping(field, required)))
        setSelectedChannels(loaded.mapping.channels.map(item => item.channelId))
        setChannelFields(Object.fromEntries(loaded.mapping.channels.map(item => [item.channelId, CHANNEL_FIELDS.map(([field]) => item.fields.find(existing => existing.field === field) ?? emptyMapping(field))])))
        setChannelWorksheets(Object.fromEntries(loaded.mapping.channels.map(item => [item.channelId, item.worksheetName ?? ''])))
      }
    })
  }, [sourceId])

  const channelMap = useMemo(() => new Map(channels.map(channel => [channel.channelId, channel])), [channels])
  function toggleChannel(channelId: string) {
    setSelectedChannels(current => current.includes(channelId) ? current.filter(item => item !== channelId) : [...current, channelId])
    setChannelFields(current => ({ ...current, [channelId]: current[channelId] ?? CHANNEL_FIELDS.map(([field]) => emptyMapping(field)) }))
  }
  function updateSourceField(field: string, value: FieldMapping) { setSourceFields(current => current.map(item => item.field === field ? value : item)) }
  function updateChannelField(channelId: string, field: string, value: FieldMapping) { setChannelFields(current => ({ ...current, [channelId]: (current[channelId] ?? []).map(item => item.field === field ? value : item) })) }

  async function save() {
    if (!source) return
    setSaving(true)
    try {
      await sourceWorkspaceApi.saveMapping(source.id, {
        expected_source_version: source.version,
        worksheet_mode: worksheetMode, worksheet_name: worksheetMode === 'selected' ? worksheetName : null, data_start_row: dataStartRow,
        source_fields: sourceFields.map(item => ({ field: item.field, reference_type: item.referenceType, reference_value: item.referenceValue, required: item.required ?? false })),
        channel_mappings: selectedChannels.map(channelId => ({ channel_id: channelId, worksheet_name: channelWorksheets[channelId] || null, fields: (channelFields[channelId] ?? []).map(item => ({ field: item.field, reference_type: item.referenceType, reference_value: item.referenceValue, required: false })) })),
        value_policy: valuePolicy,
      })
      notify.success({ title: 'Source Mapping saved', description: 'A new immutable Mapping revision was created.' })
      setSource(await sourceWorkspaceApi.source(source.id))
    } catch (error) {
      notify.error({ title: 'Mapping was not saved', description: error instanceof Error ? error.message : 'Check the mapped fields.' })
    } finally { setSaving(false) }
  }

  async function createWorkspace() {
    if (!source) return
    const workspace = await sourceWorkspaceApi.createWorkspace(source.id, `${source.name} pricing`)
    navigate(`/workspace/${workspace.id}`)
  }

  async function loadPreview() {
    setPreviewing(true)
    try { setPreview(await sourceWorkspaceApi.previewSource(sourceId) as unknown as SourcePreview) }
    catch (error) { notify.error({ title: 'Source Preview unavailable', description: error instanceof Error ? error.message : 'Save a valid Mapping and Sheet revision first.' }) }
    finally { setPreviewing(false) }
  }

  if (!source) return <PageShell><p className="fh-card fh-card-pad">Loading Source configuration...</p></PageShell>
  return <PageShell>
    <div className="fh-page-header"><div><h1 className="fh-page-title">{source.name}</h1><p className="fh-page-subtitle">Map Source Product identity first, then each destination Channel independently.</p></div><button className="fh-button-primary" type="button" disabled={!source.mapping} onClick={() => void createWorkspace()}><Icon name="workspace" /> Open Workspace</button></div>
    <section className="fh-card fh-card-pad space-y-4">
      <div className="grid gap-4 sm:grid-cols-3"><label className="fh-field-label">Worksheet policy<select className="fh-input mt-1" value={worksheetMode} onChange={event => setWorksheetMode(event.target.value as 'all' | 'selected')}><option value="selected">Selected worksheet</option><option value="all">All worksheets</option></select></label><label className="fh-field-label">Worksheet<input className="fh-input mt-1" disabled={worksheetMode === 'all'} value={worksheetName} onChange={event => setWorksheetName(event.target.value)} /></label><label className="fh-field-label">Data starts at row<input className="fh-input mt-1" type="number" min="1" value={dataStartRow} onChange={event => setDataStartRow(Number(event.target.value))} /></label></div>
      <div><h2 className="fh-section-title">Source Product fields</h2><p className="fh-text-caption">Unmapped columns are ignored. Header suggestions never override this saved Mapping.</p></div>
      <div className="grid gap-3">{SOURCE_FIELDS.map(([field, label]) => <label className="grid gap-1" key={field}><span className="fh-field-label">{label}</span><MappingControl mapping={sourceFields.find(item => item.field === field)!} onChange={value => updateSourceField(field, value)} /></label>)}</div>
    </section>
    <section className="fh-card fh-card-pad mt-5 space-y-4"><div><h2 className="fh-section-title">This Source manages</h2><p className="fh-text-caption">Only enabled Channels with an implemented connector are available.</p></div><div className="flex flex-wrap gap-2">{channels.map(channel => <label className="fh-channel-toggle" key={channel.channelId}><input type="checkbox" checked={selectedChannels.includes(channel.channelId)} onChange={() => toggleChannel(channel.channelId)} /><span>{formatChannelDisplayName(channel.channelId, { displayName: channel.name })}</span></label>)}</div>
      {selectedChannels.map(channelId => <article className="rounded-xl border border-border p-4" key={channelId}><div className="flex flex-wrap items-center gap-3"><h3 className="font-semibold text-text-base">{formatChannelDisplayName(channelId, { displayName: channelMap.get(channelId)?.name })}</h3><label className="fh-field-label ms-auto">Worksheet override<input className="fh-input mt-1" value={channelWorksheets[channelId] ?? ''} onChange={event => setChannelWorksheets(current => ({ ...current, [channelId]: event.target.value }))} placeholder="Use Source worksheet" /></label></div><div className="mt-3 grid gap-3">{CHANNEL_FIELDS.map(([field, label]) => <label className="grid gap-1" key={field}><span className="fh-field-label">{label}</span><MappingControl mapping={(channelFields[channelId] ?? CHANNEL_FIELDS.map(([name]) => emptyMapping(name))).find(item => item.field === field)!} onChange={value => updateChannelField(channelId, field, value)} /></label>)}</div></article>)}
      <div><h2 className="fh-section-title">Value handling</h2><p className="fh-text-caption">Each special value is interpreted explicitly. Currency and unit are never inferred.</p></div>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{Object.entries(POLICY_OPTIONS).map(([key, options]) => <label className="fh-field-label capitalize" key={key}>{key}<select className="fh-input mt-1" value={valuePolicy[key]} onChange={event => setValuePolicy(current => ({ ...current, [key]: event.target.value }))}>{options.map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label>)}</div>
      <div className="flex justify-end"><button className="fh-button-primary" type="button" disabled={saving} onClick={() => void save()}><Icon name="save" /> {saving ? 'Saving...' : 'Save Mapping Revision'}</button></div>
    </section>
    <section className="fh-card mt-5" aria-label="Source Preview"><div className="fh-panel-header"><div><h2 className="fh-section-title">Source Preview</h2><p className="fh-text-caption">Shows which rows the saved Mapping currently recognizes as Source Products.</p></div><button className="fh-button-secondary" type="button" disabled={!source.mapping || previewing} onClick={() => void loadPreview()}>{previewing ? 'Loading...' : 'Preview recognized rows'}</button></div>{preview && <><div className="grid grid-cols-2 gap-3 border-t border-border p-4"><div><strong className="text-text-base">{preview.recognized}</strong><span className="fh-text-caption ms-2">recognized</span></div><div><strong className="text-text-base">{preview.ignored}</strong><span className="fh-text-caption ms-2">ignored</span></div></div><div className="overflow-x-auto"><table className="min-w-full text-sm"><thead><tr><th className="p-3 text-start">Row</th><th className="p-3 text-start">Source Product</th><th className="p-3 text-start">Recognition</th><th className="p-3 text-start">Mapped Channels</th></tr></thead><tbody>{preview.items.slice(0, 25).map(item => <tr className="border-t border-border" key={item.rowKey}><td className="p-3">{item.rowNumber}</td><td className="p-3">{item.sourceProduct.name || item.sourceProduct.source_key || '—'}</td><td className="p-3">{item.recognized ? 'Source Product' : 'Ignored row'}</td><td className="p-3">{item.channels.map(channel => formatChannelDisplayName(channel.channelId)).join(', ') || 'None'}</td></tr>)}</tbody></table></div></>}</section>
  </PageShell>
}
