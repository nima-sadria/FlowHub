import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { useNavigate, useParams } from 'react-router'
import { ApiError } from '../api/client'
import Icon from '../components/Icon'
import BrandIcon from '../components/BrandIcon'
import Badge from '../components/Badge'
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
  SmartColumnInput,
  type WorksheetCopyIntent,
} from './sourceConfiguration/WorksheetRuleEditor'
import { useAuth } from '../auth'
import { effectiveHasPerm } from '../utils/permissions'
import { WORKSPACE_PERMISSION } from '../utils/workspacePermissions'
import { useOptionalServices } from '../services/ServiceContext'
import type { CommerceTypeOption } from '../services/types'
import type { CommerceSourceConfiguration } from '../services/commerce/CommerceService'
import { ConfigPanel, DEFAULT_READ_POLICY, type ReadPolicyDraft } from './CommerceHub'

interface PendingWorksheetCopy {
  intent: WorksheetCopyIntent
  destinationWorksheetNames: string[]
}

interface SectionOpenSignal {
  ids: string[] | 'all'
  open: boolean
  token: number
}

function ConfigurationSection({ id, title, description, defaultOpen = false, openSignal, unsaved, children }: { id?: string; title: string; description?: string; defaultOpen?: boolean; openSignal?: SectionOpenSignal | null; unsaved?: boolean; children: ReactNode }) {
  const [open, setOpen] = useState(defaultOpen)
  const applies = Boolean(openSignal && (openSignal.ids === 'all' || (id && openSignal.ids.includes(id))))
  useEffect(() => {
    if (applies && openSignal) setOpen(openSignal.open)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [openSignal?.token])
  return <details id={id} className="fh-card group scroll-mt-4" open={open} onToggle={event => {
    const next = event.currentTarget.open
    if (next !== open) setOpen(next)
  }}>
    <summary className="fh-panel-header cursor-pointer list-none" title={description}>
      <div className="flex items-center gap-2">
        <h2 className="fh-section-title">{title}</h2>
        {unsaved && <span aria-hidden="true" className="fh-status-dot fh-status-dot-warning" title={translate('sources:sourceConfiguration.unsavedChanges')} />}
        {unsaved && <span className="sr-only">{translate('sources:sourceConfiguration.unsavedChanges')}</span>}
        {description && <span className="fh-help-icon" aria-label={description} role="img">i</span>}
      </div>
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

const WOOCOMMERCE_CONNECTOR_TYPE = 'woocommerce'

const DATA_MAPPING_SECTION_IDS = ['worksheet-rules', 'workbook', 'channel-columns', 'channel-columns-pw', 'worksheet-columns']
const SECTION_GROUPS: Record<string, string[]> = {
  'data-mapping': DATA_MAPPING_SECTION_IDS,
}

function isFieldFilled(field: FieldMapping | undefined): boolean {
  return Boolean(field && field.referenceType !== 'disabled' && field.referenceValue?.trim())
}

function channelMappedStatus(fields: FieldMapping[], connectorType: string | undefined): { mapped: boolean; missingFields: string[] } {
  const missingFields: string[] = []
  if (!isFieldFilled(fields.find(item => item.field === 'external_id'))) missingFields.push(fieldDisplayName('external_id'))
  if (connectorType !== WOOCOMMERCE_CONNECTOR_TYPE) {
    if (!isFieldFilled(fields.find(item => item.field === 'stock'))) missingFields.push(fieldDisplayName('stock'))
    if (!isFieldFilled(fields.find(item => item.field === 'status'))) missingFields.push(fieldDisplayName('status'))
  }
  return { mapped: missingFields.length === 0, missingFields }
}

function channelValidation(fields: FieldMapping[], enabled: boolean, connectorType: string | undefined): string[] {
  if (!enabled) return []
  const issues: string[] = []
  if (!isFieldFilled(fields.find(item => item.field === 'external_id'))) {
    issues.push(translate('sources:sourceConfiguration.productIdentifierRequired'))
  }
  if (connectorType !== WOOCOMMERCE_CONNECTOR_TYPE) {
    const stockFilled = isFieldFilled(fields.find(item => item.field === 'stock'))
    const statusFilled = isFieldFilled(fields.find(item => item.field === 'status'))
    if (!stockFilled || !statusFilled) {
      issues.push(translate('sources:sourceConfiguration.stockStatusRequired'))
    }
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

function fallbackChannelsForSource(source: SourceProfile & { mapping: SourceMapping | null }): SourceChannel[] {
  const channelIds = new Set<string>()
  source.mapping?.channels.forEach(channel => channelIds.add(channel.channelId))
  source.mapping?.worksheetRules?.forEach(rule => {
    rule.channels.forEach(channel => channelIds.add(channel.channelId))
  })
  if (source.legacyMapping?.primaryChannelId) channelIds.add(source.legacyMapping.primaryChannelId)

  return Array.from(channelIds, channelId => ({
    channelId,
    name: formatChannelDisplayName(channelId, { showInstance: true }),
    connectorType: channelId.split(':', 1)[0],
    capabilityVersion: 'unavailable',
    capabilities: {},
    enabled: false,
    implementationState: 'implemented',
    available: false,
    configured: true,
  }))
}

export default function SourceConfiguration() {
  const { sourceId = '' } = useParams()
  const commerce = useOptionalServices()?.commerce
  const navigate = useNavigate()
  const notify = useNotification()
  const { user } = useAuth()
  const canCreateWorkspace = effectiveHasPerm(user, WORKSPACE_PERMISSION.create)
  const canEditSource = effectiveHasPerm(user, WORKSPACE_PERMISSION.edit)
  const canViewActivity = effectiveHasPerm(user, WORKSPACE_PERMISSION.readAudit)
  const canViewDiagnostics = effectiveHasPerm(user, 'can_view_settings')
  const canManageCommerce = user?.is_admin === true
  const [source, setSource] = useState<(SourceProfile & { mapping: SourceMapping | null }) | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadFailure, setLoadFailure] = useState<{ notFound: boolean; reason: string } | null>(null)
  const [reloadToken, setReloadToken] = useState(0)
  const [channels, setChannels] = useState<SourceChannel[]>([])
  const [channelProfilesUnavailable, setChannelProfilesUnavailable] = useState(false)
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
  const [previewedFingerprint, setPreviewedFingerprint] = useState<string | null>(null)
  const [connectionChecking, setConnectionChecking] = useState(false)
  const [channelSetupId, setChannelSetupId] = useState<string | null>(null)
  const [channelTypes, setChannelTypes] = useState<CommerceTypeOption[]>([])
  const [channelSetupLoading, setChannelSetupLoading] = useState(false)
  const [channelSetupError, setChannelSetupError] = useState(false)
  const [externalConfig, setExternalConfig] = useState<CommerceSourceConfiguration | null>(null)
  const [readPolicy, setReadPolicy] = useState<ReadPolicyDraft>(DEFAULT_READ_POLICY)
  const [readPolicyBaseline, setReadPolicyBaseline] = useState<ReadPolicyDraft>(DEFAULT_READ_POLICY)
  const [reading, setReading] = useState(false)
  const [activeNavId, setActiveNavId] = useState('overview')
  const [sectionSignal, setSectionSignal] = useState<SectionOpenSignal | null>(null)

  useEffect(() => {
    let active = true
    setLoading(true)
    setLoadFailure(null)
    setSource(null)
    setChannelProfilesUnavailable(false)
    Promise.all([
      sourceWorkspaceApi.source(sourceId),
      sourceWorkspaceApi.channels().then(
        available => ({ ok: true as const, available }),
        () => ({ ok: false as const }),
      ),
    ]).then(([loaded, channelResult]) => {
      if (!active) return
      setSource(loaded)
      setChannels(channelResult.ok ? channelResult.available.items : fallbackChannelsForSource(loaded))
      setChannelProfilesUnavailable(!channelResult.ok)
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
      const worksheetChannelIds = [...new Set(loadedWorksheetRules.flatMap(rule => rule.channels.filter(channel => channel.enabled).map(channel => channel.channelId)))]
      if (worksheetChannelIds.length > 0) {
        setConfiguredChannelIds(worksheetChannelIds)
        setChannelEnabled(Object.fromEntries(worksheetChannelIds.map(channelId => [channelId, true])))
      }
      setSelectedWorksheetRules(loadedWorksheetRules.filter(rule => rule.enabled).map(rule => rule.worksheetName))
      setExpandedWorksheet(loadedWorksheetRules.find(rule => rule.enabled)?.worksheetName ?? null)
      setValuePolicy({ ...DEFAULT_VALUE_POLICY, ...loaded.mapping?.valuePolicy })
      if (loaded.mapping) {
        const selectedChannels = loaded.mapping.channels.length > 0
          ? loaded.mapping.channels
          : loadedWorksheetRules
              .flatMap(rule => rule.channels)
              .filter((channel, index, items) => channel.enabled && items.findIndex(item => item.channelId === channel.channelId) === index)
        setSourceFields(SOURCE_FIELDS.map(([field, _label, required]) => loaded.mapping!.sourceFields.find(item => item.field === field) ?? emptyMapping(field, required)))
        setConfiguredChannelIds(selectedChannels.map(item => item.channelId))
        setChannelEnabled(Object.fromEntries(selectedChannels.map(item => [item.channelId, item.enabled])))
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
      if (!active) return
      setLoadFailure({
        notFound: error instanceof ApiError && error.status === 404,
        reason: localizedApiError(error, 'sources:sourceConfiguration.tryAgain'),
      })
    }).finally(() => {
      if (active) setLoading(false)
    })
    return () => { active = false }
  }, [reloadToken, sourceId])

  useEffect(() => {
    if (!source || source.sourceKind !== 'external' || !source.externalSourceId || !commerce) {
      setExternalConfig(null)
      return
    }
    let active = true
    commerce.getSourceConfiguration(source.externalSourceId).then(configuration => {
      if (!active) return
      setExternalConfig(configuration)
      const loadedPolicy = configuration.settings.source_read_policy
      const policy = loadedPolicy && typeof loadedPolicy === 'object' && !Array.isArray(loadedPolicy)
        ? { ...DEFAULT_READ_POLICY, ...(loadedPolicy as Partial<ReadPolicyDraft>) }
        : DEFAULT_READ_POLICY
      setReadPolicy(policy)
      setReadPolicyBaseline(policy)
    }).catch(() => {})
    return () => { active = false }
  }, [commerce, source?.externalSourceId, source?.sourceKind, reloadToken])

  const hasReadPolicySection = Boolean(source && source.sourceKind === 'external' && source.externalSourceId)

  useEffect(() => {
    if (loading || !source || typeof IntersectionObserver === 'undefined') return
    const ids = ['overview', 'connection', 'data-mapping', 'normalization', ...(hasReadPolicySection ? ['read-policy'] : []), 'validation', 'snapshots', 'activity', 'diagnostics']
    const elements = ids
      .map(id => document.getElementById(id))
      .filter((element): element is HTMLElement => element !== null)
    if (elements.length === 0) return
    const observer = new IntersectionObserver(entries => {
      const visible = entries
        .filter(entry => entry.isIntersecting)
        .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)
      if (visible[0]?.target.id) setActiveNavId(visible[0].target.id)
    }, { rootMargin: '-112px 0px -65% 0px', threshold: [0, 1] })
    elements.forEach(element => observer.observe(element))
    return () => observer.disconnect()
  }, [loading, source, hasReadPolicySection])

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
  const readPolicyDirty = JSON.stringify(readPolicy) !== JSON.stringify(readPolicyBaseline)

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
    const channel = channels.find(item => item.channelId === channelId)
    if (channel?.configured === false) {
      if (canManageCommerce) void openChannelSetup(channelId)
      return
    }
    ensureConfigured(channelId)
    const enabled = !Boolean(channelEnabled[channelId])
    setChannelEnabled(current => ({ ...current, [channelId]: enabled }))
    setWorksheetRules(rules => rules.map(rule => {
      const existing = rule.channels.find(channel => channel.channelId === channelId)
      const next = existing
        ? { ...existing, enabled }
        : { channelId, worksheetName: rule.worksheetName, enabled, fields: emptyWorksheetChannelFields() }
      return { ...rule, channels: [...rule.channels.filter(channel => channel.channelId !== channelId), next] }
    }))
  }

  async function openChannelSetup(channelId?: string) {
    if (!canManageCommerce || !commerce) return
    setChannelSetupLoading(true)
    setChannelSetupError(false)
    setChannelSetupId(channelId ?? 'new')
    try {
      const result = await commerce.getChannelTypes()
      setChannelTypes(result.items)
    } catch {
      setChannelSetupError(true)
    } finally {
      setChannelSetupLoading(false)
    }
  }

  function closeChannelSetup() {
    setChannelSetupId(null)
    setChannelSetupError(false)
  }

  async function handleChannelSetupSaved(saved: { externalId: string }) {
    const available = await sourceWorkspaceApi.channels()
    setChannels(available.items)
    const configured = available.items.find(item => item.channelId === saved.externalId)
    if (configured?.configured) {
      ensureConfigured(saved.externalId)
      setChannelEnabled(current => ({ ...current, [saved.externalId]: true }))
    }
    closeChannelSetup()
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
    setWorksheetRules(current => [...current, {
      ...createWorksheetRule(name),
      channels: configuredChannelIds
        .filter(channelId => channelEnabled[channelId])
        .map(channelId => ({
          channelId,
          worksheetName: name,
          enabled: true,
          fields: (channelFields[channelId] ?? emptyWorksheetChannelFields()).map(field => ({ ...field })),
        })),
    }])
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

  async function validateConfiguration() {
    setConnectionChecking(true)
    try {
      if (source?.sourceKind === 'external' && source.externalSourceId && commerce) {
        const connection = await commerce.testSource(source.externalSourceId)
        if (!connection.ok) {
          notify.error({
            title: translate('sources:sourceConfiguration.connectionCheckFailed'),
            description: translate('commerce:commerceHub.pleaseVerifyYourCredentialsAndTryAgain'),
          })
          return
        }
        if (connection.spreadsheet_found !== true) {
          setDetectedWorksheets([])
          notify.success({
            title: translate('sources:sourceConfiguration.connectionReady'),
            description: translate('sources:sourceConfiguration.selectSpreadsheetBeforeWorksheetDetection'),
          })
          return
        }
      }
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

  function goToSection(id: string) {
    setActiveNavId(id)
    setSectionSignal({ ids: SECTION_GROUPS[id] ?? [id], open: true, token: Date.now() })
    document.getElementById(id)?.scrollIntoView?.({ behavior: 'smooth', block: 'start' })
  }

  function expandAllSections() {
    setSectionSignal({ ids: 'all', open: true, token: Date.now() })
  }

  function collapseAllSections() {
    setSectionSignal({ ids: 'all', open: false, token: Date.now() })
  }

  async function readNow() {
    if (!source?.externalSourceId || !commerce) return
    setReading(true)
    try {
      const result = await commerce.readSource(source.externalSourceId)
      if (result.ok) {
        notify.success({
          title: translate('commerce:commerceHub.sourceRefreshedSuccessfully'),
          description: translate('commerce:commerceHub.rowsLoaded', { count: result.rows_read }),
        })
      } else {
        notify.error({
          title: translate('commerce:commerceHub.unableToRefreshTheSource'),
          description: translate('commerce:commerceHub.pleaseTryAgain'),
        })
      }
    } catch {
      notify.error({
        title: translate('commerce:commerceHub.unableToRefreshTheSource'),
        description: translate('commerce:commerceHub.pleaseTryAgain'),
      })
    } finally {
      setReading(false)
    }
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
            .map(item => ({
              ...createWorksheetRule(item.name),
              enabled: current.length === 0 && result.items.length === 1,
              channels: configuredChannelIds
                .filter(channelId => channelEnabled[channelId])
                .map(channelId => ({
                  channelId,
                  worksheetName: item.name,
                  enabled: true,
                  fields: (channelFields[channelId] ?? emptyWorksheetChannelFields()).map(field => ({ ...field })),
                })),
            }))
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

  function mappingPayload() {
    if (!source) return null
    return {
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
    }
  }

  async function saveReadPolicy() {
    if (!source?.externalSourceId || !commerce || !externalConfig) return
    if (JSON.stringify(readPolicy) === JSON.stringify(readPolicyBaseline)) return
    try {
      await commerce.saveSource(source.externalSourceId, {
        display_name: externalConfig.display_name,
        enabled: externalConfig.enabled,
        access_mode: externalConfig.access_mode,
        description: '',
        settings: { ...externalConfig.settings, source_read_policy: readPolicy },
        secrets: {},
        currency: externalConfig.currency_profile?.currency || 'IRR',
        currency_unit: externalConfig.currency_profile?.status === 'resolved' ? externalConfig.currency_profile.unit || '' : '',
      })
      setReadPolicyBaseline(readPolicy)
    } catch {
      notify.error({
        title: translate('sources:sourceConfiguration.readPolicyNotSaved'),
        description: translate('sources:sourceConfiguration.tryAgain'),
      })
    }
  }

  async function save() {
    if (!canEditSource) return
    if (!source) return
    const payload = mappingPayload()
    if (!payload || previewedFingerprint !== configurationFingerprint) return
    setSaving(true)
    try {
      await sourceWorkspaceApi.saveMapping(source.id, payload)
      await saveReadPolicy()
      notify.success({
        title: translate('sources:sourceConfiguration.sourceMappingSaved'),
        description: translate('sources:sourceConfiguration.aNewImmutableMappingRevisionWasCreated'),
      })
      setBaselineFingerprint(configurationFingerprint)
      setPreviewedFingerprint(null)
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
    if (!canCreateWorkspace) return
    if (!source) return
    const workspace = await sourceWorkspaceApi.createWorkspace(
      source.id,
      translate('sources:sourceConfiguration.pricingWorkspaceName', { source: source.name }),
    )
    navigate(`/workspace/${workspace.id}`)
  }

  async function loadPreview() {
    if (!canEditSource) return
    const payload = mappingPayload()
    if (!payload) return
    setPreviewing(true)
    try {
      setPreview(await sourceWorkspaceApi.previewUnsavedMapping(sourceId, payload))
      setPreviewedFingerprint(configurationFingerprint)
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

  if (loading) {
    return <PageShell><p className="fh-card fh-card-pad" role="status" aria-live="polite" aria-busy="true">{translate('sources:sourceConfiguration.loadingSourceConfiguration')}</p></PageShell>
  }

  if (loadFailure || !source) {
    const notFound = loadFailure?.notFound === true
    return (
      <PageShell>
        <section className="fh-card fh-card-pad" role="alert" aria-busy="false">
          <h1 className="fh-page-title">
            {notFound
              ? translate('sources:sourceConfiguration.sourceNotFound')
              : translate('sources:sourceConfiguration.sourceConfigurationUnavailable')}
          </h1>
          <p className="fh-page-subtitle mt-2">
            {loadFailure?.reason ?? translate('sources:sourceConfiguration.loadFailureDescription')}
          </p>
          <div className="mt-5 flex flex-wrap gap-2">
            <button className="fh-button-primary" type="button" onClick={() => navigate('/sources')}>
              {translate('sources:sourceConfiguration.backToSources')}
            </button>
            {!notFound && (
              <button className="fh-button-secondary" type="button" onClick={() => setReloadToken(current => current + 1)}>
                {translate('common:action.retry')}
              </button>
            )}
            {canViewDiagnostics && (
              <button className="fh-button-secondary" type="button" onClick={() => navigate(`/diagnostics#source-${encodeURIComponent(sourceId)}`)}>
                {translate('common:action.diagnostics')}
              </button>
            )}
          </div>
        </section>
      </PageShell>
    )
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
        </div>
        {canCreateWorkspace && (
          <button className="fh-button-primary" type="button" disabled={!source.mapping} onClick={() => void createWorkspace()}>
            <Icon name="workspace" /> {translate('sources:sourceConfiguration.openWorkspace')}
          </button>
        )}
      </div>

      <div className="mb-5 flex flex-wrap items-center gap-2">
        <nav className="no-scrollbar flex snap-x flex-1 gap-2 overflow-x-auto pb-1" aria-label={translate('sources:sourceConfiguration.sourceName')}>
          {[
            ['overview', 'sources:sourceConfiguration.detail.overview', false],
            ['connection', 'sources:sourceConfiguration.detail.connection', false],
            ['data-mapping', 'sources:sourceConfiguration.detail.dataMapping', dirty],
            ['normalization', 'sources:sourceConfiguration.detail.normalization', dirty],
            ...(hasReadPolicySection ? [['read-policy', 'sources:sourceConfiguration.section.readPolicy', readPolicyDirty]] : []),
            ['validation', 'sources:sourceConfiguration.detail.validation', false],
            ['snapshots', 'sources:sourceConfiguration.detail.snapshots', false],
            ['activity', 'sources:sourceConfiguration.detail.activity', false],
            ['diagnostics', 'sources:sourceConfiguration.detail.diagnostics', false],
          ].map(([id, label, unsaved]) => {
            const active = activeNavId === id
            return (
              <button
                type="button"
                className={`${active ? 'fh-button-primary' : 'fh-button-secondary'} fh-button-sm snap-start whitespace-nowrap`}
                aria-current={active ? 'true' : undefined}
                onClick={() => goToSection(id as string)}
                key={id as string}
              >
                {translate(label as string)}
                {unsaved && <span aria-hidden="true" className="fh-status-dot fh-status-dot-warning ms-1" />}
                {unsaved && <span className="sr-only">{translate('sources:sourceConfiguration.unsavedChanges')}</span>}
              </button>
            )
          })}
        </nav>
        <div className="flex shrink-0 gap-2">
          <button type="button" className="fh-button-secondary fh-button-sm whitespace-nowrap" onClick={expandAllSections}>{translate('sources:sourceConfiguration.expandAll')}</button>
          <button type="button" className="fh-button-secondary fh-button-sm whitespace-nowrap" onClick={collapseAllSections}>{translate('sources:sourceConfiguration.collapseAll')}</button>
        </div>
      </div>

      {!canEditSource && <div className="fh-alert fh-alert-info mb-5" role="status"><Icon name="info" /><span>{translate('sources:sourceConfiguration.readOnlyPermission')}</span></div>}

      <section className="fh-card mb-5" id="overview">
        <div className="fh-panel-header">
          <div className="flex min-w-0 items-center gap-3">
            <BrandIcon identity={{ provider: source.externalSourceId, sourceType: source.sourceKind }} label={source.name} size={40} />
            <div className="min-w-0">
              <h2 className="fh-section-title">{translate('sources:sourceConfiguration.section.general')}</h2>
              <p className="fh-text-caption truncate">{translate('sources:sourceConfiguration.readOncePolicy')}</p>
            </div>
          </div>
          <div className="fh-actions">
            {canManageCommerce && source.sourceKind === 'external' && source.externalSourceId && <button className="fh-button-secondary fh-button-sm" type="button" onClick={() => navigate(`/commerce?tab=sources&resource=${encodeURIComponent(source.externalSourceId as string)}`)}><Icon name="settings" /> {translate('sources:sourceConfiguration.manageConnection')}</button>}
            {canEditSource && <button className="fh-button-secondary fh-button-sm" type="button" disabled={connectionChecking} onClick={() => void validateConfiguration()}><Icon name="testConnection" /> {connectionChecking ? translate('sources:sourceConfiguration.checkingConnection') : translate('sources:sourceConfiguration.validateConfiguration')}</button>}
          </div>
        </div>
        <dl className="grid gap-x-6 gap-y-3 border-t border-border p-4 sm:grid-cols-2 xl:grid-cols-4">
          <div><dt className="fh-text-caption">{translate('sources:sourceConfiguration.sourceName')}</dt><dd className="font-medium text-text-base">{source.name}</dd></div>
          <div><dt className="fh-text-caption">{translate('sources:sourceConfiguration.sourceType')}</dt><dd className="font-medium text-text-base">{source.sourceKind === 'flowhub_sheet' ? translate('sources:sourceCenter.flowhubSheet') : source.sourceKind === 'imported_sheet' ? translate('sources:sourceCenter.importedSpreadsheet') : translate('sources:sourceCenter.linkedExternalSource')}</dd></div>
          <div><dt className="fh-text-caption">{translate('sources:sourceConfiguration.columnSetupStatus')}</dt><dd><Badge variant={source.mapping ? 'success' : 'warning'}>{source.mapping ? translate('common:status.ready') : translate('sources:sourceConfiguration.notConfigured')}</Badge></dd></div>
          <div id="connection"><dt className="fh-text-caption">{translate('sources:sourceConfiguration.section.accessScope')}</dt><dd className="font-medium text-text-base">{translate('sources:sourceConfiguration.accessScopePolicy')}</dd></div>
        </dl>
      </section>

      {source.legacyMapping && !source.mapping && (
        <section className="fh-alert-warning mb-5" role="status">
          <strong>{translate('sources:sourceConfiguration.legacyMappingDetected')}</strong>
          <p className="mt-1">{translate('sources:sourceConfiguration.legacyMappingAssignedToPrimaryChannel')}</p>
        </section>
      )}

      <fieldset className="min-w-0" id="data-mapping" disabled={!canEditSource}>
      <ConfigurationSection id="worksheet-rules" openSignal={sectionSignal} unsaved={dirty} title={translate('sources:sourceConfiguration.worksheetRules')} description={translate('sources:sourceConfiguration.worksheetRulesSectionHelp')}>
        <div className="mt-4 grid gap-3 lg:grid-cols-2">
          <label className={`rounded-xl border p-4 ${worksheetRuleMode === 'shared' ? 'border-accent bg-accent/5' : 'border-border'}`} title={translate('sources:sourceConfiguration.sharedWorksheetRulesHelp')}>
            <span className="flex items-center gap-2 font-medium text-text-base"><input type="radio" name="worksheet-rule-mode" value="shared" checked={worksheetRuleMode === 'shared'} onChange={() => changeWorksheetRuleMode('shared')} />{translate('sources:sourceConfiguration.sharedWorksheetRules')}</span>
          </label>
          <label className={`rounded-xl border p-4 ${worksheetRuleMode === 'per_worksheet' ? 'border-accent bg-accent/5' : 'border-border'}`} title={translate('sources:sourceConfiguration.separateWorksheetRulesHelp')}>
            <span className="flex items-center gap-2 font-medium text-text-base"><input type="radio" name="worksheet-rule-mode" value="per_worksheet" checked={worksheetRuleMode === 'per_worksheet'} onChange={() => changeWorksheetRuleMode('per_worksheet')} />{translate('sources:sourceConfiguration.separateWorksheetRules')}</span>
          </label>
        </div>
      </ConfigurationSection>

      <div className={`mt-3 ${worksheetRuleMode === 'per_worksheet' ? 'hidden' : ''}`}>
        <ConfigurationSection id="workbook" openSignal={sectionSignal} unsaved={dirty} title={translate('sources:sourceConfiguration.section.workbook')} description={translate('sources:sourceConfiguration.section.workbookHelp')}>
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
        {worksheetMode === 'selected' && <fieldset className="fh-worksheet-picker">
          <legend className="px-2 font-medium text-text-base">{translate('sources:sourceConfiguration.chooseParticipatingWorksheets')}</legend>
          <div className="fh-worksheet-picker-toolbar">
            <button className="fh-button-secondary fh-button-sm" type="button" disabled={detectingWorksheets} onClick={() => void detectWorksheets()}><Icon name="refresh" /> {detectingWorksheets ? translate('sources:sourceConfiguration.detectingWorksheets') : translate('sources:sourceConfiguration.detectWorksheets')}</button>
            {detectedWorksheets.length > 0 && <><button className="fh-button-secondary fh-button-sm" type="button" onClick={() => setSelectedWorksheetNames(detectedWorksheets.map(item => item.name))}>{translate('sources:sourceConfiguration.selectAll')}</button><button className="fh-button-secondary fh-button-sm" type="button" onClick={() => setSelectedWorksheetNames([])}>{translate('sources:sourceConfiguration.clearAll')}</button></>}
            {detectedWorksheets.length === 0 && <label className="fh-field-label min-w-[260px]">{translate('sources:sourceConfiguration.worksheet')}<input className="fh-input mt-1" value={worksheetName} onChange={event => { setWorksheetName(event.target.value); setSelectedWorksheetNames(event.target.value.trim() ? [event.target.value.trim()] : []) }} /></label>}
          </div>
          {detectedWorksheets.length > 0 && <div className="fh-worksheet-picker-grid" data-testid="worksheet-picker-grid">
            {detectedWorksheets.map(item => {
              const selected = selectedWorksheetNames.includes(item.name)
              return <label className="fh-inline-check fh-worksheet-picker-item" data-selected={selected} key={item.name}><input type="checkbox" checked={selected} onChange={event => setSelectedWorksheetNames(current => event.target.checked ? [...new Set([...current, item.name])] : current.filter(name => name !== item.name))} /><span className="min-w-0"><strong className="block truncate text-text-base">{item.name}</strong><small className="fh-text-caption block truncate">{translate('sources:sourceConfiguration.worksheetRowCount', { count: item.rowCount })}</small></span></label>
            })}
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
              <SmartColumnInput
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

      {source.sourceKind === 'external' && source.externalSourceId && (
        <div className="mt-3">
          <ConfigurationSection id="read-policy" openSignal={sectionSignal} unsaved={readPolicyDirty} title={translate('sources:sourceConfiguration.section.readPolicy')} description={translate('sources:sourceConfiguration.section.readPolicyHelp')}>
            <div className="flex flex-col gap-3">
              <label className="fh-inline-check">
                <input
                  type="checkbox"
                  checked={readPolicy.enabled}
                  onChange={event => setReadPolicy(current => ({ ...current, enabled: event.target.checked }))}
                />
                {translate('commerce:commerceHub.limitSourceReads')}
              </label>
              <label className="fh-inline-check">
                <input
                  type="checkbox"
                  checked={readPolicy.manual_read_allowed}
                  onChange={event => setReadPolicy(current => ({ ...current, manual_read_allowed: event.target.checked }))}
                />
                {translate('commerce:commerceHub.manualReadNowAllowed')}
              </label>
              <label className="fh-field max-w-xs">
                <span className="fh-help-text">{translate('sources:sourceConfiguration.maxAcquisitionsPer24Hours')}</span>
                <input
                  type="number"
                  min={1}
                  max={1000}
                  value={readPolicy.max_reads_per_24h}
                  onChange={event => setReadPolicy(current => ({
                    ...current,
                    max_reads_per_24h: Number(event.target.value || DEFAULT_READ_POLICY.max_reads_per_24h),
                  }))}
                  className="fh-input"
                />
              </label>
              <p className="fh-text-caption">{translate('sources:sourceConfiguration.readPolicyAcquisitionHelp')}</p>
              <p className="fh-text-caption">{translate('sources:sourceConfiguration.readPolicyQuotaScope')}</p>
            </div>
          </ConfigurationSection>
        </div>
      )}

      {channelProfilesUnavailable && (
        <div className="fh-alert-warning mt-5 flex flex-wrap items-center justify-between gap-3" role="status">
          <span>{translate('sources:sourceConfiguration.channelProfilesUnavailable')}</span>
          <button className="fh-button-secondary fh-button-sm" type="button" onClick={() => setReloadToken(current => current + 1)}>
            <Icon name="refresh" /> {translate('common:action.retry')}
          </button>
        </div>
      )}

      <div className={`mt-5 space-y-3 ${worksheetRuleMode === 'per_worksheet' ? 'hidden' : ''}`}>
        <ConfigurationSection id="channel-columns" openSignal={sectionSignal} unsaved={dirty} title={translate('sources:sourceConfiguration.section.channelColumns')} description={translate('sources:sourceConfiguration.section.channelColumnsHelp')}>
          <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
            <p className="fh-text-caption">{translate('sources:sourceConfiguration.mappingConfiguredAfterConnection')}</p>
            {canManageCommerce && <button className="fh-button-secondary fh-button-sm" type="button" onClick={() => void openChannelSetup()}><Icon name="add" /> {translate('commerce:commerceHub.addChannel')}</button>}
          </div>
          <div className="overflow-x-auto rounded-lg border border-border" aria-label={translate('sources:sourceConfiguration.channelMappings')}>
            <table className="fh-table min-w-[1480px]">
              <thead><tr>
                <th className="w-[240px]">{translate('workspace:unifiedWorkspace.channel')}</th>
                <th className="w-[140px]">{translate('sources:sourceConfiguration.mapped')}</th>
                <th className="w-[190px]">{translate('sources:sourceConfiguration.worksheetOverride')}</th>
                {CHANNEL_FIELDS.map(([field, labelKey]) => <th className="w-[210px]" key={field}>{translate(labelKey)}</th>)}
                <th className="w-[240px]">{translate('common:action.actions')}</th>
                <th className="w-[150px] text-end">{translate('sources:sourceConfiguration.enableHeader')}</th>
              </tr></thead>
              <tbody>{channelResources.ordered.map(orderedChannel => {
                const channel = orderedChannel.item
                const enabled = Boolean(channelEnabled[channel.channelId])
                const fields = channelFields[channel.channelId] ?? emptyChannelFields()
                const issues = channelValidation(fields, enabled, channel.connectorType)
                const configured = channel.configured !== false
                const mappedStatus = channelMappedStatus(fields, channel.connectorType)
                const controlsDisabled = !channel.available || !configured
                const canToggle = channel.available && configured && (enabled || mappedStatus.mapped)
                const copyResources = prepareResourceCollection(
                  configuredChannelResources.ordered.map(item => item.item).filter(item => item.channelId !== channel.channelId),
                  sourceChannelSignals,
                )
                return <tr data-channel-id={channel.channelId} key={channel.channelId}>
                  <td><div className="flex items-center gap-3"><BrandIcon identity={{ provider: channel.connectorType || channel.channelId, sourceType: channel.connectorType }} label={orderedChannel.displayName} size={36} /><div className="min-w-0"><strong className="block truncate text-text-base">{orderedChannel.displayName}</strong>{configured ? <ResourceStateBadge badge={orderedChannel.badge} /> : <span className="fh-text-caption">{translate('common:status.setupRequired')}</span>}</div></div></td>
                  <td>{!configured
                    ? <span className="fh-text-caption">{translate('common:status.setupRequired')}</span>
                    : <Badge variant={mappedStatus.mapped ? 'success' : 'warning'}>{mappedStatus.mapped ? translate('sources:sourceConfiguration.mapped') : translate('sources:sourceConfiguration.mappingIncomplete')}</Badge>}</td>
                  <td><input className="fh-input min-w-[170px]" disabled={controlsDisabled} value={channelWorksheets[channel.channelId] ?? ''} onChange={event => setChannelWorksheets(current => ({ ...current, [channel.channelId]: event.target.value }))} placeholder={translate('sources:sourceConfiguration.useSourceWorksheet')} /></td>
                  {CHANNEL_FIELDS.map(([field]) => <td key={field}><SmartColumnInput mapping={fields.find(item => item.field === field)!} disabled={controlsDisabled} allowInternalColumnId={source.sourceKind === 'flowhub_sheet'} onChange={value => updateChannelField(channel.channelId, field, value)} /></td>)}
                  <td><div className="grid min-w-[220px] gap-2"><select className="fh-input" aria-label={translate('sources:sourceConfiguration.copyMappingFrom')} disabled={controlsDisabled} value={copyFrom[channel.channelId] ?? ''} onChange={event => setCopyFrom(current => ({ ...current, [channel.channelId]: event.target.value }))}><option value="">{translate('sources:sourceConfiguration.copyMappingFrom')}</option><ResourceOptionGroups resources={copyResources} renderLabel={item => item.displayName} /></select><div className="flex gap-2"><button className="fh-button-secondary fh-button-sm" type="button" disabled={controlsDisabled || !copyFrom[channel.channelId]} onClick={() => copyMapping(channel.channelId)}>{translate('sources:sourceConfiguration.copyMapping')}</button><button className="fh-button-secondary fh-button-sm" type="button" disabled={controlsDisabled} aria-label={translate('sources:sourceConfiguration.clearMapping')} onClick={() => clearMapping(channel.channelId)}><Icon name="close" /></button></div>{issues.length > 0 && <span className="fh-field-error">{issues[0]}</span>}</div></td>
                  <td className="text-end">{!configured
                    ? (canManageCommerce
                      ? <button className="fh-button-secondary fh-button-sm" type="button" onClick={() => void openChannelSetup(channel.channelId)}>{translate('common:action.setupNow')}</button>
                      : <span className="fh-text-caption">{translate('common:status.setupRequired')}</span>)
                    : <label className="fh-inline-check justify-end" title={canToggle ? undefined : translate('sources:sourceConfiguration.completeMappingToEnable', { fields: mappedStatus.missingFields.join(', ') })}>
                        <input type="checkbox" checked={enabled} disabled={!canToggle} onChange={() => toggleChannel(channel.channelId)} />
                        {enabled ? translate('sources:sourceConfiguration.enabled') : translate('sources:sourceConfiguration.disabled')}
                      </label>}</td>
                </tr>
              })}</tbody>
            </table>
          </div>
        </ConfigurationSection>
        <ConfigurationSection id="normalization" openSignal={sectionSignal} unsaved={dirty} title={translate('sources:sourceConfiguration.section.valueHandling')} description={translate('sources:sourceConfiguration.section.valueHandlingHelp')}>
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

      {worksheetRuleMode === 'per_worksheet' && <div className="mt-5 space-y-3">
        <ConfigurationSection
          id="channel-columns-pw"
          openSignal={sectionSignal}
          unsaved={dirty}
          title={translate('sources:sourceConfiguration.section.channelColumns')}
          description={translate('sources:sourceConfiguration.section.channelColumnsHelp')}
          defaultOpen
        >
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3" aria-label={translate('sources:sourceConfiguration.channelMappings')}>
            <ResourceSectionList resources={channelResources} renderItem={orderedChannel => {
              const channel = orderedChannel.item
              const enabled = Boolean(channelEnabled[channel.channelId])
              return (
                <label
                  className={`flex items-center gap-3 rounded-xl border p-3 ${enabled ? 'border-accent bg-accent/5' : 'border-border bg-bg-base'} ${!channel.available ? 'opacity-60' : ''}`}
                  key={channel.channelId}
                >
                  <BrandIcon identity={{ provider: channel.connectorType || channel.channelId, sourceType: channel.connectorType }} label={orderedChannel.displayName} size={40} />
                  <span className="min-w-0 flex-1">
                    <strong className="block truncate text-text-base">{orderedChannel.displayName}</strong>
                    <ResourceStateBadge badge={orderedChannel.badge} />
                  </span>
                  <input
                    type="checkbox"
                    checked={enabled}
                    disabled={!channel.available}
                    aria-label={orderedChannel.displayName}
                    onChange={() => toggleChannel(channel.channelId)}
                  />
                </label>
              )
            }} />
          </div>
        </ConfigurationSection>
        <ConfigurationSection id="worksheet-columns" openSignal={sectionSignal} unsaved={dirty} title={translate('sources:sourceConfiguration.section.worksheetColumns')} description={translate('sources:sourceConfiguration.section.worksheetColumnsHelp')}>
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
          channels={channelResources.ordered.map(item => item.item).filter(channel => channelEnabled[channel.channelId])}
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

      <section className="fh-card mt-5 scroll-mt-4" id="validation" aria-label={translate('sources:sourceConfiguration.sourcePreview')}>
        <div className="fh-panel-header">
          <div>
            <h2 className="fh-section-title">{translate('sources:sourceConfiguration.sourcePreview')}</h2>
            <p className="fh-text-caption">{translate('sources:sourceConfiguration.previewShowsIndependentChannelValues')}</p>
          </div>
          <button className="fh-button-secondary" type="button" disabled={previewing} onClick={() => void loadPreview()}>
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
                    <Badge variant="neutral">{translate('sources:sourceConfiguration.worksheet')}: {item.worksheetName}</Badge>
                    <Badge variant="neutral">{translate('sources:sourceConfiguration.row')} {item.rowNumber}</Badge>
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
      </fieldset>

      <div className="mt-5 grid gap-3 lg:grid-cols-3">
        <section className="fh-card fh-card-pad scroll-mt-4" id="snapshots">
          <h2 className="fh-section-title">{translate('sources:sourceConfiguration.detail.snapshots')}</h2>
          <p className="fh-text-caption mt-2">{translate('sources:sourceConfiguration.detail.snapshotsHelp')}</p>
        </section>
        <section className="fh-card fh-card-pad scroll-mt-4" id="activity">
          <h2 className="fh-section-title">{translate('sources:sourceConfiguration.detail.activity')}</h2>
          {canViewActivity && <button className="fh-button-secondary mt-4" type="button" onClick={() => navigate(`/activity?source=${encodeURIComponent(source.externalSourceId ?? source.id)}`)}>{translate('common:action.viewActivity')}</button>}
        </section>
        <section className="fh-card fh-card-pad scroll-mt-4" id="diagnostics">
          <h2 className="fh-section-title">{translate('sources:sourceConfiguration.detail.diagnostics')}</h2>
          {canViewDiagnostics && <button className="fh-button-secondary mt-4" type="button" onClick={() => navigate(`/diagnostics#source-${source.externalSourceId ?? source.id}`)}>{translate('common:action.diagnostics')}</button>}
        </section>
      </div>

      <div className="sticky bottom-2 z-30 mt-5 flex flex-wrap items-center gap-2 rounded-xl border border-border bg-bg-base/95 p-2 shadow-lg backdrop-blur sm:bottom-3 sm:gap-3 sm:p-3" data-testid="source-configuration-actions">
        <Badge variant={dirty ? 'warning' : 'success'}>{dirty ? translate('sources:sourceConfiguration.unsavedChanges') : translate('sources:sourceConfiguration.allChangesSaved')}</Badge>
        <span className="fh-text-caption hidden sm:inline">{translate('sources:sourceConfiguration.savedAsImmutableRevision')}</span>
        <div className="order-last grid w-full grid-cols-2 gap-2 sm:order-none sm:ms-auto sm:flex sm:w-auto sm:flex-wrap">
          {canEditSource && <button className="fh-button-secondary fh-button-sm w-full sm:w-auto" type="button" disabled={connectionChecking} onClick={() => void validateConfiguration()}><Icon name="testConnection" /> {connectionChecking ? translate('sources:sourceConfiguration.checkingConnection') : translate('sources:sourceConfiguration.validateConfiguration')}</button>}
          {canEditSource && source.sourceKind === 'external' && source.externalSourceId && readPolicy.manual_read_allowed && (
            <button className="fh-button-secondary fh-button-sm w-full sm:w-auto" type="button" disabled={reading} onClick={() => void readNow()}><Icon name="refresh" /> {reading ? translate('commerce:commerceHub.reading') : translate('commerce:commerceHub.readNow')}</button>
          )}
          {canEditSource && <button className="fh-button-primary fh-button-sm order-first col-span-2 w-full sm:order-none sm:w-auto" type="button" disabled={saving || previewedFingerprint !== configurationFingerprint || (worksheetRuleMode === 'shared' ? worksheetMode === 'selected' && selectedWorksheetNames.length === 0 : !worksheetRulesValid)} onClick={() => void save()}><Icon name="save" /> {saving ? translate('sources:sourceConfiguration.saving') : translate('sources:sourceConfiguration.saveMappingRevision')}</button>}
          <button className="fh-button-secondary fh-button-sm w-full sm:w-auto" type="button" onClick={closeConfiguration}><Icon name="previous" /> {translate('sources:sourceConfiguration.backToSources')}</button>
        </div>
      </div>

      {channelSetupId && canManageCommerce && <div className="fixed inset-0 z-50 grid place-items-center bg-black/50 p-4" role="dialog" aria-modal="true" aria-label={translate('commerce:commerceHub.addChannel')}>
        <div className="max-h-[calc(100vh-2rem)] w-full max-w-[45rem] overflow-y-auto">
          {channelSetupLoading ? <div className="fh-card fh-card-pad fh-text-caption" role="status">{translate('commerce:commerceHub.loadingChannelConfiguration')}</div> : channelSetupError ? <div className="fh-card fh-card-pad" role="alert"><p className="fh-section-title">{translate('commerce:commerceHub.unableToLoadCommerceHub')}</p><div className="mt-4 flex gap-2"><button className="fh-button-secondary" type="button" onClick={closeChannelSetup}>{translate('common:action.cancel')}</button><button className="fh-button-primary" type="button" onClick={() => void openChannelSetup(channelSetupId === 'new' ? undefined : channelSetupId)}>{translate('common:action.retry')}</button></div></div> : <ConfigPanel kind="channel" types={channelTypes} initialResourceId={channelSetupId === 'new' ? null : channelSetupId} headingLevel={2} onCancel={closeChannelSetup} onSaved={handleChannelSetupSaved} />}
        </div>
      </div>}

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
