import { translate } from '../i18n'
import { localizedApiError } from '../i18n/errors'
import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import PageShell from '../components/PageShell'
import Icon from '../components/Icon'
import { useNotification } from '../notifications/NotificationProvider'
import { formatChannelDisplayName } from '../features/unifiedWorkspace/channelDisplayName'
import { sourceWorkspaceApi } from '../features/sourceWorkspace/api'
import type { FieldMapping, ReferenceType, SourceChannel, SourceMapping, SourceProfile } from '../features/sourceWorkspace/types'

const SOURCE_FIELDS = [
  ['name', 'sources:sourceConfiguration.sourceProductName', true],
  ['source_key', 'sources:sourceConfiguration.sourceProductKey', false],
  ['category', 'sources:sourceConfiguration.category', false],
  ['brand', 'sources:sourceConfiguration.brand', false],
  ['cost', 'sources:sourceConfiguration.cost', false],
] as const
const CHANNEL_FIELDS = [
  ['external_id', 'sources:sourceConfiguration.externalListingId'],
  ['price', 'common:field.price'],
  ['stock', 'common:field.stock'],
  ['status', 'common:field.status'],
] as const
const DEFAULT_VALUE_POLICY: Record<string, string> = { blank: 'no_change', x: 'unavailable', dash: 'no_change', zero: 'explicit_zero', formula: 'calculated_value', invalid: 'blocked' }
const POLICY_OPTIONS: Record<string, Array<[string, string]>> = {
  blank: [['no_change', 'sources:sourceConfiguration.noTargetChange'], ['blocked', 'sources:sourceConfiguration.blockedIssue']],
  x: [['unavailable', 'sources:sourceConfiguration.noListingUnavailable'], ['no_change', 'sources:sourceConfiguration.noTargetChange'], ['blocked', 'sources:sourceConfiguration.blockedIssue']],
  dash: [['no_change', 'sources:sourceConfiguration.noTargetChange'], ['unavailable', 'common:status.unavailable'], ['blocked', 'sources:sourceConfiguration.blockedIssue']],
  zero: [['explicit_zero', 'sources:sourceConfiguration.explicitZero'], ['no_change', 'sources:sourceConfiguration.noTargetChange'], ['blocked', 'sources:sourceConfiguration.blockedIssue']],
  formula: [['calculated_value', 'sources:sourceConfiguration.useEvaluatedResult'], ['blocked', 'sources:sourceConfiguration.blockedIssue']],
  invalid: [['blocked', 'sources:sourceConfiguration.blockedIssue']],
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
    <select className="fh-input" aria-label={translate('sources:sourceConfiguration.referenceType', { field: mapping.field })} value={mapping.referenceType} onChange={event => onChange({ ...mapping, referenceType: event.target.value as ReferenceType, referenceValue: event.target.value === "disabled" ? null : mapping.referenceValue })}>
      <option value="disabled">{translate('sources:sourceConfiguration.notConfigured')}</option>
      <option value="column_letter">{translate('sources:sourceConfiguration.columnLetter')}</option>
      <option value="header_name">{translate('sources:sourceConfiguration.exactHeader')}</option>
      <option value="column_id">{translate('sources:sourceConfiguration.internalColumn')}</option>
    </select>
    <input className="fh-input" aria-label={translate('sources:sourceConfiguration.columnReference', { field: mapping.field })} disabled={mapping.referenceType === "disabled"} value={mapping.referenceValue ?? ''} onChange={event => onChange({ ...mapping, referenceValue: event.target.value })} placeholder={mapping.referenceType === "column_letter" ? translate('sources:sourceConfiguration.exampleColumn') : translate('sources:sourceConfiguration.exactColumnReference')} />
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
      notify.success({ title: translate('sources:sourceConfiguration.sourceMappingSaved'), description: translate('sources:sourceConfiguration.aNewImmutableMappingRevisionWasCreated') })
      setSource(await sourceWorkspaceApi.source(source.id))
    } catch (error) {
      notify.error({ title: translate('sources:sourceConfiguration.mappingWasNotSaved'), description: localizedApiError(error, 'sources:sourceConfiguration.checkTheMappedFields') })
    } finally { setSaving(false) }
  }

  async function createWorkspace() {
    if (!source) return
    const workspace = await sourceWorkspaceApi.createWorkspace(source.id, translate('sources:sourceConfiguration.pricingWorkspaceName', { source: source.name }))
    navigate(`/workspace/${workspace.id}`)
  }

  async function loadPreview() {
    setPreviewing(true)
    try { setPreview(await sourceWorkspaceApi.previewSource(sourceId) as unknown as SourcePreview) }
    catch (error) { notify.error({ title: translate('sources:sourceConfiguration.sourcePreviewUnavailable'), description: localizedApiError(error, 'sources:sourceConfiguration.saveAValidMappingAndSheetRevision') }) }
    finally { setPreviewing(false) }
  }

  if (!source) return <PageShell><p className="fh-card fh-card-pad">{translate('sources:sourceConfiguration.loadingSourceConfiguration')}</p></PageShell>
  return <PageShell>
    <div className="fh-page-header"><div><h1 className="fh-page-title">{source.name}</h1><p className="fh-page-subtitle">{translate('sources:sourceConfiguration.mapSourceProductIdentityFirstThenEach')}</p></div><button className="fh-button-primary" type="button" disabled={!source.mapping} onClick={() => void createWorkspace()}><Icon name="workspace" /> {translate('sources:sourceConfiguration.openWorkspace')}</button></div>
    <section className="fh-card fh-card-pad space-y-4">
      <div className="grid gap-4 sm:grid-cols-3"><label className="fh-field-label">{translate('sources:sourceConfiguration.worksheetPolicy')}<select className="fh-input mt-1" value={worksheetMode} onChange={event => setWorksheetMode(event.target.value as 'all' | 'selected')}><option value="selected">{translate('sources:sourceConfiguration.selectedWorksheet')}</option><option value="all">{translate('sources:sourceConfiguration.allWorksheets')}</option></select></label><label className="fh-field-label">{translate('sources:sourceConfiguration.worksheet')}<input className="fh-input mt-1" disabled={worksheetMode === "all"} value={worksheetName} onChange={event => setWorksheetName(event.target.value)} /></label><label className="fh-field-label">{translate('sources:sourceConfiguration.dataStartsAtRow')}<input className="fh-input mt-1" type="number" min="1" value={dataStartRow} onChange={event => setDataStartRow(Number(event.target.value))} /></label></div>
      <div><h2 className="fh-section-title">{translate('sources:sourceConfiguration.sourceProductFields')}</h2><p className="fh-text-caption">{translate('sources:sourceConfiguration.unmappedColumnsAreIgnoredHeaderSuggestionsNever')}</p></div>
      <div className="grid gap-3">{SOURCE_FIELDS.map(([field, labelKey]) => <label className="grid gap-1" key={field}><span className="fh-field-label">{translate(labelKey)}</span><MappingControl mapping={sourceFields.find(item => item.field === field)!} onChange={value => updateSourceField(field, value)} /></label>)}</div>
    </section>
    <section className="fh-card fh-card-pad mt-5 space-y-4"><div><h2 className="fh-section-title">{translate('sources:sourceConfiguration.thisSourceManages')}</h2><p className="fh-text-caption">{translate('sources:sourceConfiguration.onlyEnabledChannelsWithAnImplementedConnector')}</p></div><div className="flex flex-wrap gap-2">{channels.map(channel => <label className="fh-channel-toggle" key={channel.channelId}><input type="checkbox" checked={selectedChannels.includes(channel.channelId)} onChange={() => toggleChannel(channel.channelId)} /><span>{formatChannelDisplayName(channel.channelId, { displayName: channel.name })}</span></label>)}</div>
      {selectedChannels.map(channelId => <article className="rounded-xl border border-border p-4" key={channelId}><div className="flex flex-wrap items-center gap-3"><h3 className="font-semibold text-text-base">{formatChannelDisplayName(channelId, { displayName: channelMap.get(channelId)?.name })}</h3><label className="fh-field-label ms-auto">{translate('sources:sourceConfiguration.worksheetOverride')}<input className="fh-input mt-1" value={channelWorksheets[channelId] ?? ''} onChange={event => setChannelWorksheets(current => ({ ...current, [channelId]: event.target.value }))} placeholder={translate('sources:sourceConfiguration.useSourceWorksheet')} /></label></div><div className="mt-3 grid gap-3">{CHANNEL_FIELDS.map(([field, labelKey]) => <label className="grid gap-1" key={field}><span className="fh-field-label">{translate(labelKey)}</span><MappingControl mapping={(channelFields[channelId] ?? CHANNEL_FIELDS.map(([name]) => emptyMapping(name))).find(item => item.field === field)!} onChange={value => updateChannelField(channelId, field, value)} /></label>)}</div></article>)}
      <div><h2 className="fh-section-title">{translate('sources:sourceConfiguration.valueHandling')}</h2><p className="fh-text-caption">{translate('sources:sourceConfiguration.eachSpecialValueIsInterpretedExplicitlyCurrency')}</p></div>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{Object.entries(POLICY_OPTIONS).map(([key, options]) => <label className="fh-field-label capitalize" key={key}>{translate(`sources:sourceConfiguration.valueType.${key}`)}<select className="fh-input mt-1" value={valuePolicy[key]} onChange={event => setValuePolicy(current => ({ ...current, [key]: event.target.value }))}>{options.map(([value, labelKey]) => <option value={value} key={value}>{translate(labelKey)}</option>)}</select></label>)}</div>
      <div className="flex justify-end"><button className="fh-button-primary" type="button" disabled={saving} onClick={() => void save()}><Icon name="save" /> {saving ? translate('sources:sourceConfiguration.saving') : translate('sources:sourceConfiguration.saveMappingRevision')}</button></div>
    </section>
    <section className="fh-card mt-5" aria-label={translate('sources:sourceConfiguration.sourcePreview')}><div className="fh-panel-header"><div><h2 className="fh-section-title">{translate('sources:sourceConfiguration.sourcePreview')}</h2><p className="fh-text-caption">{translate('sources:sourceConfiguration.showsWhichRowsTheSavedMappingCurrently')}</p></div><button className="fh-button-secondary" type="button" disabled={!source.mapping || previewing} onClick={() => void loadPreview()}>{previewing ? translate('sources:sourceConfiguration.loading') : translate('sources:sourceConfiguration.previewRecognizedRows')}</button></div>{preview && <><div className="grid grid-cols-2 gap-3 border-t border-border p-4"><div><strong className="text-text-base">{preview.recognized}</strong><span className="fh-text-caption ms-2">{translate('sources:sourceConfiguration.recognized')}</span></div><div><strong className="text-text-base">{preview.ignored}</strong><span className="fh-text-caption ms-2">{translate('sources:sourceConfiguration.ignored')}</span></div></div><div className="overflow-x-auto"><table className="min-w-full text-sm"><thead><tr><th className="p-3 text-start">{translate('sources:sourceConfiguration.row')}</th><th className="p-3 text-start">{translate('sources:sourceConfiguration.sourceProduct')}</th><th className="p-3 text-start">{translate('sources:sourceConfiguration.recognition')}</th><th className="p-3 text-start">{translate('sources:sourceConfiguration.mappedChannels')}</th></tr></thead><tbody>{preview.items.slice(0, 25).map(item => <tr className="border-t border-border" key={item.rowKey}><td className="p-3">{item.rowNumber}</td><td className="p-3">{item.sourceProduct.name || item.sourceProduct.source_key || '—'}</td><td className="p-3">{item.recognized ? translate('sources:sourceConfiguration.sourceProduct') : translate('sources:sourceConfiguration.ignoredRow')}</td><td className="p-3">{item.channels.map(channel => formatChannelDisplayName(channel.channelId)).join(', ') || translate('common:status.none')}</td></tr>)}</tbody></table></div></>}</section>
  </PageShell>
}
