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
  DiscoveredWorksheet,
  IdentityAuthority,
  IdentityValidation,
  IdentityValidationRow,
  MappingReadiness,
  ReferenceType,
  SourceChannel,
  SourceMapping,
  SourceLifecycleImpact,
  SourcePreview,
  SourceProfile,
  SourceMappingSaveRequest,
  SourceWorksheetRule,
} from '../features/sourceWorkspace/types'
import { translate } from '../i18n'
import { formatStatus } from '../i18n/display'
import { formatDateTime, formatNumber } from '../i18n/format'
import { localizedApiError } from '../i18n/errors'
import { useNotification } from '../notifications/NotificationProvider'
import { ResourceOptionGroups, ResourceSectionList, ResourceStateBadge } from '../components/ResourceOrdering'
import { connectionExceptionMessage, connectionResultMessage } from '../features/diagnostics/connectionErrorPresentation'
import {
  orderRelatedItems,
  prepareResourceCollection,
  sourceChannelSignals,
} from '../features/resourceOrdering/resourceOrdering'
import WorksheetRuleEditor, {
  createWorksheetRule,
  emptyChannelFields as emptyWorksheetChannelFields,
  SOURCE_FIELD_DEFINITIONS,
  SOURCE_FIELD_GROUPS,
  MappingFieldLabel,
  requiredChannelMappingFields,
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

function externalConnectionPresentation(
  configuration: CommerceSourceConfiguration | null,
  disabled: boolean,
): { label: string; variant: 'success' | 'warning' | 'info' | 'disabled' } {
  if (disabled) return { label: translate('common:status.disabled'), variant: 'disabled' }
  if (!configuration?.connection_configured) {
    return { label: translate('commerce:commerceHub.connectionNotConfigured'), variant: 'warning' }
  }
  const lastStatus = String(configuration.last_test?.status ?? '').trim().toLowerCase()
  if (['healthy', 'ok', 'operational'].includes(lastStatus)) {
    return { label: translate('common:status.healthy'), variant: 'success' }
  }
  if (lastStatus && !['unknown', 'not_checked', 'not_tested'].includes(lastStatus)) {
    return { label: translate('sources:sourceCenter.needsAttentionKpi'), variant: 'warning' }
  }
  return { label: translate('commerce:commerceHub.connectionConfiguredNotVerified'), variant: 'info' }
}

type RemoteReadQuota = {
  enabled: boolean
  limit: number
  usage: number
  remaining: number
  resetAt: string | null
  exhausted: boolean
}

type WorksheetDiscoveryState = {
  requiresRemoteRead: boolean
  metadataSource: 'local' | 'snapshot' | 'remote' | 'unavailable'
}

type WorksheetDiscoveryFeedback = {
  variant: 'success' | 'warning' | 'danger'
  title: string
  message: string
}

const UNSPECIFIED_IDENTITY_AUTHORITY: IdentityAuthority = {
  type: 'unspecified',
  systemIdentifier: null,
  displayLabel: null,
}

const IDENTITY_AUTHORITY_PRESETS = [
  { value: 'external_system:woocommerce', type: 'external_system', systemIdentifier: 'woocommerce', labelKey: 'sources:sourceConfiguration.identityAuthorityOption.woocommerce' },
  { value: 'external_system:snappshop', type: 'external_system', systemIdentifier: 'snappshop', labelKey: 'sources:sourceConfiguration.identityAuthorityOption.snappshop' },
  { value: 'external_system:tapsishop', type: 'external_system', systemIdentifier: 'tapsishop', labelKey: 'sources:sourceConfiguration.identityAuthorityOption.tapsishop' },
  { value: 'external_system:technolife', type: 'external_system', systemIdentifier: 'technolife', labelKey: 'sources:sourceConfiguration.identityAuthorityOption.technolife' },
  { value: 'external_system:erp', type: 'external_system', systemIdentifier: 'erp', labelKey: 'sources:sourceConfiguration.identityAuthorityOption.erp' },
  { value: 'external_system:accounting', type: 'external_system', systemIdentifier: 'accounting', labelKey: 'sources:sourceConfiguration.identityAuthorityOption.accounting' },
  { value: 'internal:sku', type: 'internal', systemIdentifier: 'sku', labelKey: 'sources:sourceConfiguration.identityAuthorityOption.internalSku' },
] as const

function identityAuthorityValue(authority: IdentityAuthority): string {
  if (authority.type === 'unspecified') return ''
  if (authority.type === 'custom') return 'custom'
  return `${authority.type}:${authority.systemIdentifier ?? ''}`
}

function identityAuthorityComplete(authority: IdentityAuthority): boolean {
  return authority.type !== 'unspecified' && Boolean(authority.systemIdentifier?.trim())
}

function identityRowLabel(row: IdentityValidationRow): string {
  return typeof row === 'string' ? row : `${row.worksheetName}!${row.rowNumber}`
}

function sourceReadQuota(source: SourceProfile | null): RemoteReadQuota | null {
  const quota = source?.readQuota
  if (!quota) return null
  return {
    enabled: quota.enabled,
    limit: quota.limit,
    usage: quota.usage,
    remaining: quota.remaining,
    resetAt: quota.reset_at,
    exhausted: quota.exhausted,
  }
}

function sourceWorksheetDiscovery(source: SourceProfile | null): WorksheetDiscoveryState | null {
  const discovery = source?.worksheetDiscovery
  if (!discovery) return null
  return {
    requiresRemoteRead: discovery.requires_remote_read,
    metadataSource: discovery.metadata_source === 'discovery_cache' ? 'snapshot' : discovery.metadata_source,
  }
}

function formatQuotaReset(value: string | null | undefined): string {
  if (!value) return translate('sources:sourceConfiguration.remoteReadsResetUnavailable')
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return translate('sources:sourceConfiguration.remoteReadsResetUnavailable')
  return new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
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

const SOURCE_FIELDS = SOURCE_FIELD_DEFINITIONS

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

function isFieldFilled(field: FieldMapping | undefined): boolean {
  return Boolean(field && field.referenceType !== 'disabled' && field.referenceValue?.trim())
}

function channelMappedStatus(fields: FieldMapping[], connectorType: string | undefined, capabilities?: Readonly<Record<string, unknown>>): { mapped: boolean; missingFields: string[] } {
  const missingFields: string[] = []
  for (const field of requiredChannelMappingFields(connectorType, capabilities)) {
    if (!isFieldFilled(fields.find(item => item.field === field))) missingFields.push(fieldDisplayName(field))
  }
  return { mapped: missingFields.length === 0, missingFields }
}

function channelValidation(fields: FieldMapping[], enabled: boolean, connectorType: string | undefined, capabilities?: Readonly<Record<string, unknown>>): string[] {
  if (!enabled) return []
  const issues: string[] = []
  const requiredFields = requiredChannelMappingFields(connectorType, capabilities)
  if (requiredFields.has('external_id') && !isFieldFilled(fields.find(item => item.field === 'external_id'))) {
    issues.push(translate('sources:sourceConfiguration.productIdentifierRequired'))
  }
  if ((requiredFields.has('stock') && !isFieldFilled(fields.find(item => item.field === 'stock')))
    || (requiredFields.has('status') && !isFieldFilled(fields.find(item => item.field === 'status')))) {
    issues.push(translate('sources:sourceConfiguration.stockStatusRequired'))
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

type IdentityDuplicate = { key: string; rows: string[] }
type IdentityBindingConflict = {
  key: string
  rows: string[]
  boundCanonicalProductId: string | null
  conflictingCanonicalProductIds: string[]
}

function identityPreviewDetails(preview: SourcePreview | null, persisted: IdentityValidation | null): {
  status: 'pass' | 'blocked' | 'pending'
  participatingRowCount: number | null
  validKeyCount: number | null
  missingKeyCount: number | null
  duplicateKeyCount: number | null
  duplicateRowCount: number | null
  bindingConflictCount: number | null
  missingRows: string[]
  duplicates: IdentityDuplicate[]
  bindingConflicts: IdentityBindingConflict[]
  mappingReferences: string[]
  evidence: IdentityValidation['evidence']
} {
  const validation = preview?.identityValidation ?? persisted
  const missingKeyCount = validation?.missingKeyCount
    ?? preview?.issues.find(issue => issue.category === 'missing_source_product_key')?.count
    ?? null
  const duplicateKeyCount = validation?.duplicateKeyCount
    ?? preview?.issues.find(issue => issue.category === 'duplicate_source_product_key')?.count
    ?? null
  const duplicateGroups = new Map<string, IdentityDuplicate>()
  for (const group of validation?.duplicateGroups ?? []) {
    const rows = group.rows.map(identityRowLabel)
    duplicateGroups.set(`${group.keyValue}\u0000${rows.join('\u0000')}`, { key: group.keyValue, rows })
  }
  if (duplicateGroups.size === 0 && preview) {
    for (const item of preview.items) {
      for (const issue of item.issues.filter(candidate => candidate.category === 'duplicate_source_product_key')) {
        const details = issue.details ?? {}
        const key = typeof details.keyValue === 'string'
          ? details.keyValue
          : String(item.sourceProduct.source_key ?? '')
        const rows = Array.isArray(details.conflictingRows)
          ? details.conflictingRows.filter((row): row is string => typeof row === 'string')
          : [`${item.worksheetName}!${item.rowNumber}`]
        const signature = `${key}\u0000${rows.join('\u0000')}`
        duplicateGroups.set(signature, { key, rows })
      }
    }
  }
  const legacyStatus = missingKeyCount || duplicateKeyCount ? 'blocked' : 'pending'
  return {
    status: validation?.status ?? legacyStatus,
    participatingRowCount: validation?.participatingRowCount ?? preview?.total ?? null,
    validKeyCount: validation?.validKeyCount ?? null,
    missingKeyCount,
    duplicateKeyCount,
    duplicateRowCount: validation?.duplicateRowCount ?? duplicateKeyCount,
    bindingConflictCount: validation?.bindingConflictCount ?? null,
    missingRows: (validation?.missingRows ?? []).map(identityRowLabel),
    duplicates: [...duplicateGroups.values()],
    bindingConflicts: (validation?.bindingConflicts ?? []).map(conflict => ({
      key: conflict.keyValue,
      rows: conflict.rows.map(identityRowLabel),
      boundCanonicalProductId: conflict.boundCanonicalProductId,
      conflictingCanonicalProductIds: conflict.conflictingCanonicalProductIds,
    })),
    mappingReferences: (validation?.mappingReferences ?? []).map(reference => reference.worksheetName
      ? `${reference.worksheetName}: ${reference.referenceValue ?? '—'}`
      : reference.referenceValue ?? '—'),
    evidence: validation?.evidence ?? null,
  }
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
  const canManageSources = effectiveHasPerm(user, WORKSPACE_PERMISSION.admin)
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
  const [identityAuthority, setIdentityAuthority] = useState<IdentityAuthority>(UNSPECIFIED_IDENTITY_AUTHORITY)
  const [channelFields, setChannelFields] = useState<Record<string, FieldMapping[]>>({})
  const [channelWorksheets, setChannelWorksheets] = useState<Record<string, string>>({})
  const [channelEnabled, setChannelEnabled] = useState<Record<string, boolean>>({})
  const [configuredChannelIds, setConfiguredChannelIds] = useState<string[]>([])
  const [copyFrom, setCopyFrom] = useState<Record<string, string>>({})
  const [worksheetMode, setWorksheetMode] = useState<'all' | 'selected'>('selected')
  const [worksheetRuleMode, setWorksheetRuleMode] = useState<'shared' | 'per_worksheet'>('shared')
  const [duplicateProductPolicy, setDuplicateProductPolicy] = useState<'block' | 'last_sheet_wins'>('block')
  const [worksheetRules, setWorksheetRules] = useState<SourceWorksheetRule[]>([])
  const [detectedWorksheets, setDetectedWorksheets] = useState<DiscoveredWorksheet[]>([])
  const [selectedWorksheetNames, setSelectedWorksheetNames] = useState<string[]>([])
  const [newWorksheetName, setNewWorksheetName] = useState('')
  const [detectingWorksheets, setDetectingWorksheets] = useState(false)
  const [worksheetDiscoveryFeedback, setWorksheetDiscoveryFeedback] = useState<WorksheetDiscoveryFeedback | null>(null)
  const [dataStartRow, setDataStartRow] = useState(1)
  const [worksheetName, setWorksheetName] = useState('')
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
  const [readQuota, setReadQuota] = useState<RemoteReadQuota | null>(null)
  const [discoveryQuota, setDiscoveryQuota] = useState<RemoteReadQuota | null>(null)
  const [worksheetDiscovery, setWorksheetDiscovery] = useState<WorksheetDiscoveryState | null>(null)
  const [readPolicy, setReadPolicy] = useState<ReadPolicyDraft>(DEFAULT_READ_POLICY)
  const [readPolicyBaseline, setReadPolicyBaseline] = useState<ReadPolicyDraft>(DEFAULT_READ_POLICY)
  const [reading, setReading] = useState(false)
  const [activeNavId, setActiveNavId] = useState('overview')
  const [sectionSignal, setSectionSignal] = useState<SectionOpenSignal | null>(null)
  const [removalOpen, setRemovalOpen] = useState(false)
  const [removalImpact, setRemovalImpact] = useState<SourceLifecycleImpact | null>(null)
  const [checkingRemoval, setCheckingRemoval] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [confirmationName, setConfirmationName] = useState('')
  const [confirmHistoryPolicy, setConfirmHistoryPolicy] = useState(false)

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
      setReadQuota(sourceReadQuota(loaded))
      setDiscoveryQuota(loaded.discoveryQuota ? {
        enabled: loaded.discoveryQuota.enabled, limit: loaded.discoveryQuota.limit,
        usage: loaded.discoveryQuota.usage, remaining: loaded.discoveryQuota.remaining,
        resetAt: loaded.discoveryQuota.reset_at, exhausted: loaded.discoveryQuota.exhausted,
      } : null)
      setWorksheetDiscovery(sourceWorksheetDiscovery(loaded))
      setChannels(channelResult.ok ? channelResult.available.items : fallbackChannelsForSource(loaded))
      setChannelProfilesUnavailable(!channelResult.ok)
      setDataStartRow(loaded.mapping?.dataStartRow ?? loaded.dataStartRow)
      setWorksheetMode(loaded.mapping?.worksheetMode ?? loaded.worksheetMode)
      setWorksheetName(loaded.mapping?.worksheetName ?? loaded.worksheetName ?? '')
      setSelectedWorksheetNames(
        loaded.mapping?.selectedWorksheetNames?.length
          ? loaded.mapping.selectedWorksheetNames
          : loaded.mapping?.worksheetRuleMode === 'per_worksheet'
            ? (loaded.mapping.worksheetRules ?? []).filter(rule => rule.enabled).map(rule => rule.worksheetName)
          : loaded.mapping?.worksheetMode === 'selected' && loaded.mapping.worksheetName
            ? [loaded.mapping.worksheetName]
            : loaded.worksheetMode === 'selected' && loaded.worksheetName
              ? [loaded.worksheetName]
              : [],
      )
      setWorksheetRuleMode(loaded.mapping?.worksheetRuleMode ?? 'shared')
      setDuplicateProductPolicy(loaded.mapping?.duplicateProductPolicy ?? 'block')
      setIdentityAuthority(loaded.mapping?.identityAuthority ?? UNSPECIFIED_IDENTITY_AUTHORITY)
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
  const externalSourceDisabled = Boolean(
    source?.sourceKind === 'external'
    && source.externalSourceId
    && externalConfig?.enabled === false,
  )
  const quotaResetPending = Boolean(
    readQuota?.resetAt && new Date(readQuota.resetAt).getTime() > Date.now(),
  )
  const remoteReadQuotaExhausted = Boolean(
    readQuota?.enabled && readQuota.exhausted && (!readQuota.resetAt || quotaResetPending),
  )
  const effectiveDiscoveryQuota = discoveryQuota ?? (
    worksheetDiscovery?.metadataSource === 'remote' ? readQuota : null
  )
  const discoveryRefreshBlocked = Boolean(effectiveDiscoveryQuota?.enabled && effectiveDiscoveryQuota.exhausted)
  const worksheetDetectionHelp = source?.sourceKind !== 'external' || worksheetDiscovery?.metadataSource === 'local'
    ? translate('sources:sourceConfiguration.worksheetDetectionUsesLocalSource')
    : worksheetDiscovery?.metadataSource === 'snapshot'
    ? translate('sources:sourceConfiguration.worksheetDetectionUsesSnapshot')
    : worksheetDiscovery?.metadataSource === 'unavailable'
      ? translate('sources:sourceConfiguration.selectSpreadsheetBeforeWorksheetDetection')
      : translate('sources:sourceConfiguration.worksheetDetectionMayUseRead')

  const configurationFingerprint = useMemo(() => JSON.stringify({
    identityAuthority,
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
  }), [channelEnabled, channelFields, channelWorksheets, configuredChannelIds, dataStartRow, duplicateProductPolicy, identityAuthority, selectedWorksheetNames, sourceFields, valuePolicy, worksheetMode, worksheetName, worksheetRuleMode, worksheetRules])
  const dirty = baselineFingerprint !== null && baselineFingerprint !== configurationFingerprint
  const readPolicyDirty = JSON.stringify(readPolicy) !== JSON.stringify(readPolicyBaseline)
  const savedParticipatingWorksheetNames = worksheetRules.filter(rule => rule.enabled).map(rule => rule.worksheetName)
  const participatingWorksheetNames = worksheetMode === 'all'
    ? (detectedWorksheets.length > 0 ? detectedWorksheets.map(item => item.name) : savedParticipatingWorksheetNames)
    : (selectedWorksheetNames.length > 0 ? selectedWorksheetNames : savedParticipatingWorksheetNames)
  const participatingWorksheetCount = participatingWorksheetNames.length
  const effectiveWorksheetRuleMode = participatingWorksheetCount > 1 ? worksheetRuleMode : 'shared'
  const renderedWorksheetRuleMode = worksheetRuleMode === 'per_worksheet' && worksheetRules.length > 0
    ? 'per_worksheet'
    : effectiveWorksheetRuleMode
  const sharedDiscoveredColumns = detectedWorksheets.find(item => participatingWorksheetNames.includes(item.name))?.columns ?? []
  const presetAuthoritySystems = new Set<string>(IDENTITY_AUTHORITY_PRESETS.map(option => option.systemIdentifier))
  const dynamicAuthoritySystems = [...new Set(channels.map(channel => channel.connectorType).filter(system => !presetAuthoritySystems.has(system)))]
  if (identityAuthority.type === 'external_system' && identityAuthority.systemIdentifier && !presetAuthoritySystems.has(identityAuthority.systemIdentifier) && !dynamicAuthoritySystems.includes(identityAuthority.systemIdentifier)) {
    dynamicAuthoritySystems.push(identityAuthority.systemIdentifier)
  }
  const identityAuthorityOptions = [
    ...IDENTITY_AUTHORITY_PRESETS.map(option => ({ value: option.value, label: translate(option.labelKey) })),
    ...dynamicAuthoritySystems.map(systemIdentifier => ({
      value: `external_system:${systemIdentifier}`,
      label: formatChannelDisplayName(systemIdentifier, { showInstance: false }),
    })),
  ]

  useEffect(() => {
    if (worksheetRuleMode !== 'per_worksheet') return
    const participating = new Set(participatingWorksheetNames)
    setWorksheetRules(current => current.map(rule => ({
      ...rule,
      enabled: participating.has(rule.worksheetName),
    })))
    if (participatingWorksheetNames.length === 1) {
      const selectedRule = worksheetRules.find(rule => rule.worksheetName === participatingWorksheetNames[0])
      if (selectedRule) {
        setDataStartRow(selectedRule.dataStartRow)
        setSourceFields(selectedRule.sourceFields.map(field => ({ ...field })))
        setValuePolicy({ ...DEFAULT_VALUE_POLICY, ...selectedRule.valuePolicy })
        setConfiguredChannelIds(selectedRule.channels.map(channel => channel.channelId))
        setChannelEnabled(Object.fromEntries(selectedRule.channels.map(channel => [channel.channelId, channel.enabled])))
        setChannelFields(Object.fromEntries(selectedRule.channels.map(channel => [
          channel.channelId,
          channel.fields.map(field => ({ ...field })),
        ])))
        setChannelWorksheets(Object.fromEntries(selectedRule.channels.map(channel => [
          channel.channelId,
          channel.worksheetName ?? selectedRule.worksheetName,
        ])))
      }
    }
  // Participating worksheet identities are the authoritative scope boundary.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [worksheetMode, selectedWorksheetNames.join('\u0000'), detectedWorksheets.map(item => item.name).join('\u0000')])

  const navigationSections = useMemo(() => [
    { id: 'overview', labelKey: 'sources:sourceConfiguration.section.general', unsaved: false },
    { id: 'worksheet-discovery', labelKey: 'sources:sourceConfiguration.section.worksheetDiscovery', unsaved: false },
    { id: 'worksheet-participation', labelKey: 'sources:sourceConfiguration.chooseParticipatingWorksheets', unsaved: dirty },
    ...(participatingWorksheetCount > 1 ? [{ id: 'worksheet-rules', labelKey: 'sources:sourceConfiguration.worksheetRules', unsaved: dirty }] : []),
    { id: 'source-identity', labelKey: 'sources:sourceConfiguration.sourceIdentity', unsaved: dirty },
    ...(renderedWorksheetRuleMode === 'shared'
      ? [
          { id: 'workbook', labelKey: 'sources:sourceConfiguration.section.workbook', unsaved: dirty },
          { id: 'channel-columns', labelKey: 'sources:sourceConfiguration.section.channelColumns', unsaved: dirty },
          { id: 'normalization', labelKey: 'sources:sourceConfiguration.section.valueHandling', unsaved: dirty },
        ]
      : [
          { id: 'channel-columns-pw', labelKey: 'sources:sourceConfiguration.section.channelColumns', unsaved: dirty },
          { id: 'worksheet-columns', labelKey: 'sources:sourceConfiguration.section.worksheetColumns', unsaved: dirty },
        ]),
    ...(hasReadPolicySection
      ? [{ id: 'read-policy', labelKey: 'sources:sourceConfiguration.section.readPolicy', unsaved: readPolicyDirty }]
      : []),
    { id: 'validation', labelKey: 'sources:sourceConfiguration.sourcePreview', unsaved: false },
    { id: 'snapshots', labelKey: 'sources:sourceConfiguration.detail.snapshots', unsaved: false },
    { id: 'activity', labelKey: 'sources:sourceConfiguration.detail.activity', unsaved: false },
    { id: 'diagnostics', labelKey: 'sources:sourceConfiguration.detail.diagnostics', unsaved: false },
  ], [dirty, hasReadPolicySection, participatingWorksheetCount, readPolicyDirty, renderedWorksheetRuleMode])

  function retainQuotaLimit(error: unknown) {
    if (!(error instanceof ApiError) || error.code !== 'SOURCE_READ_LIMIT_REACHED') return false
    const limit = error.details.limit ?? readQuota?.limit ?? 0
    const usage = error.details.usage ?? readQuota?.usage ?? limit
    setReadQuota({
      enabled: true,
      limit,
      usage,
      remaining: 0,
      resetAt: error.details.resetAt ?? readQuota?.resetAt ?? null,
      exhausted: true,
    })
    return true
  }

  function quotaLimitDescription(error?: unknown) {
    const limit = error instanceof ApiError ? error.details.limit ?? readQuota?.limit ?? 0 : readQuota?.limit ?? 0
    const usage = error instanceof ApiError ? error.details.usage ?? readQuota?.usage ?? limit : readQuota?.usage ?? limit
    const resetAt = error instanceof ApiError ? error.details.resetAt ?? readQuota?.resetAt : readQuota?.resetAt
    return translate('sources:sourceConfiguration.remoteReadsLimitReached', {
      usage,
      limit,
      reset: formatQuotaReset(resetAt),
    })
  }

  function retainDiscoveryQuotaLimit(error: unknown) {
    if (!(error instanceof ApiError) || error.code !== 'SOURCE_DISCOVERY_LIMIT_REACHED') return false
    const limit = error.details.limit ?? discoveryQuota?.limit ?? 0
    const usage = error.details.usage ?? discoveryQuota?.usage ?? limit
    setDiscoveryQuota({
      enabled: true,
      limit,
      usage,
      remaining: 0,
      resetAt: error.details.resetAt ?? discoveryQuota?.resetAt ?? null,
      exhausted: true,
    })
    return true
  }

  function discoveryQuotaDescription(error?: unknown) {
    const quota = discoveryQuota ?? effectiveDiscoveryQuota
    const limit = error instanceof ApiError ? error.details.limit ?? quota?.limit ?? 0 : quota?.limit ?? 0
    const usage = error instanceof ApiError ? error.details.usage ?? quota?.usage ?? limit : quota?.usage ?? limit
    const resetAt = error instanceof ApiError ? error.details.resetAt ?? quota?.resetAt : quota?.resetAt
    return translate('sources:sourceConfiguration.discoveryLimitReached', {
      usage,
      limit,
      reset: formatQuotaReset(resetAt),
    })
  }

  useEffect(() => {
    if (loading || !source || typeof IntersectionObserver === 'undefined') return
    const elements = navigationSections.map(section => section.id)
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
  }, [loading, navigationSections, source])

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

  function changeIdentityAuthority(value: string) {
    if (!value) {
      setIdentityAuthority(UNSPECIFIED_IDENTITY_AUTHORITY)
      return
    }
    if (value === 'custom') {
      setIdentityAuthority(current => current.type === 'custom'
        ? current
        : { type: 'custom', systemIdentifier: '', displayLabel: null })
      return
    }
    const [type, ...identifierParts] = value.split(':')
    setIdentityAuthority({
      type: type === 'internal' ? 'internal' : 'external_system',
      systemIdentifier: identifierParts.join(':') || null,
      displayLabel: null,
    })
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
    if (mode === 'per_worksheet' && worksheetRules.length === 0) {
      const detectedWorksheetNames = detectedWorksheets.map(item => item.name)
      if (detectedWorksheetNames.length === 0) {
        setWorksheetDiscoveryFeedback({
          variant: 'warning',
          title: translate('sources:sourceConfiguration.detectWorksheetsFirst'),
          message: translate('sources:sourceConfiguration.detectWorksheetsBeforeSeparateRules'),
        })
        return
      }
      const worksheetNames = detectedWorksheetNames
      const selectedNames = new Set(selectedWorksheetNames)
      setWorksheetRules(worksheetNames.map(name => ({
        ...createWorksheetRule(name),
        enabled: selectedNames.size === 0 || selectedNames.has(name),
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
      const enabledWorksheetNames = worksheetNames.filter(name => selectedNames.size === 0 || selectedNames.has(name))
      setSelectedWorksheetRules(enabledWorksheetNames)
      setExpandedWorksheet(enabledWorksheetNames[0] ?? worksheetNames[0] ?? null)
    }
    setWorksheetRuleMode(mode)
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
    if (externalSourceDisabled) {
      notify.error({
        title: translate('sources:sourceConfiguration.connectionCheckFailed'),
        description: translate('sources:sourceCenter.setupReasonDisabled'),
      })
      return
    }
    setConnectionChecking(true)
    try {
      if (source?.sourceKind === 'external' && source.externalSourceId && commerce) {
        const connection = await commerce.testSource(source.externalSourceId)
        if (!connection.ok) {
          notify.error({
            title: translate('sources:sourceConfiguration.connectionCheckFailed'),
            description: connectionResultMessage(connection),
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
        // Connection verification does not acquire the workbook. Worksheet
        // discovery is an explicit action because it may spend one read slot.
        notify.success({
          title: translate('sources:sourceConfiguration.connectionReady'),
          description: translate('sources:sourceConfiguration.connectionReadyDetectWorksheets'),
        })
        return
      }
      const result = await sourceWorkspaceApi.worksheets(sourceId)
      setDetectedWorksheets(result.items.map(item => ({ ...item, columns: item.columns ?? [] })))
      notify.success({ title: translate('sources:sourceConfiguration.connectionReady'), description: translate('sources:sourceConfiguration.worksheetsDetected', { count: result.items.length }) })
    } catch (error) {
      notify.error({ title: translate('sources:sourceConfiguration.connectionCheckFailed'), description: connectionExceptionMessage(error) })
    } finally {
      setConnectionChecking(false)
    }
  }

  function closeConfiguration() {
    if (dirty && !window.confirm(translate('sources:sourceConfiguration.discardUnsavedChanges'))) return
    navigate('/sources')
  }

  async function openRemoval() {
    if (!source || !canManageSources) return
    setRemovalOpen(true)
    setRemovalImpact(null)
    setConfirmationName('')
    setConfirmHistoryPolicy(false)
    setCheckingRemoval(true)
    try {
      const impact = await sourceWorkspaceApi.sourceLifecycle(source.id)
      if (impact.sourceId === source.id) setRemovalImpact(impact)
    } catch (error) {
      notify.error({
        title: translate('sources:sourceCenter.sourceCouldNotBeRemoved'),
        description: localizedApiError(error, 'sources:sourceCenter.removalImpactUnavailable'),
      })
      setRemovalOpen(false)
    } finally {
      setCheckingRemoval(false)
    }
  }

  function closeRemoval() {
    if (deleting) return
    setRemovalOpen(false)
    setRemovalImpact(null)
    setConfirmationName('')
    setConfirmHistoryPolicy(false)
  }

  async function removeSource() {
    if (
      !source
      || !removalImpact
      || Object.keys(removalImpact.blockers).length > 0
      || confirmationName !== source.name
      || !confirmHistoryPolicy
    ) return
    setDeleting(true)
    try {
      const result = await sourceWorkspaceApi.deleteSource(source, confirmationName)
      notify.success({
        title: result.outcome === 'deleted'
          ? translate('sources:sourceCenter.sourceDeleted')
          : translate('sources:sourceCenter.sourceArchived'),
        description: result.outcome === 'deleted'
          ? translate('sources:sourceCenter.unusedSourceDeletedSafely')
          : translate('sources:sourceCenter.protectedHistoryPreserved'),
      })
      navigate('/sources', { replace: true })
    } catch (error) {
      notify.error({
        title: translate('sources:sourceCenter.sourceCouldNotBeRemoved'),
        description: localizedApiError(error, 'sources:sourceCenter.activeWorkspacePreventsRemoval'),
      })
    } finally {
      setDeleting(false)
    }
  }

  async function archiveCurrentSource() {
    if (!source || !removalImpact || Object.keys(removalImpact.blockers).length > 0 || confirmationName !== source.name) return
    setDeleting(true)
    try {
      await sourceWorkspaceApi.archiveSource(source, confirmationName)
      navigate('/sources', { replace: true })
    } catch (error) {
      notify.error({ title: translate('sources:sourceCenter.sourceCouldNotBeRemoved'), description: localizedApiError(error, 'sources:sourceCenter.activeWorkspacePreventsRemoval') })
    } finally {
      setDeleting(false)
    }
  }

  function goToSection(id: string) {
    setActiveNavId(id)
    setSectionSignal({ ids: [id], open: true, token: Date.now() })
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
    if (externalSourceDisabled) {
      notify.error({
        title: translate('commerce:commerceHub.unableToRefreshTheSource'),
        description: translate('sources:sourceCenter.setupReasonDisabled'),
      })
      return
    }
    if (remoteReadQuotaExhausted) {
      notify.error({
        title: translate('sources:sourceConfiguration.remoteReadsLimitReachedTitle'),
        description: quotaLimitDescription(),
      })
      return
    }
    setReading(true)
    try {
      const result = await commerce.readSource(source.externalSourceId)
      if (result.ok) {
        const usage = Number(result.reads_used_last_24h ?? 0)
        const remaining = Number(result.reads_remaining ?? result.remaining_reads_today ?? 0)
        setReadQuota(current => ({
          enabled: current?.enabled ?? true,
          limit: current?.limit ?? Math.max(usage + remaining, 0),
          usage,
          remaining,
          resetAt: result.reset_at,
          exhausted: remaining <= 0,
        }))
        setWorksheetDiscovery({ requiresRemoteRead: false, metadataSource: 'snapshot' })
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
    } catch (error) {
      notify.error({
        title: retainQuotaLimit(error)
          ? translate('sources:sourceConfiguration.remoteReadsLimitReachedTitle')
          : translate('commerce:commerceHub.unableToRefreshTheSource'),
        description: error instanceof ApiError && error.code === 'SOURCE_READ_LIMIT_REACHED'
          ? quotaLimitDescription(error)
          : localizedApiError(error, 'commerce:commerceHub.pleaseTryAgain'),
      })
    } finally {
      setReading(false)
    }
  }

  async function detectWorksheets(refresh = false) {
    // Mapping remains editable while a Source is disabled, but worksheet
    // discovery is a remote read and follows the same enabled boundary as
    // Test connection and Read now.
    if (refresh && externalSourceDisabled) {
      setWorksheetDiscoveryFeedback({
        variant: 'danger',
        title: translate('sources:sourceConfiguration.worksheetDetectionFailed'),
        message: translate('commerce:commerceHub.sourceDisabledRemoteActions'),
      })
      notify.error({
        title: translate('sources:sourceConfiguration.worksheetDetectionFailed'),
        description: translate('commerce:commerceHub.sourceDisabledRemoteActions'),
      })
      return
    }
    if (refresh && discoveryRefreshBlocked) {
      setWorksheetDiscoveryFeedback({
        variant: 'danger',
        title: translate('sources:sourceConfiguration.discoveryLimitReachedTitle'),
        message: discoveryQuotaDescription(),
      })
      notify.error({
        title: translate('sources:sourceConfiguration.discoveryLimitReachedTitle'),
        description: discoveryQuotaDescription(),
      })
      return
    }
    setDetectingWorksheets(true)
    setWorksheetDiscoveryFeedback(null)
    try {
      const result = refresh
        ? await sourceWorkspaceApi.refreshWorksheets(sourceId)
        : await sourceWorkspaceApi.worksheets(sourceId)
      setDetectedWorksheets(result.items.map(item => ({ ...item, columns: item.columns ?? [] })))
      if (result.readQuota) setReadQuota(result.readQuota)
      if (result.discoveryQuota) setDiscoveryQuota(result.discoveryQuota)
      if (result.worksheetDiscovery) {
        setWorksheetDiscovery({
          requiresRemoteRead: result.worksheetDiscovery.requiresRemoteRead,
          metadataSource: result.worksheetDiscovery.metadataSource === 'flowhub_sheet'
            ? 'local'
            : result.worksheetDiscovery.metadataSource === 'unavailable'
              ? 'unavailable'
              : result.worksheetDiscovery.metadataSource === 'snapshot'
                ? 'snapshot'
                : 'remote',
        })
      }
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
          const detected = new Set(result.items.map(item => item.name))
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
          return [
            ...current.map(rule => detected.has(rule.worksheetName) ? rule : { ...rule, enabled: false }),
            ...additions,
          ]
        })
        setSelectedWorksheetRules(current => current.filter(name => result.items.some(item => item.name === name)))
        setExpandedWorksheet(current => current ?? result.items[0]?.name ?? null)
      }
      setWorksheetDiscoveryFeedback({
        variant: 'success',
        title: translate('sources:sourceConfiguration.worksheetsDetected', { count: result.items.length }),
        message: result.items.length === 0
          ? translate('sources:sourceConfiguration.refreshFromNextcloudRequired')
          : result.worksheetDiscovery?.remoteReadUsed
          ? translate('sources:sourceConfiguration.worksheetDiscoveryReadUsed')
          : translate('sources:sourceConfiguration.worksheetDiscoveryLocal'),
      })
    } catch (error) {
      const quotaReached = refresh ? retainDiscoveryQuotaLimit(error) : false
      const title = quotaReached
        ? translate('sources:sourceConfiguration.discoveryLimitReachedTitle')
        : translate('sources:sourceConfiguration.worksheetDetectionFailed')
      const description = quotaReached
        ? discoveryQuotaDescription(error)
        : localizedApiError(error, 'sources:sourceConfiguration.tryAgain')
      setWorksheetDiscoveryFeedback({ variant: 'danger', title, message: description })
      notify.error({
        title,
        description,
      })
    } finally {
      setDetectingWorksheets(false)
    }
  }

  function mappingPayload(): SourceMappingSaveRequest | null {
    if (!source) return null
    return {
      expected_source_version: source.version,
      worksheet_mode: worksheetMode,
      worksheet_name: worksheetMode === 'selected' && selectedWorksheetNames.length === 1 ? selectedWorksheetNames[0] : null,
      selected_worksheet_names: worksheetMode === 'selected' ? selectedWorksheetNames : [],
      data_start_row: effectiveWorksheetRuleMode === 'shared' ? dataStartRow : 1,
      source_fields: (effectiveWorksheetRuleMode === 'shared' ? sourceFields : []).map(item => ({
        field: item.field,
        reference_type: item.referenceType,
        reference_value: item.referenceValue,
        required: item.required ?? false,
      })),
      channel_mappings: (effectiveWorksheetRuleMode === 'shared' ? configuredChannelIds : []).map(channelId => ({
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
      worksheet_rule_mode: effectiveWorksheetRuleMode,
      duplicate_product_policy: duplicateProductPolicy,
      worksheet_rules: effectiveWorksheetRuleMode === 'per_worksheet' ? worksheetRules.map(rule => ({
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
      identity_policy_version: 2,
      identity_authority: {
        type: identityAuthority.type,
        system_identifier: identityAuthority.systemIdentifier?.trim() || null,
        display_label: identityAuthority.displayLabel?.trim() || null,
      },
    }
  }

  async function saveReadPolicy() {
    if (!source?.externalSourceId || !commerce || !externalConfig) return
    if (JSON.stringify(readPolicy) === JSON.stringify(readPolicyBaseline)) return
    try {
      await commerce.saveSource(source.externalSourceId, {
        display_name: externalConfig.display_name,
        ...(typeof externalConfig.enabled === 'boolean' ? { enabled: externalConfig.enabled } : {}),
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
    if (saveIssues.length > 0) {
      notify.error({
        title: translate('sources:sourceConfiguration.mappingWasNotSaved'),
        description: saveIssues[0],
      })
      return
    }
    const payload = mappingPayload()
    if (!payload) return
    setSaving(true)
    try {
      // Configuration persistence must never acquire the remote workbook.
      // The backend derives identity readiness only from existing FlowHub
      // evidence and returns PASS, BLOCKED, or PENDING with this revision.
      const savedMapping = await sourceWorkspaceApi.saveMapping(source.id, payload)
      await saveReadPolicy()
      notify.success({
        title: translate('sources:sourceConfiguration.sourceMappingSaved'),
        description: translate(savedMapping.mappingReadiness === 'identity_validation_pending'
          ? 'sources:sourceConfiguration.mappingSavedValidationPending'
          : savedMapping.mappingReadiness === 'identity_validation_blocked'
            ? 'sources:sourceConfiguration.mappingSavedValidationBlocked'
            : 'sources:sourceConfiguration.aNewImmutableMappingRevisionWasCreated'),
      })
      setBaselineFingerprint(configurationFingerprint)
      setPreviewedFingerprint(null)
      const refreshed = await sourceWorkspaceApi.source(source.id)
      setSource({ ...refreshed, mapping: savedMapping, mappingReadiness: savedMapping.mappingReadiness })
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
      const result = await sourceWorkspaceApi.previewUnsavedMapping(sourceId, payload)
      setPreview(result)
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

  const sourceArchived = source.status === 'archived'
  const canMutateSource = canEditSource && !sourceArchived

  const currentPreview = previewedFingerprint === configurationFingerprint ? preview : null
  const effectiveMappingReadiness: MappingReadiness | null = dirty
    ? 'identity_validation_pending'
    : source.mapping?.mappingReadiness
      ?? source.mappingReadiness
      ?? (source.mapping ? 'identity_validation_pending' : null)
  const mappingReady = effectiveMappingReadiness === 'ready'
  const persistedIdentityValidation = dirty ? null : source.mapping?.identityValidation ?? null
  const previewSummary = currentPreview?.businessSummary ?? null
  const identityPreview = identityPreviewDetails(currentPreview, persistedIdentityValidation)
  const previewItems = currentPreview?.items.filter(item => previewFilter === 'all' || (previewFilter === 'ready' ? item.ready : item.hasIssues)) ?? []
  const currentPreviewIndex = Math.min(previewIndex, Math.max(0, previewItems.length - 1))
  const currentPreviewItem = previewItems[currentPreviewIndex] ?? null
  const channelName = (channelId: string) => channelResources.ordered.find(resource => resource.id === channelId)?.displayName ?? formatChannelDisplayName(channelId, { showInstance: true })
  const requiredSourceFieldsMissing = (fields: FieldMapping[]) => SOURCE_FIELDS
    .filter(([, , required]) => required)
    .map(([field]) => field)
    .filter(field => {
      const mapping = fields.find(item => item.field === field)
      return !mapping || mapping.referenceType === 'disabled' || !mapping.referenceValue?.trim()
    })
  /**
   * Everything here mirrors a real backend rule (WORKSHEET_REQUIRED,
   * SOURCE_IDENTITY_REQUIRED, CHANNEL_MAPPING_REQUIRED,
   * CHANNEL_EXTERNAL_ID_REQUIRED, CHANNEL_STOCK_STATUS_REQUIRED in
   * source_workspace/service.py) so Save never silently fails against a
   * requirement the UI never mentioned. Disabled Channels and disabled
   * worksheet rules are intentionally exempt, matching that same contract.
   */
  const saveIssues: string[] = (() => {
    const issues: string[] = []
    if (!identityAuthorityComplete(identityAuthority)) {
      issues.push(translate('sources:sourceConfiguration.identityAuthorityRequired'))
    }
    if (effectiveWorksheetRuleMode === 'shared') {
      if (worksheetMode === 'selected' && selectedWorksheetNames.length === 0) {
        issues.push(translate('sources:sourceConfiguration.selectAtLeastOneWorksheet'))
      }
      for (const field of requiredSourceFieldsMissing(sourceFields)) {
        issues.push(translate('sources:sourceConfiguration.requiredSourceFieldMissing', { field: fieldDisplayName(field) }))
      }
      const enabledChannelIds = configuredChannelIds.filter(channelId => channelEnabled[channelId])
      if (enabledChannelIds.length === 0) {
        issues.push(translate('sources:sourceConfiguration.atLeastOneChannelRequired'))
      }
      for (const channelId of enabledChannelIds) {
        const connectorType = channels.find(item => item.channelId === channelId)?.connectorType
        const fields = channelFields[channelId] ?? emptyChannelFields()
        for (const issue of channelValidation(fields, true, connectorType, channels.find(item => item.channelId === channelId)?.capabilities)) {
          issues.push(`${channelName(channelId)}: ${issue}`)
        }
      }
    } else {
      const enabledRules = worksheetRules.filter(rule => rule.enabled)
      if (enabledRules.length === 0) {
        issues.push(translate('sources:sourceConfiguration.addAtLeastOneWorksheet'))
      }
      for (const rule of enabledRules) {
        for (const field of requiredSourceFieldsMissing(rule.sourceFields)) {
          issues.push(translate('sources:sourceConfiguration.requiredSourceFieldMissingForWorksheet', { field: fieldDisplayName(field), worksheet: rule.worksheetName }))
        }
        const enabledChannels = rule.channels.filter(channel => channel.enabled)
        if (enabledChannels.length === 0) {
          issues.push(translate('sources:sourceConfiguration.atLeastOneChannelRequiredForWorksheet', { worksheet: rule.worksheetName }))
        }
        for (const channel of enabledChannels) {
          const connectorType = channels.find(item => item.channelId === channel.channelId)?.connectorType
          for (const issue of channelValidation(channel.fields, true, connectorType, channels.find(item => item.channelId === channel.channelId)?.capabilities)) {
            issues.push(`${rule.worksheetName} — ${channelName(channel.channelId)}: ${issue}`)
          }
        }
      }
    }
    return issues
  })()
  const displayFieldReference = (mapping: FieldMapping) => mapping.referenceType === 'disabled'
    ? translate('sources:sourceConfiguration.disabled')
    : `${translate(REFERENCE_TYPE_LABELS[mapping.referenceType])}: ${mapping.referenceValue ?? '—'}`
  const identityKeyMappings = effectiveWorksheetRuleMode === 'shared'
    ? [displayFieldReference(sourceFields.find(field => field.field === 'source_key') ?? emptyMapping('source_key', true))]
    : worksheetRules
      .filter(rule => rule.enabled)
      .map(rule => `${rule.worksheetName}: ${displayFieldReference(rule.sourceFields.find(field => field.field === 'source_key') ?? emptyMapping('source_key', true))}`)
  const identityAuthorityLabel = identityAuthority.type === 'unspecified'
    ? translate('sources:sourceConfiguration.identityAuthorityUnspecified')
    : identityAuthority.displayLabel?.trim()
      || identityAuthorityOptions.find(option => option.value === identityAuthorityValue(identityAuthority))?.label
      || identityAuthority.systemIdentifier
      || translate('sources:sourceConfiguration.identityAuthorityOption.custom')
  const identityEvidenceLabel = identityPreview.evidence?.label?.trim()
    || (identityPreview.evidence?.kind === 'source_observation' && identityPreview.evidence.snapshotId != null
      ? translate('sources:sourceConfiguration.identityValidationSourceSnapshot', { id: identityPreview.evidence.snapshotId })
      : identityPreview.evidence?.kind === 'source_observation'
        ? translate('sources:sourceConfiguration.identityValidationSourceObservation')
        : identityPreview.evidence?.kind === 'flowhub_sheet_revision'
          ? translate('sources:sourceConfiguration.identityValidationSourceSheetRevision')
          : translate('sources:sourceConfiguration.identityValidationSourceNone'))
  const identityMappingLabels = identityPreview.mappingReferences.length > 0
    ? identityPreview.mappingReferences
    : identityKeyMappings
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
        {canCreateWorkspace && !sourceArchived && (
          <button className="fh-button-primary" type="button" disabled={!mappingReady} title={!mappingReady ? translate('sources:sourceConfiguration.identityValidationRequiredBeforeWorkspace') : undefined} onClick={() => void createWorkspace()}>
            <Icon name="workspace" /> {translate('sources:sourceConfiguration.openWorkspace')}
          </button>
        )}
      </div>

      <div className="mb-5 flex flex-wrap items-center gap-2">
        <nav className="no-scrollbar flex snap-x flex-1 gap-2 overflow-x-auto pb-1" aria-label={translate('sources:sourceConfiguration.sourceName')}>
          {navigationSections.map(({ id, labelKey, unsaved }) => {
            const active = activeNavId === id
            return (
              <button
                type="button"
                className={`${active ? 'fh-button-primary' : 'fh-button-secondary'} fh-button-sm snap-start whitespace-nowrap`}
                aria-current={active ? 'true' : undefined}
                onClick={() => goToSection(id)}
                key={id}
              >
                {translate(labelKey)}
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
      {sourceArchived && <div className="fh-alert fh-alert-info mb-5" role="status" data-testid="archived-source-read-only"><Icon name="info" /><span><strong>{translate('common:status.archived')}</strong> {translate('sources:sourceCenter.archivedReadOnly')}</span></div>}
      {externalSourceDisabled && !sourceArchived && <div className="fh-alert-warning mb-5" role="status"><Icon name="warning" /><span>{translate('sources:sourceCenter.setupReasonDisabled')}</span></div>}

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
            {canManageCommerce && !sourceArchived && source.sourceKind === 'external' && source.externalSourceId && <button className="fh-button-secondary fh-button-sm" type="button" onClick={() => navigate(`/commerce?tab=sources&resource=${encodeURIComponent(source.externalSourceId as string)}&returnTo=${encodeURIComponent(`/sources/${source.id}`)}`)}><Icon name="settings" /> {translate('sources:sourceConfiguration.manageConnection')}</button>}
            {canMutateSource && source.sourceKind === 'external' && <button className="fh-button-secondary fh-button-sm" type="button" disabled={connectionChecking || externalSourceDisabled} title={externalSourceDisabled ? translate('sources:sourceCenter.setupReasonDisabled') : undefined} onClick={() => void validateConfiguration()}><Icon name="testConnection" /> {connectionChecking ? translate('sources:sourceConfiguration.checkingConnection') : translate('commerce:commerceHub.testConnection')}</button>}
          </div>
        </div>
        <dl className="grid gap-x-6 gap-y-3 border-t border-border p-4 sm:grid-cols-2 xl:grid-cols-4">
          <div><dt className="fh-text-caption">{translate('sources:sourceConfiguration.sourceName')}</dt><dd className="font-medium text-text-base">{source.name}</dd></div>
          <div><dt className="fh-text-caption">{translate('sources:sourceConfiguration.sourceType')}</dt><dd className="font-medium text-text-base">{source.sourceKind === 'flowhub_sheet' ? translate('sources:sourceCenter.flowhubSheet') : source.sourceKind === 'imported_sheet' ? translate('sources:sourceCenter.importedSpreadsheet') : translate('sources:sourceCenter.linkedExternalSource')}</dd></div>
          <div><dt className="fh-text-caption">{translate('sources:sourceCenter.lifecycleStatus')}</dt><dd><Badge variant={sourceArchived ? 'neutral' : source.status === 'active' ? 'success' : 'disabled'}>{formatStatus(source.status)}</Badge></dd></div>
          {source.archivedAt && <div><dt className="fh-text-caption">{translate('sources:sourceCenter.archivedAt')}</dt><dd className="font-medium text-text-base">{formatDateTime(source.archivedAt)}</dd></div>}
          <div><dt className="fh-text-caption">{translate('sources:sourceConfiguration.columnSetupStatus')}</dt><dd><Badge variant={mappingReady ? 'success' : effectiveMappingReadiness ? 'warning' : 'warning'}>{mappingReady
            ? translate('common:status.ready')
            : effectiveMappingReadiness === 'identity_validation_blocked'
              ? translate('sources:sourceConfiguration.identityValidationBlockedShort')
              : effectiveMappingReadiness === 'identity_validation_pending'
                ? translate('sources:sourceConfiguration.identityValidationPendingShort')
                : translate('sources:sourceConfiguration.notConfigured')}</Badge></dd></div>
          {source.sourceKind === 'external' && <div><dt className="fh-text-caption">{translate('sources:sourceConfiguration.connectionStatus')}</dt><dd>{sourceArchived
            ? <Badge variant="neutral">{translate('common:status.archived')}</Badge>
            : <Badge variant={externalConnectionPresentation(externalConfig, externalSourceDisabled).variant}>{externalConnectionPresentation(externalConfig, externalSourceDisabled).label}</Badge>}</dd></div>}
          <div><dt className="fh-text-caption">{translate('sources:sourceConfiguration.section.accessScope')}</dt><dd className="font-medium text-text-base">{translate('sources:sourceConfiguration.accessScopePolicy')}</dd></div>
        </dl>
      </section>

      {source.legacyMapping && !source.mapping && (
        <section className="fh-alert-warning mb-5" role="status">
          <strong>{translate('sources:sourceConfiguration.legacyMappingDetected')}</strong>
          <p className="mt-1">{translate('sources:sourceConfiguration.legacyMappingAssignedToPrimaryChannel')}</p>
        </section>
      )}

      <fieldset className="min-w-0" id="data-mapping" disabled={!canMutateSource}>
      {source.sourceKind === 'external' && source.externalSourceId && (
        <div className="fh-alert fh-alert-info mb-3" role="note">
          <Icon name="info" />
          <span>{translate('sources:sourceConfiguration.dataSheetWorksheetScopeHelp')}</span>
        </div>
      )}
      <ConfigurationSection id="worksheet-discovery" openSignal={sectionSignal} defaultOpen title={translate('sources:sourceConfiguration.section.worksheetDiscovery')} description={translate('sources:sourceConfiguration.section.worksheetDiscoveryHelp')}>
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-3">
            <button
              className="fh-button-secondary"
              type="button"
              disabled={detectingWorksheets || externalSourceDisabled}
              title={externalSourceDisabled
                ? translate('commerce:commerceHub.sourceDisabledRemoteActions')
                : worksheetDetectionHelp}
              onClick={() => void detectWorksheets()}
            >
              <Icon name="refresh" /> {detectingWorksheets ? translate('sources:sourceConfiguration.detectingWorksheets') : translate('sources:sourceConfiguration.detectWorksheets')}
            </button>
            {source.sourceKind === 'external' && <button
              className="fh-button-secondary"
              type="button"
              disabled={detectingWorksheets || externalSourceDisabled || discoveryRefreshBlocked}
              title={externalSourceDisabled ? translate('commerce:commerceHub.sourceDisabledRemoteActions') : undefined}
              onClick={() => void detectWorksheets(true)}
            >
              <Icon name="refresh" /> {translate('sources:sourceConfiguration.refreshFromNextcloud')}
            </button>}
            {canManageCommerce && source.sourceKind === 'external' && source.externalSourceId && (
              <button className="fh-button-secondary" type="button" onClick={() => navigate(`/commerce?tab=sources&resource=${encodeURIComponent(source.externalSourceId as string)}&returnTo=${encodeURIComponent(`/sources/${source.id}`)}`)}>
                <Icon name="settings" /> {translate('sources:sourceConfiguration.manageConnection')}
              </button>
            )}
          </div>
          <p className="fh-text-caption" data-testid="worksheet-detection-help">{worksheetDetectionHelp}</p>
          {effectiveDiscoveryQuota?.enabled && <p className="fh-text-caption" data-testid="worksheet-discovery-quota">
            {translate('sources:sourceConfiguration.discoveryAllowance', {
              usage: effectiveDiscoveryQuota.usage,
              limit: effectiveDiscoveryQuota.limit,
            })}
          </p>}
          {worksheetDiscoveryFeedback && (() => {
            const feedback = worksheetDiscoveryFeedback ?? {
              variant: 'danger' as const,
              title: translate('sources:sourceConfiguration.discoveryLimitReachedTitle'),
              message: discoveryQuotaDescription(),
            }
            const alertClass = feedback.variant === 'success'
              ? 'fh-alert-success'
              : feedback.variant === 'warning'
                ? 'fh-alert-warning'
                : 'fh-alert-danger'
            return <div className={alertClass} role={feedback.variant === 'danger' ? 'alert' : 'status'} data-testid="worksheet-discovery-feedback">
              <strong>{feedback.title}</strong>
              <p className="mt-1">{feedback.message}</p>
            </div>
          })()}
          {detectedWorksheets.length > 0 && <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3" data-testid="detected-worksheet-inventory">
            {detectedWorksheets.map(item => <div className="rounded-lg border border-border bg-bg-subtle p-3" key={item.name}>
              <strong className="block truncate text-text-base">{item.name}</strong>
              <span className="fh-text-caption">{item.rowCount === null
                ? translate('sources:sourceConfiguration.worksheetRowCountUnavailable')
                : translate('sources:sourceConfiguration.worksheetRowCount', { count: item.rowCount })}</span>
            </div>)}
          </div>}
        </div>
      </ConfigurationSection>

      <div className="mt-3">
      <ConfigurationSection id="worksheet-participation" openSignal={sectionSignal} defaultOpen unsaved={dirty} title={translate('sources:sourceConfiguration.chooseParticipatingWorksheets')} description={translate('sources:sourceConfiguration.worksheetSellerHelp')}>
        <div className="space-y-4">
          <label className="fh-field-label">
            {translate('sources:sourceConfiguration.worksheetPolicy')}
            <select className="fh-input mt-1" value={worksheetMode} onChange={event => setWorksheetMode(event.target.value as 'all' | 'selected')}>
              <option value="selected">{translate('sources:sourceConfiguration.selectedWorksheet')}</option>
              <option value="all">{translate('sources:sourceConfiguration.allWorksheets')}</option>
            </select>
          </label>
          {worksheetMode === 'selected' && <fieldset className="fh-worksheet-picker">
            <legend className="px-2 font-medium text-text-base">{translate('sources:sourceConfiguration.chooseParticipatingWorksheets')}</legend>
            <div className="fh-worksheet-picker-toolbar">
              {detectedWorksheets.length > 0 && <><button className="fh-button-secondary fh-button-sm" type="button" onClick={() => setSelectedWorksheetNames(detectedWorksheets.map(item => item.name))}>{translate('sources:sourceConfiguration.selectAll')}</button><button className="fh-button-secondary fh-button-sm" type="button" onClick={() => setSelectedWorksheetNames([])}>{translate('sources:sourceConfiguration.clearAll')}</button></>}
            </div>
            {detectedWorksheets.length > 0 && <div className="fh-worksheet-picker-grid" data-testid="worksheet-picker-grid">
              {detectedWorksheets.map(item => {
                const selected = selectedWorksheetNames.includes(item.name)
                return <label className="fh-inline-check fh-worksheet-picker-item" data-selected={selected} key={item.name}><input type="checkbox" checked={selected} onChange={event => setSelectedWorksheetNames(current => event.target.checked ? [...new Set([...current, item.name])] : current.filter(name => name !== item.name))} /><span className="min-w-0"><strong className="block truncate text-text-base">{item.name}</strong></span></label>
              })}
            </div>}
            {selectedWorksheetNames.length === 0 && <p className="fh-alert-warning mt-3" role="alert">{translate('sources:sourceConfiguration.selectAtLeastOneWorksheet')}</p>}
          </fieldset>}
        </div>
      </ConfigurationSection>
      </div>

      {participatingWorksheetCount > 1 && <div className="mt-3">
      <ConfigurationSection id="worksheet-rules" openSignal={sectionSignal} unsaved={dirty} title={translate('sources:sourceConfiguration.worksheetRules')} description={translate('sources:sourceConfiguration.worksheetRulesSectionHelp')}>
        <div className="mt-4 grid gap-3 lg:grid-cols-2">
          <label className={`rounded-xl border p-4 ${worksheetRuleMode === 'shared' ? 'border-accent bg-accent/5' : 'border-border'}`} title={translate('sources:sourceConfiguration.sharedWorksheetRulesHelp')}>
            <span className="flex items-center gap-2 font-medium text-text-base"><input type="radio" name="worksheet-rule-mode" value="shared" checked={worksheetRuleMode === 'shared'} onChange={() => changeWorksheetRuleMode('shared')} />{translate('sources:sourceConfiguration.sharedWorksheetRules')}</span>
          </label>
          <label className={`rounded-xl border p-4 ${worksheetRuleMode === 'per_worksheet' ? 'border-accent bg-accent/5' : 'border-border'} ${detectedWorksheets.length === 0 && worksheetRules.length === 0 ? 'opacity-70' : ''}`} title={translate('sources:sourceConfiguration.separateWorksheetRulesHelp')}>
            <span className="flex items-center gap-2 font-medium text-text-base"><input type="radio" name="worksheet-rule-mode" value="per_worksheet" disabled={detectedWorksheets.length === 0 && worksheetRules.length === 0} checked={worksheetRuleMode === 'per_worksheet'} onChange={() => changeWorksheetRuleMode('per_worksheet')} />{translate('sources:sourceConfiguration.separateWorksheetRules')}</span>
            {detectedWorksheets.length === 0 && worksheetRules.length === 0 && <span className="fh-text-caption mt-2 block">{translate('sources:sourceConfiguration.detectWorksheetsBeforeSeparateRules')}</span>}
          </label>
        </div>
      </ConfigurationSection>
      </div>}

      <div className="mt-3">
        <ConfigurationSection id="source-identity" openSignal={sectionSignal} defaultOpen unsaved={dirty} title={translate('sources:sourceConfiguration.sourceIdentity')} description={translate('sources:sourceConfiguration.identityAuthorityHelp')}>
          <div className="grid gap-3 lg:max-w-2xl">
            <label className="grid gap-1">
              <MappingFieldLabel label={translate('sources:sourceConfiguration.identityAuthority')} required help={translate('sources:sourceConfiguration.identityAuthorityHelp')} />
              <select
                className="fh-input"
                value={identityAuthorityValue(identityAuthority)}
                required
                aria-required="true"
                aria-invalid={!identityAuthorityComplete(identityAuthority) || undefined}
                aria-describedby="identity-authority-help"
                onChange={event => changeIdentityAuthority(event.target.value)}
              >
                <option value="">{translate('sources:sourceConfiguration.chooseIdentityAuthority')}</option>
                {identityAuthorityOptions.map(option => <option value={option.value} key={option.value}>{option.label}</option>)}
                <option value="custom">{translate('sources:sourceConfiguration.identityAuthorityOption.custom')}</option>
              </select>
            </label>
            {identityAuthority.type === 'custom' && <div className="grid gap-3 sm:grid-cols-2">
              <label className="grid gap-1">
                <MappingFieldLabel label={translate('sources:sourceConfiguration.identityAuthoritySystemIdentifier')} required />
                <input
                  className="fh-input"
                  value={identityAuthority.systemIdentifier ?? ''}
                  required
                  aria-required="true"
                  onChange={event => setIdentityAuthority(current => ({ ...current, systemIdentifier: event.target.value }))}
                />
              </label>
              <label className="grid gap-1">
                <MappingFieldLabel label={translate('sources:sourceConfiguration.identityAuthorityDisplayLabel')} />
                <input className="fh-input" value={identityAuthority.displayLabel ?? ''} onChange={event => setIdentityAuthority(current => ({ ...current, displayLabel: event.target.value || null }))} />
              </label>
            </div>}
            <p className="fh-text-caption" id="identity-authority-help">{translate('sources:sourceConfiguration.identityAuthorityDoesNotEnableChannel')}</p>
          </div>
        </ConfigurationSection>
      </div>

      <div className={`mt-3 ${renderedWorksheetRuleMode === 'per_worksheet' ? 'hidden' : ''}`}>
        <ConfigurationSection id="workbook" openSignal={sectionSignal} unsaved={dirty} title={translate('sources:sourceConfiguration.section.workbook')} description={translate('sources:sourceConfiguration.section.workbookHelp')}>
          <div className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
          <label className="fh-field-label">
            {translate('sources:sourceConfiguration.dataStartsAtRow')}
            <input className="fh-input mt-1" type="number" min="1" value={dataStartRow} onChange={event => setDataStartRow(Number(event.target.value))} />
          </label>
        </div>
        <div>
          <h2 className="fh-section-title">{translate('sources:sourceConfiguration.sourceProductFields')}</h2>
          <p className="fh-text-caption">{translate('sources:sourceConfiguration.unmappedColumnsAreIgnoredHeaderSuggestionsNever')}</p>
        </div>
        <div className="grid gap-4">
          {SOURCE_FIELD_GROUPS.map(group => {
            const controls = <>
            <p className="fh-text-caption mb-3">{translate(group.helpKey)}</p>
            {group.id === 'primary' && <p className="fh-text-caption mb-3">{translate('sources:sourceConfiguration.sourceProductCommercialHelp')}</p>}
            <div className="grid gap-3 lg:grid-cols-2">
              {SOURCE_FIELDS.filter(([field]) => (group.fields as readonly string[]).includes(field)).map(([field, labelKey, required]) => (
                <label className="grid gap-1" key={field}>
                  <MappingFieldLabel label={translate(labelKey)} required={required} help={field === 'source_key' ? translate('sources:sourceConfiguration.sourceProductKeyHelp') : undefined} />
                  <SmartColumnInput
                    mapping={sourceFields.find(item => item.field === field)!}
                    columns={sharedDiscoveredColumns}
                    required={required}
                    allowInternalColumnId={source.sourceKind === 'flowhub_sheet'}
                    onChange={value => updateSourceField(field, value)}
                  />
                </label>
              ))}
            </div>
            </>
            return group.id === 'classification'
              ? <section className="rounded-lg border border-dashed border-border bg-bg-base p-3" data-source-field-group={group.id} key={group.id}>
                  <h3 className="font-medium text-text-base">{translate(group.titleKey)}</h3>
                  <div className="mt-3">{controls}</div>
                </section>
              : <fieldset className="rounded-lg border border-border bg-bg-subtle p-3" data-source-field-group={group.id} key={group.id}>
                  <legend className="px-1 font-medium text-text-base">{translate(group.titleKey)}</legend>
                  {controls}
                </fieldset>
          })}
        </div>
          </div>
        </ConfigurationSection>
      </div>

      {source.sourceKind === 'external' && source.externalSourceId && (
        <div className="mt-3">
          <ConfigurationSection id="read-policy" openSignal={sectionSignal} unsaved={readPolicyDirty} title={translate('sources:sourceConfiguration.section.readPolicy')} description={translate('sources:sourceConfiguration.section.readPolicyHelp')}>
            <div className="flex flex-col gap-3">
              {readQuota && (
                <div className="rounded-lg border border-border bg-surface-subtle p-3" data-testid="remote-read-allowance" role="status">
                  <h3 className="font-medium text-text-base">{translate('sources:sourceConfiguration.remoteReads')}</h3>
                  <p className="mt-1 text-sm text-text-muted">{translate('sources:sourceConfiguration.remoteReadsUsage', { usage: readQuota.usage, limit: readQuota.limit })}</p>
                  <p className={`text-sm font-medium ${remoteReadQuotaExhausted ? 'text-danger' : 'text-text-base'}`}>
                    {remoteReadQuotaExhausted
                      ? translate('sources:sourceConfiguration.remoteReadsLimitReachedShort')
                      : translate('sources:sourceConfiguration.remoteReadsRemaining', { count: readQuota.remaining })}
                  </p>
                  <p className="text-sm text-text-muted">{translate('sources:sourceConfiguration.remoteReadsReset', { reset: formatQuotaReset(readQuota.resetAt) })}</p>
                </div>
              )}
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
              <p className="fh-text-caption">{translate('sources:sourceConfiguration.remoteReadsActionHelp')}</p>
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

      <div className={`mt-5 space-y-3 ${renderedWorksheetRuleMode === 'per_worksheet' ? 'hidden' : ''}`}>
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
                const requiredFields = requiredChannelMappingFields(channel.connectorType, channel.capabilities)
                const issues = channelValidation(fields, enabled, channel.connectorType, channel.capabilities)
                const configured = channel.configured !== false
                const mappedStatus = channelMappedStatus(fields, channel.connectorType, channel.capabilities)
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
                  {CHANNEL_FIELDS.map(([field, labelKey]) => {
                    const label = field === 'external_id'
                      ? translate('sources:sourceConfiguration.channelProductIdentifier', { channel: orderedChannel.displayName })
                      : translate(labelKey)
                    const required = enabled && requiredFields.has(field)
                    return <td key={field}><div className="grid gap-1">
                      <MappingFieldLabel label={label} required={required} help={field === 'external_id' ? translate('sources:sourceConfiguration.channelProductIdentifierHelp') : undefined} />
                      <SmartColumnInput mapping={fields.find(item => item.field === field)!} columns={sharedDiscoveredColumns} disabled={controlsDisabled} required={required} fieldLabel={label} allowInternalColumnId={source.sourceKind === 'flowhub_sheet'} onChange={value => updateChannelField(channel.channelId, field, value)} />
                    </div></td>
                  })}
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

      {renderedWorksheetRuleMode === 'per_worksheet' && <div className="mt-5 space-y-3">
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
          rowCount={detectedWorksheets.find(item => item.name === rule.worksheetName)?.rowCount ?? undefined}
          columns={detectedWorksheets.find(item => item.name === rule.worksheetName)?.columns ?? []}
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
            <h2 className="fh-section-title">{translate('sources:sourceConfiguration.identityValidation')}</h2>
            <p className="fh-text-caption">{translate('sources:sourceConfiguration.localIdentityValidationHelp')}</p>
          </div>
          <button className="fh-button-secondary" type="button" disabled={previewing} onClick={() => void loadPreview()}>
            {previewing ? translate('sources:sourceConfiguration.loading') : translate('sources:sourceConfiguration.validateIdentityFromLocalData')}
          </button>
        </div>
        <section className={`border-t border-border p-4 ${identityPreview.status === 'pass' ? 'fh-alert fh-alert-success' : identityPreview.status === 'blocked' ? 'fh-alert-warning' : 'fh-alert fh-alert-info'}`} data-testid="source-identity-preview" aria-live="polite">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="font-medium text-text-base">{translate('sources:sourceConfiguration.identityValidation')}</h3>
            <Badge variant={identityPreview.status === 'pass' ? 'success' : identityPreview.status === 'blocked' ? 'warning' : 'pending'}>{translate(identityPreview.status === 'pass'
              ? 'sources:sourceConfiguration.identityValidationPass'
              : identityPreview.status === 'blocked'
                ? 'sources:sourceConfiguration.identityValidationBlocked'
                : 'sources:sourceConfiguration.identityValidationPending')}</Badge>
          </div>
          <dl className="mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
            <div><dt className="fh-text-caption">{translate('sources:sourceConfiguration.identityAuthority')}</dt><dd className="font-medium text-text-base">{identityAuthorityLabel}</dd></div>
            <div><dt className="fh-text-caption">{translate('sources:sourceConfiguration.identityMappedKeyColumn')}</dt><dd className="font-medium text-text-base">{identityMappingLabels.join(' · ')}</dd></div>
            <div><dt className="fh-text-caption">{translate('sources:sourceConfiguration.identityValidationSource')}</dt><dd className="font-medium text-text-base">{identityEvidenceLabel}</dd></div>
            <div><dt className="fh-text-caption">{translate('sources:sourceConfiguration.identityParticipatingRowCount')}</dt><dd className="font-medium text-text-base">{identityPreview.participatingRowCount == null ? '—' : formatNumber(identityPreview.participatingRowCount)}</dd></div>
            <div><dt className="fh-text-caption">{translate('sources:sourceConfiguration.identityValidKeyCount')}</dt><dd className="font-medium text-text-base">{identityPreview.validKeyCount == null ? '—' : formatNumber(identityPreview.validKeyCount)}</dd></div>
            <div><dt className="fh-text-caption">{translate('sources:sourceConfiguration.identityMissingKeyCount')}</dt><dd className="font-medium text-text-base">{identityPreview.missingKeyCount == null ? '—' : formatNumber(identityPreview.missingKeyCount)}</dd></div>
            <div><dt className="fh-text-caption">{translate('sources:sourceConfiguration.identityDuplicateKeyCount')}</dt><dd className="font-medium text-text-base">{identityPreview.duplicateKeyCount == null ? '—' : formatNumber(identityPreview.duplicateKeyCount)}</dd></div>
            <div><dt className="fh-text-caption">{translate('sources:sourceConfiguration.identityBindingConflictCount')}</dt><dd className="font-medium text-text-base">{identityPreview.bindingConflictCount == null ? '—' : formatNumber(identityPreview.bindingConflictCount)}</dd></div>
          </dl>
          {identityPreview.status === 'pending' && <div className="mt-3 space-y-2">
            <p>{translate('sources:sourceConfiguration.noLocalIdentityData')}</p>
            {source.sourceKind === 'external' && source.externalSourceId && readPolicy.manual_read_allowed && <button className="fh-button-secondary fh-button-sm" type="button" disabled={reading || externalSourceDisabled || remoteReadQuotaExhausted} title={remoteReadQuotaExhausted ? quotaLimitDescription() : translate('sources:sourceConfiguration.readSourceConsumesAllowance')} onClick={() => void readNow()}><Icon name="refresh" /> {translate('sources:sourceConfiguration.readSource')}</button>}
            {remoteReadQuotaExhausted && <p className="fh-text-caption text-danger">{translate('sources:sourceConfiguration.readSourceQuotaExhausted')}</p>}
          </div>}
          {identityPreview.status === 'blocked' && <div className="mt-3 space-y-2">
            {identityPreview.missingKeyCount != null && identityPreview.missingKeyCount > 0 && <p>{translate('sources:sourceConfiguration.identityMissingKeysSummary', { count: identityPreview.missingKeyCount })}</p>}
            {identityPreview.missingRows.length > 0 && <p className="fh-text-caption">{translate('sources:sourceConfiguration.identityAffectedRows', { rows: identityPreview.missingRows.join(', ') })}</p>}
            {identityPreview.duplicateRowCount != null && identityPreview.duplicateRowCount > 0 && <p>{translate('sources:sourceConfiguration.identityDuplicateKeysSummary', { count: identityPreview.duplicateRowCount })}</p>}
            {identityPreview.bindingConflictCount != null && identityPreview.bindingConflictCount > 0 && <p>{translate('sources:sourceConfiguration.identityBindingConflictsSummary', { count: identityPreview.bindingConflictCount })}</p>}
            {identityPreview.duplicates.map((duplicate, index) => <div className="rounded-lg border border-warning/30 bg-bg-base p-3" key={`${duplicate.key}-${index}`}>
              {duplicate.key && <p className="font-medium text-text-base">{translate('sources:sourceConfiguration.identityDuplicateKey', { key: duplicate.key })}</p>}
              <p className="fh-text-caption">{translate('sources:sourceConfiguration.identityAffectedRows', { rows: duplicate.rows.join(', ') })}</p>
            </div>)}
            {identityPreview.bindingConflicts.map((conflict, index) => <div className="rounded-lg border border-warning/30 bg-bg-base p-3" key={`${conflict.key}-${index}`}>
              <p className="font-medium text-text-base">{translate('sources:sourceConfiguration.identityBindingConflictKey', { key: conflict.key })}</p>
              <p className="fh-text-caption">{translate('sources:sourceConfiguration.identityAffectedRows', { rows: conflict.rows.join(', ') })}</p>
              {conflict.boundCanonicalProductId && <p className="fh-text-caption">{translate('sources:sourceConfiguration.identityBoundCanonicalProduct', { id: conflict.boundCanonicalProductId })}</p>}
              {conflict.conflictingCanonicalProductIds.length > 0 && <p className="fh-text-caption">{translate('sources:sourceConfiguration.identityConflictingCanonicalProducts', { ids: conflict.conflictingCanonicalProductIds.join(', ') })}</p>}
            </div>)}
          </div>}
        </section>
        {currentPreview && (
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
            <details className="border-t border-border p-4"><summary className="cursor-pointer fh-text-caption">{translate('sources:sourceConfiguration.technicalDetails')}</summary><p className="fh-text-caption mt-2">{translate('sources:sourceConfiguration.recognized')}: {currentPreview.recognized} · {translate('sources:sourceConfiguration.ignored')}: {currentPreview.ignored}</p></details>
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

      {canManageSources && source.status === 'active' && (
        <section className="fh-card fh-card-pad mt-5 border-danger/30" aria-labelledby="source-danger-zone-title">
          <h2 className="fh-section-title" id="source-danger-zone-title">{translate('sources:sourceConfiguration.dangerZone')}</h2>
          <p className="fh-text-caption mt-2">{translate('sources:sourceConfiguration.deleteSourceHelp')}</p>
          <button className="fh-button-danger mt-4" type="button" onClick={() => void openRemoval()}>
            <Icon name="delete" /> {translate('sources:sourceCenter.deleteSourcePermanently')}
          </button>
        </section>
      )}

      {canMutateSource && saveIssues.length > 0 && (
        <div className="fh-alert-warning mt-5" role="alert" id="source-configuration-save-issues" data-testid="source-configuration-save-issues">
          <p className="font-medium">{translate('sources:sourceConfiguration.saveBlockedSummary')}</p>
          <ul className="mt-1 list-disc ps-5">
            {saveIssues.map((issue, index) => <li key={index}>{issue}</li>)}
          </ul>
        </div>
      )}

      <div className="fh-sticky-action-bar sticky bottom-2 mt-5 flex flex-wrap items-center gap-2 rounded-xl border border-border bg-bg-base/95 p-2 shadow-lg backdrop-blur sm:bottom-3 sm:gap-3 sm:p-3" data-testid="source-configuration-actions">
        <Badge variant={dirty ? 'warning' : 'success'}>{dirty ? translate('sources:sourceConfiguration.unsavedChanges') : translate('sources:sourceConfiguration.allChangesSaved')}</Badge>
        <span className="fh-text-caption hidden sm:inline">{translate('sources:sourceConfiguration.savedAsImmutableRevision')}</span>
        <div className="order-last grid w-full grid-cols-2 gap-2 sm:order-none sm:ms-auto sm:flex sm:w-auto sm:flex-wrap">
          {canMutateSource && source.sourceKind === 'external' && <button className="fh-button-secondary fh-button-sm w-full sm:w-auto" type="button" disabled={connectionChecking || externalSourceDisabled} title={externalSourceDisabled ? translate('sources:sourceCenter.setupReasonDisabled') : undefined} onClick={() => void validateConfiguration()}><Icon name="testConnection" /> {connectionChecking ? translate('sources:sourceConfiguration.checkingConnection') : translate('commerce:commerceHub.testConnection')}</button>}
          {canMutateSource && source.sourceKind === 'external' && source.externalSourceId && readPolicy.manual_read_allowed && (
            <button className="fh-button-secondary fh-button-sm w-full sm:w-auto" type="button" disabled={reading || externalSourceDisabled || remoteReadQuotaExhausted} title={externalSourceDisabled ? translate('sources:sourceCenter.setupReasonDisabled') : remoteReadQuotaExhausted ? quotaLimitDescription() : undefined} onClick={() => void readNow()}><Icon name="refresh" /> {reading ? translate('commerce:commerceHub.reading') : translate('commerce:commerceHub.readNow')}</button>
          )}
          {canMutateSource && <button
            className="fh-button-primary fh-button-sm order-first col-span-2 w-full sm:order-none sm:w-auto"
            type="button"
            disabled={saving}
            aria-describedby={saveIssues.length > 0 ? 'source-configuration-save-issues' : undefined}
            title={saveIssues.length > 0 ? saveIssues[0] : undefined}
            onClick={() => void save()}
          ><Icon name="save" /> {saving ? translate('sources:sourceConfiguration.saving') : translate('sources:sourceConfiguration.saveMappingRevision')}</button>}
          <button className="fh-button-secondary fh-button-sm w-full sm:w-auto" type="button" onClick={closeConfiguration}><Icon name="previous" /> {translate('sources:sourceConfiguration.backToSources')}</button>
        </div>
      </div>

      {removalOpen && source && (
        <div className="fh-overlay-backdrop fixed inset-0 grid place-items-center bg-black/50 p-4" role="dialog" aria-modal="true" aria-labelledby="source-delete-title" aria-describedby="source-delete-description">
          <div className="fh-card fh-card-pad w-full max-w-lg">
            <h2 className="fh-page-title" id="source-delete-title">{translate('sources:sourceCenter.deleteSourcePermanently')}</h2>
            <p className="mt-3 text-text-base" id="source-delete-description">{translate('sources:sourceCenter.confirmSourceRemoval', { source: source.name })}</p>
            <div className="fh-alert-warning mt-4" role="note" aria-live="polite">
              <strong>{checkingRemoval
                ? translate('sources:sourceCenter.checkingHistory')
                : removalImpact?.blockers && Object.keys(removalImpact.blockers).length > 0
                  ? translate('sources:sourceConfiguration.removalBlocked')
                  : translate('sources:sourceCenter.deleteSourcePermanently')}</strong>
              <p className="mt-1">{removalImpact?.blockers && Object.keys(removalImpact.blockers).length > 0
                  ? translate('sources:sourceConfiguration.removalBlockedHelp')
                  : translate('sources:sourceCenter.safeRemovalImpact')}</p>
              {removalImpact && Object.keys(removalImpact.protectedHistory).length > 0 && (
                <p className="mt-2 fh-text-caption">{translate('sources:sourceCenter.protectedRecords', {
                  value: formatNumber(Object.values(removalImpact.protectedHistory).reduce((sum, count) => sum + count, 0)),
                })}</p>
              )}
            </div>
            <label className="fh-field mt-4">
              <span className="fh-help-text">{translate('sources:sourceConfiguration.typeSourceNameToConfirm', { source: source.name })}</span>
              <input
                autoComplete="off"
                className="fh-input"
                name="source-delete-confirmation"
                value={confirmationName}
                onChange={event => setConfirmationName(event.target.value)}
              />
            </label>
            <label className="mt-3 flex items-start gap-2 text-sm">
              <input type="checkbox" checked={confirmHistoryPolicy} onChange={event => setConfirmHistoryPolicy(event.target.checked)} />
              <span>{translate('sources:sourceCenter.confirmHistoryPolicy')}</span>
            </label>
            <div className="mt-5 flex justify-end gap-2">
              <button className="fh-button-secondary" type="button" disabled={deleting} onClick={closeRemoval}>{translate('common:action.cancel')}</button>
              <button className="fh-button-secondary" type="button" disabled={deleting || checkingRemoval || !removalImpact || Object.keys(removalImpact.blockers).length > 0 || confirmationName !== source.name} onClick={() => void archiveCurrentSource()}><Icon name="archive" /> {translate('sources:sourceCenter.archiveSource')}</button>
              <button
                className="fh-button-danger"
                type="button"
                disabled={deleting || checkingRemoval || !removalImpact || Object.keys(removalImpact.blockers).length > 0 || confirmationName !== source.name || !confirmHistoryPolicy}
                onClick={() => void removeSource()}
              >
                <Icon name="delete" /> {deleting
                  ? translate('sources:sourceCenter.checkingHistory')
                    : translate('sources:sourceCenter.deleteSourcePermanently')}
              </button>
            </div>
          </div>
        </div>
      )}

      {channelSetupId && canManageCommerce && <div className="fh-overlay-backdrop fixed inset-0 grid place-items-center bg-black/50 p-4" role="dialog" aria-modal="true" aria-label={translate('commerce:commerceHub.addChannel')}>
        <div className="max-h-[calc(100vh-2rem)] w-full max-w-[45rem] overflow-y-auto">
          {channelSetupLoading ? <div className="fh-card fh-card-pad fh-text-caption" role="status">{translate('commerce:commerceHub.loadingChannelConfiguration')}</div> : channelSetupError ? <div className="fh-card fh-card-pad" role="alert"><p className="fh-section-title">{translate('commerce:commerceHub.unableToLoadCommerceHub')}</p><div className="mt-4 flex gap-2"><button className="fh-button-secondary" type="button" onClick={closeChannelSetup}>{translate('common:action.cancel')}</button><button className="fh-button-primary" type="button" onClick={() => void openChannelSetup(channelSetupId === 'new' ? undefined : channelSetupId)}>{translate('common:action.retry')}</button></div></div> : <ConfigPanel kind="channel" types={channelTypes} initialResourceId={channelSetupId === 'new' ? null : channelSetupId} headingLevel={2} onCancel={closeChannelSetup} onSaved={handleChannelSetupSaved} />}
        </div>
      </div>}

      {pendingSharedChannelCopy && <div className="fh-overlay-backdrop fixed inset-0 grid place-items-center bg-black/50 p-4" role="dialog" aria-modal="true" aria-labelledby="copy-channel-title">
        <div className="fh-card fh-card-pad w-full max-w-xl">
          <h2 className="fh-page-title" id="copy-channel-title">{translate('sources:sourceConfiguration.copyChannelSettings')}</h2>
          <p className="mt-2 fh-text-caption">{translate('sources:sourceConfiguration.copyChannelPreview', { source: channelName(pendingSharedChannelCopy.sourceChannelId), destination: channelName(pendingSharedChannelCopy.targetChannelId) })}</p>
          <dl className="mt-4 grid gap-2 rounded-xl border border-border bg-bg-subtle p-3 sm:grid-cols-2">{(channelFields[pendingSharedChannelCopy.sourceChannelId] ?? []).map(field => <div key={field.field}><dt className="fh-text-caption">{fieldDisplayName(field.field)}</dt><dd className="font-medium text-text-base">{displayFieldReference(field)}</dd></div>)}</dl>
          <p className="fh-alert-warning mt-4">{translate('sources:sourceConfiguration.copyNeverChangesTechnicalChannelIdentity')}</p>
          <div className="mt-5 flex justify-end gap-2"><button className="fh-button-secondary" type="button" onClick={() => setPendingSharedChannelCopy(null)}>{translate('common:action.cancel')}</button><button className="fh-button-primary" type="button" onClick={applySharedChannelCopy}>{translate('sources:sourceConfiguration.confirmCopy')}</button></div>
        </div>
      </div>}

      {pendingCopy && <div className="fh-overlay-backdrop fixed inset-0 grid place-items-center bg-black/50 p-4" role="dialog" aria-modal="true" aria-labelledby="copy-worksheet-title">
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
