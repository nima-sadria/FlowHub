import { useEffect, useMemo, useState, type ReactNode } from 'react'
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
  SourcePreview,
  SourceProfile,
  SourceWorksheetRule,
} from '../features/sourceWorkspace/types'
import { translate } from '../i18n'
import { localizedApiError } from '../i18n/errors'
import { useNotification } from '../notifications/NotificationProvider'
import { ResourceOptionGroups, ResourceSectionList, ResourceStateBadge } from '../components/ResourceOrdering'
import {
  orderRelatedItems,
  prepareResourceCollection,
  sourceChannelSignals,
} from '../features/resourceOrdering/resourceOrdering'
import WorksheetRuleEditor, {
  createWorksheetRule,
  emptyChannelFields as emptyWorksheetChannelFields,
  type WorksheetCopyIntent,
} from './sourceConfiguration/WorksheetRuleEditor'

interface PendingWorksheetCopy {
  intent: WorksheetCopyIntent
  destinationWorksheetNames: string[]
}

function ConfigurationSection({ title, description, defaultOpen = false, children }: { title: string; description: string; defaultOpen?: boolean; children: ReactNode }) {
  const [open, setOpen] = useState(defaultOpen)
  return <details className="fh-card group" open={open} onToggle={event => {
    const next = event.currentTarget.open
    if (next !== open) setOpen(next)
  }}>
    <summary className="fh-panel-header cursor-pointer list-none">
      <div><h2 className="fh-section-title">{title}</h2><p className="fh-text-caption">{description}</p></div>
      <Icon name="next" className="transition-transform group-open:rotate-90" />
    </summary>
    <div className="border-t border-border p-4">{children}</div>
  </details>
}

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

const REFERENCE_TYPE_LABELS: Record<ReferenceType, string> = {
  disabled: 'sources:sourceConfiguration.disabled',
  column_letter: 'sources:sourceConfiguration.columnLetter',
  header_name: 'sources:sourceConfiguration.exactHeader',
  column_id: 'sources:sourceConfiguration.internalColumnId',
}

const emptyMapping = (field: string, required = false): FieldMapping => ({
  field,
  referenceType: 'disabled',
  referenceValue: null,
  required,
})

const emptyChannelFields = (): FieldMapping[] => CHANNEL_FIELDS.map(([field]) => emptyMapping(field))

