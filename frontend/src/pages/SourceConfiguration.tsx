import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import Icon from '../components/Icon'
import PageShell from '../components/PageShell'
import { formatChannelDisplayName } from '../features/unifiedWorkspace/channelDisplayName'
import { sourceWorkspaceApi } from '../features/sourceWorkspace/api'
import type {
  FieldMapping,
  ReferenceType,
  SourceChannel,
  SourceMapping,
  SourceProfile,
} from '../features/sourceWorkspace/types'
import { translate } from '../i18n'
import { localizedApiError } from '../i18n/errors'
import { useNotification } from '../notifications/NotificationProvider'

const SOURCE_FIELDS = [
  ['name', 'sources:sourceConfiguration.sourceProductName', true],
  ['source_key', 'sources:sourceConfiguration.sourceProductKey', false],
  ['category', 'sources:sourceConfiguration.category', false],
  ['brand', 'sources:sourceConfiguration.brand', false],
  ['cost', 'sources:sourceConfiguration.cost', false],
] as const

const CHANNEL_FIELDS = [
  ['external_id', 'sources:sourceConfiguration.productIdentifier'],
  ['price', 'common:field.price'],
  ['stock', 'common:field.stock'],
  ['status', 'common:field.status'],
] as const

const DEFAULT_VALUE_POLICY: Record<string, string> = {
  blank: 'no_change',
  x: 'unavailable',
  dash: 'no_change',
  zero: 'explicit_zero',
  formula: 'calculated_value',
  invalid: 'blocked',
}

const POLICY_OPTIONS: Record<string, Array<[string, string]>> = {
  blank: [['no_change', 'sources:sourceConfiguration.noTargetChange'], ['blocked', 'sources:sourceConfiguration.blockedIssue']],
  x: [['unavailable', 'sources:sourceConfiguration.noListingUnavailable'], ['no_change', 'sources:sourceConfiguration.noTargetChange'], ['blocked', 'sources:sourceConfiguration.blockedIssue']],
  dash: [['no_change', 'sources:sourceConfiguration.noTargetChange'], ['unavailable', 'common:status.unavailable'], ['blocked', 'sources:sourceConfiguration.blockedIssue']],
  zero: [['explicit_zero', 'sources:sourceConfiguration.explicitZero'], ['no_change', 'sources:sourceConfiguration.noTargetChange'], ['blocked', 'sources:sourceConfiguration.blockedIssue']],
  formula: [['calculated_value', 'sources:sourceConfiguration.useEvaluatedResult'], ['blocked', 'sources:sourceConfiguration.blockedIssue']],
  invalid: [['blocked', 'sources:sourceConfiguration.blockedIssue']],
}

interface SourcePreview {
  items: Array<{
    rowKey: string
    rowNumber: number
    recognized: boolean
    sourceProduct: Record<string, string | null>
    channels: Array<{ channelId: string; fields: Record<string, string | null> }>
  }>
  recognized: number
  ignored: number
  issues: Array<{ category: string; severity: string; channelId: string | null; count: number }>
}

const emptyMapping = (field: string, required = false): FieldMapping => ({
  field,
  referenceType: 'disabled',
  referenceValue: null,
  required,
})

const emptyChannelFields = (): FieldMapping[] => CHANNEL_FIELDS.map(([field]) => emptyMapping(field))