function fieldDisplayName(field: string): string {
  const sourceDefinition = SOURCE_FIELDS.find(([candidate]) => candidate === field)
  const channelDefinition = CHANNEL_FIELDS.find(([candidate]) => candidate === field)
  const translationKey = sourceDefinition?.[1] ?? channelDefinition?.[1]
  return translationKey ? translate(translationKey) : field
}

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
          aria-label={translate('sources:sourceConfiguration.referenceType', { field: fieldDisplayName(mapping.field) })}
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
          aria-label={translate('sources:sourceConfiguration.columnReference', { field: fieldDisplayName(mapping.field) })}
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
        first: fieldDisplayName(previous),
        second: fieldDisplayName(field.field),
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
  const [worksheetRuleMode, setWorksheetRuleMode] = useState<'shared' | 'per_worksheet'>('shared')
  const [duplicateProductPolicy, setDuplicateProductPolicy] = useState<'block' | 'last_sheet_wins'>('block')
  const [worksheetRules, setWorksheetRules] = useState<SourceWorksheetRule[]>([])
  const [detectedWorksheets, setDetectedWorksheets] = useState<Array<{ name: string; rowCount: number }>>([])
  const [selectedWorksheetNames, setSelectedWorksheetNames] = useState<string[]>([])
  const [newWorksheetName, setNewWorksheetName] = useState('')
  const [detectingWorksheets, setDetectingWorksheets] = useState(false)
  const [dataStartRow, setDataStartRow] = useState(1)
  const [worksheetName, setWorksheetName] = useState('Sheet1')
  const [valuePolicy, setValuePolicy] = useState<Record<string, string>>(DEFAULT_VALUE_POLICY)
  const [preview, setPreview] = useState<SourcePreview | null>(null)
  const [previewing, setPreviewing] = useState(false)
  const [saving, setSaving] = useState(false)
  const [previewFilter, setPreviewFilter] = useState<'all' | 'ready' | 'attention'>('all')
  const [previewIndex, setPreviewIndex] = useState(0)
  const [selectedWorksheetRules, setSelectedWorksheetRules] = useState<string[]>([])
  const [expandedWorksheet, setExpandedWorksheet] = useState<string | null>(null)
  const [pendingCopy, setPendingCopy] = useState<PendingWorksheetCopy | null>(null)
  const [pendingSharedChannelCopy, setPendingSharedChannelCopy] = useState<{ sourceChannelId: string; targetChannelId: string } | null>(null)
  const [baselineFingerprint, setBaselineFingerprint] = useState<string | null>(null)
  const [connectionChecking, setConnectionChecking] = useState(false)

  useEffect(() => {
    let active = true
    Promise.all([sourceWorkspaceApi.source(sourceId), sourceWorkspaceApi.channels()]).then(([loaded, available]) => {
      if (!active) return
      setSource(loaded)
      setChannels(available.items)
      setDataStartRow(loaded.mapping?.dataStartRow ?? loaded.dataStartRow)
      setWorksheetMode(loaded.mapping?.worksheetMode ?? loaded.worksheetMode)
      setWorksheetName(loaded.mapping?.worksheetName ?? loaded.worksheetName ?? 'Sheet1')
      setSelectedWorksheetNames(
        loaded.mapping?.selectedWorksheetNames?.length
          ? loaded.mapping.selectedWorksheetNames
          : loaded.mapping?.worksheetMode === 'selected' && loaded.mapping.worksheetName
            ? [loaded.mapping.worksheetName]
            : loaded.worksheetMode === 'selected' && loaded.worksheetName
              ? [loaded.worksheetName]
              : [],
      )
      setWorksheetRuleMode(loaded.mapping?.worksheetRuleMode ?? 'shared')
      setDuplicateProductPolicy(loaded.mapping?.duplicateProductPolicy ?? 'block')
      const loadedWorksheetRules = (loaded.mapping?.worksheetRules ?? []).map(rule => ({
        ...rule,
        valuePolicy: { ...DEFAULT_VALUE_POLICY, ...rule.valuePolicy },
        sourceFields: SOURCE_FIELDS.map(([field, _label, required]) => rule.sourceFields.find(item => item.field === field) ?? emptyMapping(field, required)),
        channels: rule.channels.map(channel => ({ ...channel, fields: CHANNEL_FIELDS.map(([field]) => channel.fields.find(item => item.field === field) ?? emptyMapping(field)) })),
      }))
      setWorksheetRules(loadedWorksheetRules)
      setSelectedWorksheetRules(loadedWorksheetRules.filter(rule => rule.enabled).map(rule => rule.worksheetName))
      setExpandedWorksheet(loadedWorksheetRules.find(rule => rule.enabled)?.worksheetName ?? null)
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
      setBaselineFingerprint(null)
    }).catch(error => {
      notify.error({
        title: translate('sources:sourceConfiguration.sourceConfigurationUnavailable'),
        description: localizedApiError(error, 'sources:sourceConfiguration.tryAgain'),
      })
    })
    return () => { active = false }
  }, [notify, sourceId])

  const configurationFingerprint = useMemo(() => JSON.stringify({
    sourceFields,
    channelFields,
    channelWorksheets,
    channelEnabled,
    configuredChannelIds,
    worksheetMode,
    worksheetRuleMode,
    duplicateProductPolicy,
    worksheetRules,
    selectedWorksheetNames,
    dataStartRow,
    worksheetName,
    valuePolicy,
  }), [channelEnabled, channelFields, channelWorksheets, configuredChannelIds, dataStartRow, duplicateProductPolicy, selectedWorksheetNames, sourceFields, valuePolicy, worksheetMode, worksheetName, worksheetRuleMode, worksheetRules])
  const dirty = baselineFingerprint !== null && baselineFingerprint !== configurationFingerprint

  useEffect(() => {
    if (source && baselineFingerprint === null) setBaselineFingerprint(configurationFingerprint)
  }, [baselineFingerprint, configurationFingerprint, source])

  useEffect(() => {
    if (!dirty) return
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault()
      event.returnValue = ''
    }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [dirty])

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
    setPendingSharedChannelCopy({ sourceChannelId, targetChannelId: channelId })
  }

  function applySharedChannelCopy() {
    if (!pendingSharedChannelCopy) return
    const { sourceChannelId, targetChannelId } = pendingSharedChannelCopy
    ensureConfigured(targetChannelId)
    setChannelFields(current => ({
      ...current,
      [targetChannelId]: current[sourceChannelId].map(item => ({ ...item })),
    }))
    setPendingSharedChannelCopy(null)
  }

  function changeWorksheetRuleMode(mode: 'shared' | 'per_worksheet') {
    setWorksheetRuleMode(mode)
    if (mode === 'per_worksheet' && worksheetRules.length === 0) {
      const detectedWorksheetNames = detectedWorksheets.map(item => item.name)
      const worksheetNames = detectedWorksheetNames.length > 0
        ? detectedWorksheetNames
        : selectedWorksheetNames.length > 0
          ? selectedWorksheetNames
          : [worksheetName || 'Sheet1']
      const selectedNames = new Set(selectedWorksheetNames)
      setWorksheetRules(worksheetNames.map(name => ({
        ...createWorksheetRule(name),
        enabled: detectedWorksheetNames.length === 0 || selectedNames.has(name),
        dataStartRow,
        valuePolicy: { ...valuePolicy },
        sourceFields: sourceFields.map(item => ({ ...item })),
        channels: configuredChannelIds.map(channelId => ({
          channelId,
          worksheetName: name,
          enabled: Boolean(channelEnabled[channelId]),
          fields: (channelFields[channelId] ?? emptyChannelFields()).map(item => ({ ...item })),
        })),
      })))
      const enabledWorksheetNames = worksheetNames.filter(name => detectedWorksheetNames.length === 0 || selectedNames.has(name))
      setSelectedWorksheetRules(enabledWorksheetNames)
      setExpandedWorksheet(enabledWorksheetNames[0] ?? worksheetNames[0] ?? null)
    }
  }

  function addWorksheetRule() {
    const name = newWorksheetName.trim()
    if (!name || worksheetRules.some(item => item.worksheetName === name)) return
    setWorksheetRules(current => [...current, createWorksheetRule(name)])
    setNewWorksheetName('')
  }

  function selectAllWorksheetRules() {
    setSelectedWorksheetRules(worksheetRules.map(rule => rule.worksheetName))
  }

  function setSelectedWorksheetRuleEnabled(enabled: boolean) {
    const selected = new Set(selectedWorksheetRules)
    setWorksheetRules(current => current.map(rule => selected.has(rule.worksheetName) ? { ...rule, enabled } : rule))
  }

  function requestWorksheetCopy(intent: WorksheetCopyIntent) {
    const destinations = worksheetRules
      .filter(rule => rule.worksheetName !== intent.worksheetName)
      .map(rule => rule.worksheetName)
    setPendingCopy({ intent, destinationWorksheetNames: destinations })
  }

  function applyWorksheetCopy() {
    if (!pendingCopy) return
    const { intent } = pendingCopy
    if (intent.kind === 'channel_to_channel') {
      setWorksheetRules(current => current.map(rule => {
        if (rule.worksheetName !== intent.worksheetName) return rule
        const sourceChannel = rule.channels.find(channel => channel.channelId === intent.sourceChannelId)
        if (!sourceChannel) return rule
        const targetChannel = rule.channels.find(channel => channel.channelId === intent.targetChannelId) ?? {
          channelId: intent.targetChannelId,
          worksheetName: rule.worksheetName,
          enabled: false,
          fields: emptyWorksheetChannelFields(),
        }
        return {
          ...rule,
          channels: [
            ...rule.channels.filter(channel => channel.channelId !== intent.targetChannelId),
            { ...targetChannel, fields: sourceChannel.fields.map(field => ({ ...field })) },
          ],
        }
      }))
      setPendingCopy(null)
      return
    }
    const destinations = new Set(pendingCopy.destinationWorksheetNames)
    const sourceRule = worksheetRules.find(rule => rule.worksheetName === intent.worksheetName)
    if (!sourceRule) return
    setWorksheetRules(current => current.map(rule => {
      if (!destinations.has(rule.worksheetName)) return rule
      if (intent.kind === 'shared_fields') return { ...rule, sourceFields: sourceRule.sourceFields.map(field => ({ ...field })) }
      const sourceChannel = sourceRule.channels.find(channel => channel.channelId === intent.channelId)
      if (!sourceChannel) return rule
      const targetChannel = rule.channels.find(channel => channel.channelId === intent.channelId) ?? {
        channelId: intent.channelId,
        worksheetName: rule.worksheetName,
        enabled: sourceChannel.enabled,
        fields: emptyWorksheetChannelFields(),
      }
      return {
        ...rule,
        channels: [
          ...rule.channels.filter(channel => channel.channelId !== intent.channelId),
          { ...targetChannel, fields: sourceChannel.fields.map(field => ({ ...field })) },
        ],
      }
    }))
    setPendingCopy(null)
  }

  async function testConnection() {
    setConnectionChecking(true)
    try {
      const result = await sourceWorkspaceApi.worksheets(sourceId)
      setDetectedWorksheets(result.items)
      notify.success({ title: translate('sources:sourceConfiguration.connectionReady'), description: translate('sources:sourceConfiguration.worksheetsDetected', { count: result.items.length }) })
    } catch (error) {
      notify.error({ title: translate('sources:sourceConfiguration.connectionCheckFailed'), description: localizedApiError(error, 'sources:sourceConfiguration.tryAgain') })
    } finally {
      setConnectionChecking(false)
    }
  }

  function closeConfiguration() {
    if (dirty && !window.confirm(translate('sources:sourceConfiguration.discardUnsavedChanges'))) return
    navigate('/sources')
  }

  async function detectWorksheets() {
    setDetectingWorksheets(true)
    try {
      const result = await sourceWorkspaceApi.worksheets(sourceId)
      setDetectedWorksheets(result.items)
      if (worksheetRuleMode === 'shared' && worksheetMode === 'selected') {
        setSelectedWorksheetNames(current => {
          const available = new Set(result.items.map(item => item.name))
          const preserved = current.filter(name => available.has(name))
          if (preserved.length) return preserved
          if (worksheetName && available.has(worksheetName)) return [worksheetName]
          return result.items.map(item => item.name)
        })
      }
      if (worksheetRuleMode === 'per_worksheet') {
        setWorksheetRules(current => {
          const existing = new Set(current.map(item => item.worksheetName))
          const additions = result.items
            .filter(item => !existing.has(item.name))
            .map(item => ({ ...createWorksheetRule(item.name), enabled: current.length === 0 && result.items.length === 1 }))
          return [...current, ...additions]
        })
        setSelectedWorksheetRules(current => current.filter(name => result.items.some(item => item.name === name)))
        setExpandedWorksheet(current => current ?? result.items[0]?.name ?? null)
      }
    } catch (error) {
      notify.error({ title: translate('sources:sourceConfiguration.worksheetDetectionFailed'), description: localizedApiError(error, 'sources:sourceConfiguration.tryAgain') })
    } finally {
      setDetectingWorksheets(false)
    }
  }

  async function save() {
    if (!source) return
    setSaving(true)
    try {
      await sourceWorkspaceApi.saveMapping(source.id, {
        expected_source_version: source.version,
        worksheet_mode: worksheetRuleMode === 'per_worksheet' ? 'all' : worksheetMode,
        worksheet_name: worksheetRuleMode === 'shared' && worksheetMode === 'selected' && selectedWorksheetNames.length === 1 ? selectedWorksheetNames[0] : null,
        selected_worksheet_names: worksheetRuleMode === 'shared' && worksheetMode === 'selected' ? selectedWorksheetNames : [],
        data_start_row: worksheetRuleMode === 'shared' ? dataStartRow : 1,
        source_fields: (worksheetRuleMode === 'shared' ? sourceFields : []).map(item => ({
          field: item.field,
          reference_type: item.referenceType,
          reference_value: item.referenceValue,
          required: item.required ?? false,
        })),
        channel_mappings: (worksheetRuleMode === 'shared' ? configuredChannelIds : []).map(channelId => ({
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
        worksheet_rule_mode: worksheetRuleMode,
        duplicate_product_policy: duplicateProductPolicy,
        worksheet_rules: worksheetRuleMode === 'per_worksheet' ? worksheetRules.map(rule => ({
          worksheet_name: rule.worksheetName,
          enabled: rule.enabled,
          data_start_row: rule.dataStartRow,
          value_policy: rule.valuePolicy,
          source_fields: rule.sourceFields.map(item => ({ field: item.field, reference_type: item.referenceType, reference_value: item.referenceValue, required: item.required ?? false })),
          channel_mappings: rule.channels.map(channel => ({
            channel_id: channel.channelId,
            worksheet_name: rule.worksheetName,
            enabled: channel.enabled,
            fields: channel.fields.map(item => ({ field: item.field, reference_type: item.referenceType, reference_value: item.referenceValue, required: false })),
          })),
        })) : [],
      })
      notify.success({
        title: translate('sources:sourceConfiguration.sourceMappingSaved'),
        description: translate('sources:sourceConfiguration.aNewImmutableMappingRevisionWasCreated'),
      })
      setBaselineFingerprint(configurationFingerprint)
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
      setPreview(await sourceWorkspaceApi.previewSource(sourceId))
      setPreviewIndex(0)
    } catch (error) {
      notify.error({
        title: translate('sources:sourceConfiguration.sourcePreviewUnavailable'),
        description: localizedApiError(error, 'sources:sourceConfiguration.saveAValidMappingAndSheetRevision'),
      })
    } finally {
      setPreviewing(false)
    }
  }

  const channelResources = useMemo(
    () => prepareResourceCollection(channels, sourceChannelSignals),
    [channels],
  )
  const configuredChannelResources = useMemo(
    () => prepareResourceCollection(
      channels.filter(channel => configuredChannelIds.includes(channel.channelId)),
      sourceChannelSignals,
    ),
    [channels, configuredChannelIds],
  )

  if (!source) {
    return <PageShell><p className="fh-card fh-card-pad">{translate('sources:sourceConfiguration.loadingSourceConfiguration')}</p></PageShell>
  }

  const previewSummary = preview?.businessSummary ?? null
  const previewItems = preview?.items.filter(item => previewFilter === 'all' || (previewFilter === 'ready' ? item.ready : item.hasIssues)) ?? []
  const currentPreviewIndex = Math.min(previewIndex, Math.max(0, previewItems.length - 1))
  const currentPreviewItem = previewItems[currentPreviewIndex] ?? null
  const worksheetRulesValid = worksheetRules.some(rule => rule.enabled) && worksheetRules.every(rule => {
    if (!rule.enabled) return true
    const nameField = rule.sourceFields.find(field => field.field === 'name')
    return Boolean(nameField && nameField.referenceType !== 'disabled' && nameField.referenceValue?.trim())
  })
  const channelName = (channelId: string) => channelResources.ordered.find(resource => resource.id === channelId)?.displayName ?? formatChannelDisplayName(channelId, { showInstance: true })
  const displayFieldReference = (mapping: FieldMapping) => mapping.referenceType === 'disabled'
    ? translate('sources:sourceConfiguration.disabled')
    : `${translate(REFERENCE_TYPE_LABELS[mapping.referenceType])}: ${mapping.referenceValue ?? '—'}`
  const pendingWorksheetCopyFields = (() => {
    if (!pendingCopy) return [] as FieldMapping[]
    const sourceRule = worksheetRules.find(rule => rule.worksheetName === pendingCopy.intent.worksheetName)
    if (!sourceRule) return [] as FieldMapping[]
    if (pendingCopy.intent.kind === 'shared_fields') return sourceRule.sourceFields
    const sourceChannelId = pendingCopy.intent.kind === 'channel_to_channel' ? pendingCopy.intent.sourceChannelId : pendingCopy.intent.channelId
    return sourceRule.channels.find(channel => channel.channelId === sourceChannelId)?.fields ?? []
  })()

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

      <div className="mb-5 grid gap-3">
        <ConfigurationSection title={translate('sources:sourceConfiguration.section.general')} description={translate('sources:sourceConfiguration.section.generalHelp')} defaultOpen>
          <dl className="grid gap-3 sm:grid-cols-3">
            <div><dt className="fh-text-caption">{translate('sources:sourceConfiguration.sourceName')}</dt><dd className="font-medium text-text-base">{source.name}</dd></div>
            <div><dt className="fh-text-caption">{translate('sources:sourceConfiguration.sourceType')}</dt><dd className="font-medium text-text-base">{source.sourceKind === 'flowhub_sheet' ? translate('sources:sourceCenter.flowhubSheet') : source.sourceKind === 'imported_sheet' ? translate('sources:sourceCenter.importedSpreadsheet') : translate('sources:sourceCenter.linkedExternalSource')}</dd></div>
            <div><dt className="fh-text-caption">{translate('sources:sourceConfiguration.columnSetupStatus')}</dt><dd><span className={`fh-badge ${source.mapping ? 'fh-badge-success' : 'fh-badge-warning'}`}>{source.mapping ? translate('common:status.ready') : translate('sources:sourceConfiguration.notConfigured')}</span></dd></div>
          </dl>
        </ConfigurationSection>
        <ConfigurationSection title={translate('sources:sourceConfiguration.section.connection')} description={translate('sources:sourceConfiguration.section.connectionHelp')} defaultOpen>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="fh-text-caption">{source.sourceKind === 'external' ? translate('sources:sourceConfiguration.externalConnectionHelp') : translate('sources:sourceConfiguration.managedSourceConnectionHelp')}</p>
            <button className="fh-button-secondary fh-button-sm" type="button" disabled={connectionChecking} onClick={() => void testConnection()}><Icon name="testConnection" /> {connectionChecking ? translate('sources:sourceConfiguration.checkingConnection') : translate('sources:sourceConfiguration.testConnection')}</button>
          </div>
        </ConfigurationSection>
        <ConfigurationSection title={translate('sources:sourceConfiguration.section.readPolicy')} description={translate('sources:sourceConfiguration.section.readPolicyHelp')}>
          <p className="fh-text-caption">{translate('sources:sourceConfiguration.readOncePolicy')}</p>
        </ConfigurationSection>
        <ConfigurationSection title={translate('sources:sourceConfiguration.section.accessScope')} description={translate('sources:sourceConfiguration.section.accessScopeHelp')}>
          <p className="fh-text-caption">{translate('sources:sourceConfiguration.accessScopePolicy')}</p>
        </ConfigurationSection>
      </div>

      {source.legacyMapping && !source.mapping && (
        <section className="fh-alert-warning mb-5" role="status">
          <strong>{translate('sources:sourceConfiguration.legacyMappingDetected')}</strong>
          <p className="mt-1">{translate('sources:sourceConfiguration.legacyMappingAssignedToPrimaryChannel')}</p>
        </section>
      )}

      <ConfigurationSection title={translate('sources:sourceConfiguration.worksheetRules')} description={translate('sources:sourceConfiguration.worksheetRulesSectionHelp')}>
        <div className="mt-4 grid gap-3 lg:grid-cols-2">
          <label className={`rounded-xl border p-4 ${worksheetRuleMode === 'shared' ? 'border-accent bg-accent/5' : 'border-border'}`}>
            <span className="flex items-center gap-2 font-medium text-text-base"><input type="radio" name="worksheet-rule-mode" value="shared" checked={worksheetRuleMode === 'shared'} onChange={() => changeWorksheetRuleMode('shared')} />{translate('sources:sourceConfiguration.sharedWorksheetRules')}</span>
            <span className="fh-text-caption mt-2 block">{translate('sources:sourceConfiguration.sharedWorksheetRulesHelp')}</span>
          </label>
          <label className={`rounded-xl border p-4 ${worksheetRuleMode === 'per_worksheet' ? 'border-accent bg-accent/5' : 'border-border'}`}>
            <span className="flex items-center gap-2 font-medium text-text-base"><input type="radio" name="worksheet-rule-mode" value="per_worksheet" checked={worksheetRuleMode === 'per_worksheet'} onChange={() => changeWorksheetRuleMode('per_worksheet')} />{translate('sources:sourceConfiguration.separateWorksheetRules')}</span>
            <span className="fh-text-caption mt-2 block">{translate('sources:sourceConfiguration.separateWorksheetRulesHelp')}</span>
          </label>
        </div>
      </ConfigurationSection>

      <div className={`mt-3 ${worksheetRuleMode === 'per_worksheet' ? 'hidden' : ''}`}>
        <ConfigurationSection title={translate('sources:sourceConfiguration.section.workbook')} description={translate('sources:sourceConfiguration.section.workbookHelp')}>
          <div className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
          <label className="fh-field-label">
            {translate('sources:sourceConfiguration.worksheetPolicy')}
            <select className="fh-input mt-1" value={worksheetMode} onChange={event => setWorksheetMode(event.target.value as 'all' | 'selected')}>
              <option value="selected">{translate('sources:sourceConfiguration.selectedWorksheet')}</option>
              <option value="all">{translate('sources:sourceConfiguration.allWorksheets')}</option>
            </select>
          </label>
          <label className="fh-field-label">
            {translate('sources:sourceConfiguration.dataStartsAtRow')}
            <input className="fh-input mt-1" type="number" min="1" value={dataStartRow} onChange={event => setDataStartRow(Number(event.target.value))} />
          </label>
        </div>
        {worksheetMode === 'selected' && <fieldset className="rounded-xl border border-border p-4">
          <legend className="px-2 font-medium text-text-base">{translate('sources:sourceConfiguration.chooseParticipatingWorksheets')}</legend>
          <div className="mt-2 flex flex-wrap items-center gap-3">
            <button className="fh-button-secondary" type="button" disabled={detectingWorksheets} onClick={() => void detectWorksheets()}><Icon name="refresh" /> {detectingWorksheets ? translate('sources:sourceConfiguration.detectingWorksheets') : translate('sources:sourceConfiguration.detectWorksheets')}</button>
            {detectedWorksheets.length > 0 && <><button className="fh-button-secondary fh-button-sm" type="button" onClick={() => setSelectedWorksheetNames(detectedWorksheets.map(item => item.name))}>{translate('sources:sourceConfiguration.selectAll')}</button><button className="fh-button-secondary fh-button-sm" type="button" onClick={() => setSelectedWorksheetNames([])}>{translate('sources:sourceConfiguration.clearAll')}</button></>}
            {detectedWorksheets.length === 0 && <label className="fh-field-label min-w-[260px]">{translate('sources:sourceConfiguration.worksheet')}<input className="fh-input mt-1" value={worksheetName} onChange={event => { setWorksheetName(event.target.value); setSelectedWorksheetNames(event.target.value.trim() ? [event.target.value.trim()] : []) }} /></label>}
          </div>
          {detectedWorksheets.length > 0 && <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {detectedWorksheets.map(item => <label className="fh-inline-check rounded-lg border border-border p-3" key={item.name}><input type="checkbox" checked={selectedWorksheetNames.includes(item.name)} onChange={event => setSelectedWorksheetNames(current => event.target.checked ? [...new Set([...current, item.name])] : current.filter(name => name !== item.name))} /><span><strong className="block text-text-base">{item.name}</strong><small className="fh-text-caption">{translate('sources:sourceConfiguration.worksheetRowCount', { count: item.rowCount })}</small></span></label>)}
          </div>}
          {selectedWorksheetNames.length === 0 && <p className="fh-alert-warning mt-3" role="alert">{translate('sources:sourceConfiguration.selectAtLeastOneWorksheet')}</p>}
        </fieldset>}
        <p className="fh-text-caption">{translate('sources:sourceConfiguration.worksheetSellerHelp')}</p>
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
          </div>
        </ConfigurationSection>
      </div>

      <div className={`mt-5 space-y-3 ${worksheetRuleMode === 'per_worksheet' ? 'hidden' : ''}`}>
        <ConfigurationSection title={translate('sources:sourceConfiguration.section.channelColumns')} description={translate('sources:sourceConfiguration.section.channelColumnsHelp')}>
          <div className="space-y-4" aria-label={translate('sources:sourceConfiguration.channelMappings')}>
          <ResourceSectionList resources={channelResources} renderItem={orderedChannel => {
            const channel = orderedChannel.item
            const enabled = Boolean(channelEnabled[channel.channelId])
            const fields = channelFields[channel.channelId] ?? emptyChannelFields()
            const issues = channelValidation(fields, enabled)
            const controlsDisabled = !channel.available || !enabled
            const copyResources = prepareResourceCollection(
              configuredChannelResources.ordered
                .map(item => item.item)
                .filter(item => item.channelId !== channel.channelId),
              sourceChannelSignals,
            )
            return (
              <details className="rounded-xl border border-border bg-bg-base" data-channel-id={channel.channelId} key={channel.channelId} open={enabled}>
                <summary className="flex cursor-pointer list-none flex-wrap items-center gap-3 p-4">
                  <span aria-hidden="true">▾</span>
                  <h3 className="font-semibold text-text-base">{orderedChannel.displayName}</h3>
                  <ResourceStateBadge badge={orderedChannel.badge} />
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
                        <ResourceOptionGroups
                          resources={copyResources}
                          renderLabel={item => item.displayName}
                        />
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
          }} />
          </div>
        </ConfigurationSection>
        <ConfigurationSection title={translate('sources:sourceConfiguration.section.valueHandling')} description={translate('sources:sourceConfiguration.section.valueHandlingHelp')}>
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
        </ConfigurationSection>
      </div>

      {worksheetRuleMode === 'per_worksheet' && <div className="mt-5">
        <ConfigurationSection title={translate('sources:sourceConfiguration.section.worksheetColumns')} description={translate('sources:sourceConfiguration.section.worksheetColumnsHelp')}>
          <div className="space-y-4" aria-label={translate('sources:sourceConfiguration.separateWorksheetRules')}>
        <div className="flex flex-wrap items-end gap-3">
          <button className="fh-button-secondary" type="button" disabled={detectingWorksheets} onClick={() => void detectWorksheets()}><Icon name="refresh" /> {detectingWorksheets ? translate('sources:sourceConfiguration.detectingWorksheets') : translate('sources:sourceConfiguration.detectWorksheets')}</button>
          <label className="fh-field-label min-w-[260px]">{translate('sources:sourceConfiguration.worksheetNamePrompt')}<input className="fh-input mt-1" value={newWorksheetName} onChange={event => setNewWorksheetName(event.target.value)} /></label>
          <button className="fh-button-secondary" type="button" disabled={!newWorksheetName.trim() || worksheetRules.some(item => item.worksheetName === newWorksheetName.trim())} onClick={addWorksheetRule}><Icon name="add" /> {translate('sources:sourceConfiguration.addWorksheet')}</button>
          <label className="fh-field-label ms-auto min-w-[280px]">{translate('sources:sourceConfiguration.duplicateProductPolicy')}<select className="fh-input mt-1" value={duplicateProductPolicy} onChange={event => setDuplicateProductPolicy(event.target.value as 'block' | 'last_sheet_wins')}><option value="block">{translate('sources:sourceConfiguration.blockDuplicates')}</option><option value="last_sheet_wins">{translate('sources:sourceConfiguration.lastWorksheetWins')}</option></select></label>
        </div>
        {worksheetRules.length > 0 && <div className="flex flex-wrap items-center gap-2 rounded-xl border border-border bg-bg-subtle p-3" aria-label={translate('sources:sourceConfiguration.bulkWorksheetActions')}>
          <button className="fh-button-secondary fh-button-sm" type="button" onClick={selectAllWorksheetRules}>{translate('sources:sourceConfiguration.selectAll')}</button>
          <button className="fh-button-secondary fh-button-sm" type="button" onClick={() => setSelectedWorksheetRules([])}>{translate('sources:sourceConfiguration.clearAll')}</button>
          <button className="fh-button-secondary fh-button-sm" type="button" disabled={selectedWorksheetRules.length === 0} onClick={() => setSelectedWorksheetRuleEnabled(true)}>{translate('sources:sourceConfiguration.enableSelected')}</button>
          <button className="fh-button-secondary fh-button-sm" type="button" disabled={selectedWorksheetRules.length === 0} onClick={() => setSelectedWorksheetRuleEnabled(false)}>{translate('sources:sourceConfiguration.ignoreSelected')}</button>
          <span className="fh-text-caption ms-auto">{translate('sources:sourceConfiguration.selectedWorksheetCount', { count: selectedWorksheetRules.length })}</span>
        </div>}
        {duplicateProductPolicy === 'last_sheet_wins' && <p className="fh-alert-warning">{translate('sources:sourceConfiguration.lastWorksheetWinsWarning')}</p>}
        <div className="space-y-3">{worksheetRules.map((rule, index) => <WorksheetRuleEditor
          key={rule.worksheetName}
          rule={rule}
          rowCount={detectedWorksheets.find(item => item.name === rule.worksheetName)?.rowCount}
          channels={channelResources.ordered.map(item => item.item)}
          sourceKind={source.sourceKind}
          selected={selectedWorksheetRules.includes(rule.worksheetName)}
          expanded={expandedWorksheet === rule.worksheetName}
          onSelectedChange={selected => setSelectedWorksheetRules(current => selected ? [...new Set([...current, rule.worksheetName])] : current.filter(name => name !== rule.worksheetName))}
          onExpandedChange={expanded => setExpandedWorksheet(expanded ? rule.worksheetName : null)}
          onChange={next => setWorksheetRules(current => current.map((item, itemIndex) => itemIndex === index ? next : item))}
          onRemove={() => setWorksheetRules(current => current.filter((_item, itemIndex) => itemIndex !== index))}
          onRequestCopy={requestWorksheetCopy}
        />)}</div>
        {worksheetRules.length === 0 && <p className="fh-alert-warning">{translate('sources:sourceConfiguration.addAtLeastOneWorksheet')}</p>}
          </div>
        </ConfigurationSection>
      </div>}

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
            {previewSummary && <div className="grid grid-cols-2 gap-4 border-t border-border p-4 xl:grid-cols-4">
              <button className="fh-stat-card text-start" type="button" onClick={() => { setPreviewFilter('all'); setPreviewIndex(0) }}><span className="fh-text-caption">{translate('sources:sourceConfiguration.productsFound')}</span><strong className="mt-2 block text-2xl">{previewSummary.productsFound}</strong></button>
              <button className="fh-stat-card text-start" type="button" onClick={() => { setPreviewFilter('ready'); setPreviewIndex(0) }}><span className="fh-text-caption">{translate('sources:sourceConfiguration.productsReady')}</span><strong className="mt-2 block text-2xl">{previewSummary.productsReady}</strong></button>
              <div className="fh-stat-card"><span className="fh-text-caption">{translate('sources:sourceConfiguration.productsWithPriceChanges')}</span><strong className="mt-2 block text-2xl">{previewSummary.priceChanges ?? '—'}</strong>{previewSummary.priceChanges == null && <small className="fh-text-caption mt-1 block">{translate('sources:sourceConfiguration.calculatedInWorkspace')}</small>}</div>
              <div className="fh-stat-card"><span className="fh-text-caption">{translate('sources:sourceConfiguration.productsWithStockChanges')}</span><strong className="mt-2 block text-2xl">{previewSummary.stockChanges ?? '—'}</strong>{previewSummary.stockChanges == null && <small className="fh-text-caption mt-1 block">{translate('sources:sourceConfiguration.calculatedInWorkspace')}</small>}</div>
              <div className="fh-stat-card"><span className="fh-text-caption">{translate('sources:sourceConfiguration.unchangedProducts')}</span><strong className="mt-2 block text-2xl">{previewSummary.unchanged ?? '—'}</strong>{previewSummary.unchanged == null && <small className="fh-text-caption mt-1 block">{translate('sources:sourceConfiguration.calculatedInWorkspace')}</small>}</div>
              <button className="fh-stat-card text-start" type="button" onClick={() => { setPreviewFilter('attention'); setPreviewIndex(0) }}><span className="fh-text-caption">{translate('sources:sourceConfiguration.productsNeedingAttention')}</span><strong className="mt-2 block text-2xl">{previewSummary.needsAttention}</strong></button>
              <div className="fh-stat-card"><span className="fh-text-caption">{translate('sources:sourceConfiguration.channelsReady')}</span><strong className="mt-2 block text-2xl">{previewSummary.channelsReady}</strong></div>
              <div className="fh-stat-card"><span className="fh-text-caption">{translate('sources:sourceConfiguration.channelsNotConfigured')}</span><strong className="mt-2 block text-2xl">{previewSummary.channelsNotConfigured}</strong></div>
            </div>}
            <div className="border-t border-border">
              <div className="flex flex-wrap items-center gap-2 border-b border-border p-3">
                <button className="fh-button-secondary fh-button-sm" type="button" disabled={currentPreviewIndex === 0} onClick={() => setPreviewIndex(current => Math.max(0, current - 1))}><Icon name="previous" /> {translate('sources:sourceConfiguration.previousSampleRow')}</button>
                <button className="fh-button-secondary fh-button-sm" type="button" disabled={currentPreviewIndex >= previewItems.length - 1} onClick={() => setPreviewIndex(current => Math.min(previewItems.length - 1, current + 1))}>{translate('sources:sourceConfiguration.nextSampleRow')} <Icon name="next" /></button>
                <label className="fh-inline-check ms-auto"><input type="checkbox" checked={previewFilter === 'attention'} onChange={event => { setPreviewFilter(event.target.checked ? 'attention' : 'all'); setPreviewIndex(0) }} />{translate('sources:sourceConfiguration.showOnlyProblems')}</label>
                <span className="fh-text-caption">{previewItems.length > 0 ? translate('sources:sourceConfiguration.samplePosition', { current: currentPreviewIndex + 1, total: previewItems.length }) : translate('sources:sourceConfiguration.noPreviewRows')}</span>
              </div>
              {currentPreviewItem && (() => {
                const item = currentPreviewItem
                return <article className="p-4" key={item.rowKey}>
                  <div className="flex flex-wrap items-center gap-3">
                    <span className="fh-badge fh-badge-neutral">{translate('sources:sourceConfiguration.worksheet')}: {item.worksheetName}</span>
                    <span className="fh-badge fh-badge-neutral">{translate('sources:sourceConfiguration.row')} {item.rowNumber}</span>
                    <strong className="text-text-base">{String(item.sourceProduct.name || item.sourceProduct.source_key || '—')}</strong>
                    <span className="fh-text-caption">{item.ready
                      ? translate('common:status.ready')
                      : item.hasIssues
                        ? translate('sources:sourceConfiguration.productsNeedingAttention')
                        : translate('sources:sourceConfiguration.ignoredRow')}</span>
                  </div>
                  <div className="mt-3 grid gap-2 lg:grid-cols-3">
                    {orderRelatedItems(item.channels, channelResources, channel => channel.channelId).map(channel => (
                      <div className="rounded-lg border border-border bg-bg-subtle p-3" key={channel.channelId}>
                        <strong className="text-text-base">{channelResources.ordered.find(resource => resource.id === channel.channelId)?.displayName ?? formatChannelDisplayName(channel.channelId, { showInstance: true })}</strong>
                        <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 fh-text-caption">
                          {CHANNEL_FIELDS.map(([field, labelKey]) => (
                            <div className="contents" key={field}>
                              <dt>{translate(labelKey)}</dt>
                              <dd className="font-medium text-text-base">{String(channel.fields[field] ?? translate('sources:sourceConfiguration.notConfigured'))}</dd>
                            </div>
                          ))}
                        </dl>
                      </div>
                    ))}
                  </div>
                </article>
              })()}
            </div>
            <details className="border-t border-border p-4"><summary className="cursor-pointer fh-text-caption">{translate('sources:sourceConfiguration.technicalDetails')}</summary><p className="fh-text-caption mt-2">{translate('sources:sourceConfiguration.recognized')}: {preview.recognized} · {translate('sources:sourceConfiguration.ignored')}: {preview.ignored}</p></details>
          </>
        )}
      </section>

      <div className="sticky bottom-3 z-30 mt-5 flex flex-wrap items-center gap-3 rounded-xl border border-border bg-bg-base/95 p-3 shadow-lg backdrop-blur" data-testid="source-configuration-actions">
        <span className={`fh-badge ${dirty ? 'fh-badge-warning' : 'fh-badge-success'}`}>{dirty ? translate('sources:sourceConfiguration.unsavedChanges') : translate('sources:sourceConfiguration.allChangesSaved')}</span>
        <span className="fh-text-caption">{translate('sources:sourceConfiguration.savedAsImmutableRevision')}</span>
        <div className="ms-auto flex flex-wrap gap-2">
          <button className="fh-button-secondary" type="button" disabled={connectionChecking} onClick={() => void testConnection()}><Icon name="testConnection" /> {connectionChecking ? translate('sources:sourceConfiguration.checkingConnection') : translate('sources:sourceConfiguration.testConnection')}</button>
          <button className="fh-button-primary" type="button" disabled={saving || (worksheetRuleMode === 'shared' ? worksheetMode === 'selected' && selectedWorksheetNames.length === 0 : !worksheetRulesValid)} onClick={() => void save()}><Icon name="save" /> {saving ? translate('sources:sourceConfiguration.saving') : translate('sources:sourceConfiguration.saveMappingRevision')}</button>
          <button className="fh-button-secondary" type="button" onClick={closeConfiguration}><Icon name="close" /> {translate('sources:sourceConfiguration.close')}</button>
        </div>
      </div>

      {pendingSharedChannelCopy && <div className="fixed inset-0 z-50 grid place-items-center bg-black/50 p-4" role="dialog" aria-modal="true" aria-labelledby="copy-channel-title">
        <div className="fh-card fh-card-pad w-full max-w-xl">
          <h2 className="fh-page-title" id="copy-channel-title">{translate('sources:sourceConfiguration.copyChannelSettings')}</h2>
          <p className="mt-2 fh-text-caption">{translate('sources:sourceConfiguration.copyChannelPreview', { source: channelName(pendingSharedChannelCopy.sourceChannelId), destination: channelName(pendingSharedChannelCopy.targetChannelId) })}</p>
          <dl className="mt-4 grid gap-2 rounded-xl border border-border bg-bg-subtle p-3 sm:grid-cols-2">{(channelFields[pendingSharedChannelCopy.sourceChannelId] ?? []).map(field => <div key={field.field}><dt className="fh-text-caption">{fieldDisplayName(field.field)}</dt><dd className="font-medium text-text-base">{displayFieldReference(field)}</dd></div>)}</dl>
          <p className="fh-alert-warning mt-4">{translate('sources:sourceConfiguration.copyNeverChangesTechnicalChannelIdentity')}</p>
          <div className="mt-5 flex justify-end gap-2"><button className="fh-button-secondary" type="button" onClick={() => setPendingSharedChannelCopy(null)}>{translate('common:action.cancel')}</button><button className="fh-button-primary" type="button" onClick={applySharedChannelCopy}>{translate('sources:sourceConfiguration.confirmCopy')}</button></div>
        </div>
      </div>}

      {pendingCopy && <div className="fixed inset-0 z-50 grid place-items-center bg-black/50 p-4" role="dialog" aria-modal="true" aria-labelledby="copy-worksheet-title">
        <div className="fh-card fh-card-pad max-h-[90vh] w-full max-w-2xl overflow-y-auto">
          <h2 className="fh-page-title" id="copy-worksheet-title">{pendingCopy.intent.kind === 'shared_fields' ? translate('sources:sourceConfiguration.copySharedFields') : translate('sources:sourceConfiguration.copyChannelSettings')}</h2>
          <p className="mt-2 fh-text-caption">{translate('sources:sourceConfiguration.copyFromWorksheet', { worksheet: pendingCopy.intent.worksheetName })}</p>
          {pendingCopy.intent.kind === 'channel_to_channel'
            ? <p className="mt-3 text-text-base">{translate('sources:sourceConfiguration.copyChannelPreview', { source: channelName(pendingCopy.intent.sourceChannelId), destination: channelName(pendingCopy.intent.targetChannelId) })}</p>
            : <fieldset className="mt-4 rounded-xl border border-border p-3"><legend className="px-2 font-medium text-text-base">{translate('sources:sourceConfiguration.chooseDestinationWorksheets')}</legend><div className="mt-2 grid gap-2 sm:grid-cols-2">{worksheetRules.filter(rule => rule.worksheetName !== pendingCopy.intent.worksheetName).map(rule => <label className="fh-inline-check rounded-lg border border-border p-2" key={rule.worksheetName}><input type="checkbox" checked={pendingCopy.destinationWorksheetNames.includes(rule.worksheetName)} onChange={event => setPendingCopy(current => current ? { ...current, destinationWorksheetNames: event.target.checked ? [...new Set([...current.destinationWorksheetNames, rule.worksheetName])] : current.destinationWorksheetNames.filter(name => name !== rule.worksheetName) } : current)} />{rule.worksheetName}</label>)}</div></fieldset>}
          <div className="mt-4"><h3 className="fh-form-section-title">{translate('sources:sourceConfiguration.copyPreview')}</h3><dl className="mt-2 grid gap-2 rounded-xl border border-border bg-bg-subtle p-3 sm:grid-cols-2">{pendingWorksheetCopyFields.map(field => <div key={field.field}><dt className="fh-text-caption">{fieldDisplayName(field.field)}</dt><dd className="font-medium text-text-base">{displayFieldReference(field)}</dd></div>)}</dl></div>
          <p className="fh-alert-warning mt-4">{translate('sources:sourceConfiguration.copyRequiresSave')}</p>
          <div className="mt-5 flex justify-end gap-2"><button className="fh-button-secondary" type="button" onClick={() => setPendingCopy(null)}>{translate('common:action.cancel')}</button><button className="fh-button-primary" type="button" disabled={pendingCopy.intent.kind !== 'channel_to_channel' && pendingCopy.destinationWorksheetNames.length === 0} onClick={applyWorksheetCopy}>{translate('sources:sourceConfiguration.confirmCopy')}</button></div>
        </div>
      </div>}
    </PageShell>
  )
}