function MappingControl({
  mapping,
  disabled = false,
  allowInternalColumnId = true,
  onChange,
}: {
  mapping: FieldMapping
  disabled?: boolean
  allowInternalColumnId?: boolean
  onChange: (value: FieldMapping) => void
}) {
  return (
    <div className="grid min-w-0 gap-2 sm:grid-cols-[180px_minmax(0,1fr)]">
      <label className="grid gap-1">
        <span className="fh-text-caption">{translate('sources:sourceConfiguration.mappingMethod')}</span>
        <select
          className="fh-input"
          aria-label={translate('sources:sourceConfiguration.referenceType', { field: mapping.field })}
          disabled={disabled}
          value={mapping.referenceType}
          onChange={event => onChange({
            ...mapping,
            referenceType: event.target.value as ReferenceType,
            referenceValue: event.target.value === 'disabled' ? null : mapping.referenceValue,
          })}
        >
          <option value="disabled">{translate('sources:sourceConfiguration.disabled')}</option>
          <option value="column_letter">{translate('sources:sourceConfiguration.columnLetter')}</option>
          <option value="header_name">{translate('sources:sourceConfiguration.exactHeader')}</option>
          {allowInternalColumnId && <option value="column_id">{translate('sources:sourceConfiguration.internalColumnId')}</option>}
        </select>
      </label>
      <label className="grid gap-1">
        <span className="fh-text-caption">{translate('sources:sourceConfiguration.column')}</span>
        <input
          className="fh-input"
          aria-label={translate('sources:sourceConfiguration.columnReference', { field: mapping.field })}
          disabled={disabled || mapping.referenceType === 'disabled'}
          value={mapping.referenceValue ?? ''}
          onChange={event => onChange({ ...mapping, referenceValue: event.target.value })}
          placeholder={mapping.referenceType === 'column_letter'
            ? translate('sources:sourceConfiguration.exampleColumn')
            : translate('sources:sourceConfiguration.exactColumnReference')}
        />
      </label>
    </div>
  )
}

function channelValidation(fields: FieldMapping[], enabled: boolean): string[] {
  if (!enabled) return []
  const issues: string[] = []
  const identifier = fields.find(item => item.field === 'external_id')
  if (!identifier || identifier.referenceType === 'disabled' || !identifier.referenceValue?.trim()) {
    issues.push(translate('sources:sourceConfiguration.productIdentifierRequired'))
  }
  const references = new Map<string, string>()
  for (const field of fields) {
    if (field.referenceType === 'disabled' || !field.referenceValue?.trim()) continue
    const identity = `${field.referenceType}:${field.referenceValue.trim().toLocaleLowerCase()}`
    const previous = references.get(identity)
    if (previous) {
      issues.push(translate('sources:sourceConfiguration.conflictingColumnMapping', {
        first: previous,
        second: field.field,
      }))
    } else {
      references.set(identity, field.field)
    }
  }
  return issues
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
  const [channelEnabled, setChannelEnabled] = useState<Record<string, boolean>>({})
  const [configuredChannelIds, setConfiguredChannelIds] = useState<string[]>([])
  const [copyFrom, setCopyFrom] = useState<Record<string, string>>({})
  const [worksheetMode, setWorksheetMode] = useState<'all' | 'selected'>('selected')
  const [dataStartRow, setDataStartRow] = useState(1)
  const [worksheetName, setWorksheetName] = useState('Sheet1')
  const [valuePolicy, setValuePolicy] = useState<Record<string, string>>(DEFAULT_VALUE_POLICY)
  const [preview, setPreview] = useState<SourcePreview | null>(null)
  const [previewing, setPreviewing] = useState(false)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    let active = true
    Promise.all([sourceWorkspaceApi.source(sourceId), sourceWorkspaceApi.channels()]).then(([loaded, available]) => {
      if (!active) return
      setSource(loaded)
      setChannels(available.items)
      setDataStartRow(loaded.mapping?.dataStartRow ?? loaded.dataStartRow)
      setWorksheetMode(loaded.mapping?.worksheetMode ?? loaded.worksheetMode)
      setWorksheetName(loaded.mapping?.worksheetName ?? loaded.worksheetName ?? 'Sheet1')
      setValuePolicy({ ...DEFAULT_VALUE_POLICY, ...loaded.mapping?.valuePolicy })
      if (loaded.mapping) {
        setSourceFields(SOURCE_FIELDS.map(([field, _label, required]) => loaded.mapping!.sourceFields.find(item => item.field === field) ?? emptyMapping(field, required)))
        setConfiguredChannelIds(loaded.mapping.channels.map(item => item.channelId))
        setChannelEnabled(Object.fromEntries(loaded.mapping.channels.map(item => [item.channelId, item.enabled])))
        setChannelFields(Object.fromEntries(loaded.mapping.channels.map(item => [
          item.channelId,
          CHANNEL_FIELDS.map(([field]) => item.fields.find(existing => existing.field === field) ?? emptyMapping(field)),
        ])))
        setChannelWorksheets(Object.fromEntries(loaded.mapping.channels.map(item => [item.channelId, item.worksheetName ?? ''])))
      } else if (loaded.legacyMapping) {
        const legacy = loaded.legacyMapping
        setConfiguredChannelIds([legacy.primaryChannelId])
        setChannelEnabled({ [legacy.primaryChannelId]: true })
        setChannelFields({
          [legacy.primaryChannelId]: CHANNEL_FIELDS.map(([field]) => legacy.fields.find(item => item.field === field) ?? emptyMapping(field)),
        })
      }
    }).catch(error => {
      notify.error({
        title: translate('sources:sourceConfiguration.sourceConfigurationUnavailable'),
        description: localizedApiError(error, 'sources:sourceConfiguration.tryAgain'),
      })
    })
    return () => { active = false }
  }, [notify, sourceId])

  function ensureConfigured(channelId: string) {
    setConfiguredChannelIds(current => current.includes(channelId) ? current : [...current, channelId])
    setChannelFields(current => ({ ...current, [channelId]: current[channelId] ?? emptyChannelFields() }))
  }

  function toggleChannel(channelId: string) {
    ensureConfigured(channelId)
    setChannelEnabled(current => ({ ...current, [channelId]: !current[channelId] }))
  }

  function updateSourceField(field: string, value: FieldMapping) {
    setSourceFields(current => current.map(item => item.field === field ? value : item))
  }

  function updateChannelField(channelId: string, field: string, value: FieldMapping) {
    ensureConfigured(channelId)
    setChannelFields(current => ({
      ...current,
      [channelId]: (current[channelId] ?? emptyChannelFields()).map(item => item.field === field ? value : item),
    }))
  }

  function clearMapping(channelId: string) {
    ensureConfigured(channelId)
    setChannelFields(current => ({ ...current, [channelId]: emptyChannelFields() }))
  }

  function copyMapping(channelId: string) {
    const sourceChannelId = copyFrom[channelId]
    if (!sourceChannelId || !channelFields[sourceChannelId]) return
    ensureConfigured(channelId)
    setChannelFields(current => ({
      ...current,
      [channelId]: current[sourceChannelId].map(item => ({ ...item })),
    }))
  }

  async function save() {
    if (!source) return
    setSaving(true)
    try {
      await sourceWorkspaceApi.saveMapping(source.id, {
        expected_source_version: source.version,
        worksheet_mode: worksheetMode,
        worksheet_name: worksheetMode === 'selected' ? worksheetName : null,
        data_start_row: dataStartRow,
        source_fields: sourceFields.map(item => ({
          field: item.field,
          reference_type: item.referenceType,
          reference_value: item.referenceValue,
          required: item.required ?? false,
        })),
        channel_mappings: configuredChannelIds.map(channelId => ({
          channel_id: channelId,
          worksheet_name: channelWorksheets[channelId] || null,
          enabled: Boolean(channelEnabled[channelId]),
          fields: (channelFields[channelId] ?? emptyChannelFields()).map(item => ({
            field: item.field,
            reference_type: item.referenceType,
            reference_value: item.referenceValue,
            required: false,
          })),
        })),
        value_policy: valuePolicy,
      })
      notify.success({
        title: translate('sources:sourceConfiguration.sourceMappingSaved'),
        description: translate('sources:sourceConfiguration.aNewImmutableMappingRevisionWasCreated'),
      })
      setSource(await sourceWorkspaceApi.source(source.id))
      setPreview(null)
    } catch (error) {
      notify.error({
        title: translate('sources:sourceConfiguration.mappingWasNotSaved'),
        description: localizedApiError(error, 'sources:sourceConfiguration.checkTheMappedFields'),
      })
    } finally {
      setSaving(false)
    }
  }

  async function createWorkspace() {
    if (!source) return
    const workspace = await sourceWorkspaceApi.createWorkspace(
      source.id,
      translate('sources:sourceConfiguration.pricingWorkspaceName', { source: source.name }),
    )
    navigate(`/workspace/${workspace.id}`)
  }

  async function loadPreview() {
    setPreviewing(true)
    try {
      setPreview(await sourceWorkspaceApi.previewSource(sourceId) as unknown as SourcePreview)
    } catch (error) {
      notify.error({
        title: translate('sources:sourceConfiguration.sourcePreviewUnavailable'),
        description: localizedApiError(error, 'sources:sourceConfiguration.saveAValidMappingAndSheetRevision'),
      })
    } finally {
      setPreviewing(false)
    }
  }

  if (!source) {
    return <PageShell><p className="fh-card fh-card-pad">{translate('sources:sourceConfiguration.loadingSourceConfiguration')}</p></PageShell>
  }

  return (
    <PageShell>
      <div className="fh-page-header">
        <div>
          <h1 className="fh-page-title">{source.name}</h1>
          <p className="fh-page-subtitle">{translate('sources:sourceConfiguration.mapSourceProductIdentityFirstThenEach')}</p>
        </div>
        <button className="fh-button-primary" type="button" disabled={!source.mapping} onClick={() => void createWorkspace()}>
          <Icon name="workspace" /> {translate('sources:sourceConfiguration.openWorkspace')}
        </button>
      </div>

      {source.legacyMapping && !source.mapping && (
        <section className="fh-alert-warning mb-5" role="status">
          <strong>{translate('sources:sourceConfiguration.legacyMappingDetected')}</strong>
          <p className="mt-1">{translate('sources:sourceConfiguration.legacyMappingAssignedToPrimaryChannel')}</p>
        </section>
      )}

      <section className="fh-card fh-card-pad space-y-4">
        <div className="grid gap-4 sm:grid-cols-3">
          <label className="fh-field-label">
            {translate('sources:sourceConfiguration.worksheetPolicy')}
            <select className="fh-input mt-1" value={worksheetMode} onChange={event => setWorksheetMode(event.target.value as 'all' | 'selected')}>
              <option value="selected">{translate('sources:sourceConfiguration.selectedWorksheet')}</option>
              <option value="all">{translate('sources:sourceConfiguration.allWorksheets')}</option>
            </select>
          </label>
          <label className="fh-field-label">
            {translate('sources:sourceConfiguration.worksheet')}
            <input className="fh-input mt-1" disabled={worksheetMode === 'all'} value={worksheetName} onChange={event => setWorksheetName(event.target.value)} />
          </label>
          <label className="fh-field-label">
            {translate('sources:sourceConfiguration.dataStartsAtRow')}
            <input className="fh-input mt-1" type="number" min="1" value={dataStartRow} onChange={event => setDataStartRow(Number(event.target.value))} />
          </label>
        </div>
        <div>
          <h2 className="fh-section-title">{translate('sources:sourceConfiguration.sourceProductFields')}</h2>
          <p className="fh-text-caption">{translate('sources:sourceConfiguration.unmappedColumnsAreIgnoredHeaderSuggestionsNever')}</p>
        </div>
        <div className="grid gap-3">
          {SOURCE_FIELDS.map(([field, labelKey]) => (
            <label className="grid gap-1" key={field}>
              <span className="fh-field-label">{translate(labelKey)}</span>
              <MappingControl
                mapping={sourceFields.find(item => item.field === field)!}
                allowInternalColumnId={source.sourceKind === 'flowhub_sheet'}
                onChange={value => updateSourceField(field, value)}
              />
            </label>
          ))}
        </div>
      </section>

      <section className="fh-card fh-card-pad mt-5 space-y-4" aria-label={translate('sources:sourceConfiguration.channelMappings')}>
        <div>
          <h2 className="fh-section-title">{translate('sources:sourceConfiguration.channelMappings')}</h2>
          <p className="fh-text-caption">{translate('sources:sourceConfiguration.channelMappingsAreIndependent')}</p>
        </div>
        <div className="space-y-3">
          {channels.map(channel => {
            const enabled = Boolean(channelEnabled[channel.channelId])
            const fields = channelFields[channel.channelId] ?? emptyChannelFields()
            const issues = channelValidation(fields, enabled)
            const controlsDisabled = !channel.available || !enabled
            return (
              <details className="rounded-xl border border-border bg-bg-base" key={channel.channelId} open={enabled}>
                <summary className="flex cursor-pointer list-none flex-wrap items-center gap-3 p-4">
                  <span aria-hidden="true">▾</span>
                  <h3 className="font-semibold text-text-base">{formatChannelDisplayName(channel.channelId, { showInstance: true })}</h3>
                  {!channel.available && <span className="fh-badge fh-badge-neutral">{channel.implementationState === 'coming_soon' ? translate('sources:sourceConfiguration.comingSoon') : translate('common:status.unavailable')}</span>}
                  <label className="fh-inline-check ms-auto" onClick={event => event.stopPropagation()}>
                    <input
                      type="checkbox"
                      checked={enabled}
                      disabled={!channel.available}
                      onChange={() => toggleChannel(channel.channelId)}
                    />
                    {enabled ? translate('sources:sourceConfiguration.enabled') : translate('sources:sourceConfiguration.disabled')}
                  </label>
                </summary>
                <div className="border-t border-border p-4">
                  <div className="mb-4 flex flex-wrap items-end gap-2">
                    <label className="fh-field-label min-w-[220px]">
                      {translate('sources:sourceConfiguration.worksheetOverride')}
                      <input
                        className="fh-input mt-1"
                        disabled={controlsDisabled}
                        value={channelWorksheets[channel.channelId] ?? ''}
                        onChange={event => setChannelWorksheets(current => ({ ...current, [channel.channelId]: event.target.value }))}
                        placeholder={translate('sources:sourceConfiguration.useSourceWorksheet')}
                      />
                    </label>
                    <label className="fh-field-label min-w-[220px]">
                      {translate('sources:sourceConfiguration.copyMappingFrom')}
                      <select className="fh-input mt-1" disabled={controlsDisabled} value={copyFrom[channel.channelId] ?? ''} onChange={event => setCopyFrom(current => ({ ...current, [channel.channelId]: event.target.value }))}>
                        <option value="">{translate('sources:sourceConfiguration.selectChannel')}</option>
                        {configuredChannelIds.filter(item => item !== channel.channelId).map(item => (
                          <option key={item} value={item}>{formatChannelDisplayName(item, { showInstance: true })}</option>
                        ))}
                      </select>
                    </label>
                    <button className="fh-button-secondary fh-button-sm" type="button" disabled={controlsDisabled || !copyFrom[channel.channelId]} onClick={() => copyMapping(channel.channelId)}>
                      {translate('sources:sourceConfiguration.copyMapping')}
                    </button>
                    <button className="fh-button-secondary fh-button-sm" type="button" disabled={controlsDisabled} onClick={() => clearMapping(channel.channelId)}>
                      {translate('sources:sourceConfiguration.clearMapping')}
                    </button>
                  </div>
                  <div className="grid gap-3">
                    {CHANNEL_FIELDS.map(([field, labelKey]) => (
                      <label className="grid gap-1" key={field}>
                        <span className="fh-field-label">{translate(labelKey)}</span>
                        <MappingControl
                          mapping={fields.find(item => item.field === field)!}
                          disabled={controlsDisabled}
                          allowInternalColumnId={source.sourceKind === 'flowhub_sheet'}
                          onChange={value => updateChannelField(channel.channelId, field, value)}
                        />
                      </label>
                    ))}
                  </div>
                  {issues.length > 0 && (
                    <ul className="fh-alert-warning mt-4 list-disc ps-5" aria-label={translate('sources:sourceConfiguration.mappingValidation')}>
                      {issues.map(issue => <li key={issue}>{issue}</li>)}
                    </ul>
                  )}
                </div>
              </details>
            )
          })}
        </div>

        <div>
          <h2 className="fh-section-title">{translate('sources:sourceConfiguration.valueHandling')}</h2>
          <p className="fh-text-caption">{translate('sources:sourceConfiguration.eachSpecialValueIsInterpretedExplicitlyCurrency')}</p>
        </div>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {Object.entries(POLICY_OPTIONS).map(([key, options]) => (
            <label className="fh-field-label capitalize" key={key}>
              {translate(`sources:sourceConfiguration.valueType.${key}`)}
              <select className="fh-input mt-1" value={valuePolicy[key]} onChange={event => setValuePolicy(current => ({ ...current, [key]: event.target.value }))}>
                {options.map(([value, labelKey]) => <option value={value} key={value}>{translate(labelKey)}</option>)}
              </select>
            </label>
          ))}
        </div>
        <div className="flex justify-end">
          <button className="fh-button-primary" type="button" disabled={saving} onClick={() => void save()}>
            <Icon name="save" /> {saving ? translate('sources:sourceConfiguration.saving') : translate('sources:sourceConfiguration.saveMappingRevision')}
          </button>
        </div>
      </section>

      <section className="fh-card mt-5" aria-label={translate('sources:sourceConfiguration.sourcePreview')}>
        <div className="fh-panel-header">
          <div>
            <h2 className="fh-section-title">{translate('sources:sourceConfiguration.sourcePreview')}</h2>
            <p className="fh-text-caption">{translate('sources:sourceConfiguration.previewShowsIndependentChannelValues')}</p>
          </div>
          <button className="fh-button-secondary" type="button" disabled={!source.mapping || previewing} onClick={() => void loadPreview()}>
            {previewing ? translate('sources:sourceConfiguration.loading') : translate('sources:sourceConfiguration.previewRecognizedRows')}
          </button>
        </div>
        {preview && (
          <>
            <div className="grid grid-cols-2 gap-3 border-t border-border p-4">
              <div><strong className="text-text-base">{preview.recognized}</strong><span className="fh-text-caption ms-2">{translate('sources:sourceConfiguration.recognized')}</span></div>
              <div><strong className="text-text-base">{preview.ignored}</strong><span className="fh-text-caption ms-2">{translate('sources:sourceConfiguration.ignored')}</span></div>
            </div>
            <div className="divide-y divide-border border-t border-border">
              {preview.items.slice(0, 25).map(item => (
                <article className="p-4" key={item.rowKey}>
                  <div className="flex flex-wrap items-center gap-3">
                    <span className="fh-badge fh-badge-neutral">{translate('sources:sourceConfiguration.row')} {item.rowNumber}</span>
                    <strong className="text-text-base">{item.sourceProduct.name || item.sourceProduct.source_key || '—'}</strong>
                    <span className="fh-text-caption">{item.recognized ? translate('sources:sourceConfiguration.recognized') : translate('sources:sourceConfiguration.ignoredRow')}</span>
                  </div>
                  <div className="mt-3 grid gap-2 lg:grid-cols-3">
                    {item.channels.map(channel => (
                      <div className="rounded-lg border border-border bg-bg-subtle p-3" key={channel.channelId}>
                        <strong className="text-text-base">{formatChannelDisplayName(channel.channelId, { showInstance: true })}</strong>
                        <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 fh-text-caption">
                          {CHANNEL_FIELDS.map(([field, labelKey]) => (
                            <div className="contents" key={field}>
                              <dt>{translate(labelKey)}</dt>
                              <dd className="font-medium text-text-base">{channel.fields[field] ?? translate('sources:sourceConfiguration.notConfigured')}</dd>
                            </div>
                          ))}
                        </dl>
                      </div>
                    ))}
                  </div>
                </article>
              ))}
            </div>
          </>
        )}
      </section>
    </PageShell>
  )
}
