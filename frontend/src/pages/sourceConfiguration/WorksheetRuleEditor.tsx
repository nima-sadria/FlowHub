import { useId, useMemo, useState } from 'react'
import Icon from '../../components/Icon'
import BrandIcon from '../../components/BrandIcon'
import { ResourceOptionGroups, ResourceSectionList, ResourceStateBadge } from '../../components/ResourceOrdering'
import { prepareResourceCollection, sourceChannelSignals } from '../../features/resourceOrdering/resourceOrdering'
import type { FieldMapping, ReferenceType, SourceChannel, SourceWorksheetRule } from '../../features/sourceWorkspace/types'
import { translate } from '../../i18n'

export const SOURCE_FIELD_DEFINITIONS = [
  ['name', 'sources:sourceConfiguration.sourceProductName', true],
  ['source_key', 'sources:sourceConfiguration.sourceProductKey', false],
  ['category', 'sources:sourceConfiguration.category', false],
  ['brand', 'sources:sourceConfiguration.brand', false],
  ['cost', 'sources:sourceConfiguration.cost', false],
] as const

export const CHANNEL_FIELD_DEFINITIONS = [
  ['external_id', 'sources:sourceConfiguration.productIdentifier'],
  ['price', 'common:field.price'],
  ['stock', 'common:field.stock'],
  ['status', 'common:field.status'],
] as const

export const DEFAULT_SOURCE_VALUE_POLICY: Record<string, string> = {
  blank: 'no_change', x: 'unavailable', dash: 'no_change', zero: 'explicit_zero',
  formula: 'calculated_value', invalid: 'blocked',
}

const POLICY_OPTIONS: Record<string, Array<[string, string]>> = {
  blank: [['no_change', 'sources:sourceConfiguration.noTargetChange'], ['blocked', 'sources:sourceConfiguration.blockedIssue']],
  x: [['unavailable', 'sources:sourceConfiguration.noListingUnavailable'], ['no_change', 'sources:sourceConfiguration.noTargetChange'], ['blocked', 'sources:sourceConfiguration.blockedIssue']],
  dash: [['no_change', 'sources:sourceConfiguration.noTargetChange'], ['unavailable', 'common:status.unavailable'], ['blocked', 'sources:sourceConfiguration.blockedIssue']],
  zero: [['explicit_zero', 'sources:sourceConfiguration.explicitZero'], ['no_change', 'sources:sourceConfiguration.noTargetChange'], ['blocked', 'sources:sourceConfiguration.blockedIssue']],
  formula: [['calculated_value', 'sources:sourceConfiguration.useEvaluatedResult'], ['blocked', 'sources:sourceConfiguration.blockedIssue']],
  invalid: [['blocked', 'sources:sourceConfiguration.blockedIssue']],
}

export const emptyFieldMapping = (field: string, required = false): FieldMapping => ({ field, referenceType: 'disabled', referenceValue: null, required })
export const emptySourceFields = (): FieldMapping[] => SOURCE_FIELD_DEFINITIONS.map(([field, _label, required]) => emptyFieldMapping(field, required))
export const emptyChannelFields = (): FieldMapping[] => CHANNEL_FIELD_DEFINITIONS.map(([field]) => emptyFieldMapping(field))

function fieldDisplayName(field: string): string {
  const sourceDefinition = SOURCE_FIELD_DEFINITIONS.find(([candidate]) => candidate === field)
  const channelDefinition = CHANNEL_FIELD_DEFINITIONS.find(([candidate]) => candidate === field)
  const translationKey = sourceDefinition?.[1] ?? channelDefinition?.[1]
  return translationKey ? translate(translationKey) : field
}

function sourceFieldMissing(mapping: FieldMapping): boolean {
  return Boolean((mapping.required || mapping.field === 'name') && (mapping.referenceType === 'disabled' || !mapping.referenceValue?.trim()))
}

export function createWorksheetRule(name: string): SourceWorksheetRule {
  return { worksheetName: name, enabled: true, dataStartRow: 2, valuePolicy: { ...DEFAULT_SOURCE_VALUE_POLICY }, sourceFields: emptySourceFields(), channels: [] }
}

function ColumnSelector({ mapping, disabled, allowInternalColumnId, invalid = false, describedBy, onChange }: { mapping: FieldMapping; disabled: boolean; allowInternalColumnId: boolean; invalid?: boolean; describedBy?: string; onChange: (mapping: FieldMapping) => void }) {
  return <div className="grid min-w-0 gap-2 sm:grid-cols-[170px_minmax(0,1fr)]">
    <label className="grid gap-1"><span className="fh-text-caption">{translate('sources:sourceConfiguration.mappingMethod')}</span><select className="fh-input" disabled={disabled} value={mapping.referenceType} aria-label={translate('sources:sourceConfiguration.referenceType', { field: fieldDisplayName(mapping.field) })} aria-invalid={invalid || undefined} aria-describedby={invalid ? describedBy : undefined} onChange={event => onChange({ ...mapping, referenceType: event.target.value as ReferenceType, referenceValue: event.target.value === 'disabled' ? null : mapping.referenceValue })}><option value="disabled">{translate('sources:sourceConfiguration.disabled')}</option><option value="column_letter">{translate('sources:sourceConfiguration.columnLetter')}</option><option value="header_name">{translate('sources:sourceConfiguration.exactHeader')}</option>{allowInternalColumnId && <option value="column_id">{translate('sources:sourceConfiguration.internalColumnId')}</option>}</select></label>
    <label className="grid gap-1"><span className="fh-text-caption">{translate('sources:sourceConfiguration.column')}</span><input className="fh-input" disabled={disabled || mapping.referenceType === 'disabled'} value={mapping.referenceValue ?? ''} aria-label={translate('sources:sourceConfiguration.columnReference', { field: fieldDisplayName(mapping.field) })} aria-invalid={invalid || undefined} aria-describedby={invalid ? describedBy : undefined} title={mapping.referenceType === 'column_letter' ? translate('sources:sourceConfiguration.exampleColumn') : translate('sources:sourceConfiguration.exactColumnReference')} onChange={event => onChange({ ...mapping, referenceValue: event.target.value })} /></label>
  </div>
}

export function channelValidationIssues(fields: FieldMapping[], enabled: boolean): string[] {
  if (!enabled) return []
  const issues: string[] = []
  const identifier = fields.find(item => item.field === 'external_id')
  if (!identifier || identifier.referenceType === 'disabled' || !identifier.referenceValue?.trim()) issues.push(translate('sources:sourceConfiguration.productIdentifierRequired'))
  const refs = new Map<string, string>()
  for (const field of fields) {
    if (field.referenceType === 'disabled' || !field.referenceValue?.trim()) continue
    const key = `${field.referenceType}:${field.referenceValue.trim().toLocaleLowerCase()}`
    const prior = refs.get(key)
    if (prior) issues.push(translate('sources:sourceConfiguration.conflictingColumnMapping', { first: fieldDisplayName(prior), second: fieldDisplayName(field.field) }))
    else refs.set(key, field.field)
  }
  return issues
}

export type WorksheetCopyIntent =
  | { kind: 'shared_fields'; worksheetName: string }
  | { kind: 'channel_to_worksheets'; worksheetName: string; channelId: string }
  | { kind: 'channel_to_channel'; worksheetName: string; sourceChannelId: string; targetChannelId: string }

interface Props {
  rule: SourceWorksheetRule
  rowCount?: number
  channels: SourceChannel[]
  sourceKind: 'flowhub_sheet' | 'imported_sheet' | 'external'
  selected?: boolean
  expanded?: boolean
  onSelectedChange?: (selected: boolean) => void
  onExpandedChange?: (expanded: boolean) => void
  onChange: (rule: SourceWorksheetRule) => void
  onRemove: () => void
  onRequestCopy?: (intent: WorksheetCopyIntent) => void
}

export default function WorksheetRuleEditor({ rule, rowCount, channels, sourceKind, selected = false, expanded = rule.enabled, onSelectedChange = () => {}, onExpandedChange = () => {}, onChange, onRemove, onRequestCopy = () => {} }: Props) {
  const [copyFrom, setCopyFrom] = useState<Record<string, string>>({})
  const [expandedChannels, setExpandedChannels] = useState<string[]>([])
  const editorId = useId().replace(/:/g, '')
  const sourceErrorId = `${editorId}-required-product-column`
  const channelResources = useMemo(() => prepareResourceCollection(channels, sourceChannelSignals), [channels])
  const missingSourceFields = rule.enabled ? rule.sourceFields.filter(sourceFieldMissing) : []
  const configured = (channelId: string) => rule.channels.find(item => item.channelId === channelId) ?? { channelId, worksheetName: rule.worksheetName, enabled: false, fields: emptyChannelFields() }
  const enabledChannels = rule.channels.filter(channel => channel.enabled)
  const channelIssueCount = enabledChannels.reduce((total, channel) => total + channelValidationIssues(channel.fields, true).length, 0)
  const statusKey = !rule.enabled
    ? 'sources:sourceConfiguration.worksheetStatus.ignored'
    : missingSourceFields.length > 0 || channelIssueCount > 0
      ? 'sources:sourceConfiguration.worksheetStatus.validationErrors'
      : enabledChannels.length === 0
        ? 'sources:sourceConfiguration.worksheetStatus.needsColumns'
        : 'sources:sourceConfiguration.worksheetStatus.ready'
  const statusClass = !rule.enabled ? 'fh-badge-neutral' : missingSourceFields.length > 0 || channelIssueCount > 0 ? 'fh-badge-warning' : enabledChannels.length === 0 ? 'fh-badge-neutral' : 'fh-badge-success'
  const updateSource = (field: string, mapping: FieldMapping) => onChange({ ...rule, sourceFields: rule.sourceFields.map(item => item.field === field ? mapping : item) })
  const updateChannel = (channelId: string, next: ReturnType<typeof configured>) => onChange({ ...rule, channels: [...rule.channels.filter(item => item.channelId !== channelId), next] })
  const updateChannelField = (channelId: string, field: string, mapping: FieldMapping) => {
    const channel = configured(channelId)
    updateChannel(channelId, { ...channel, fields: channel.fields.map(item => item.field === field ? mapping : item) })
  }

  return <details className="rounded-xl border border-border bg-bg-base" data-worksheet-rule={rule.worksheetName} open={expanded} onToggle={event => {
    const next = event.currentTarget.open
    if (next !== expanded) onExpandedChange(next)
  }}>
    <summary className="flex cursor-pointer list-none flex-wrap items-center gap-3 p-4">
      <input type="checkbox" checked={selected} aria-label={translate('sources:sourceConfiguration.selectWorksheet', { worksheet: rule.worksheetName })} onClick={event => event.stopPropagation()} onChange={event => onSelectedChange(event.target.checked)} />
      <Icon name="file" />
      <span className="min-w-0"><strong className="block truncate text-text-base">{rule.worksheetName}</strong>{rowCount != null && <small className="fh-text-caption">{translate('sources:sourceConfiguration.worksheetRowCount', { count: rowCount })}</small>}</span>
      <span className={`fh-badge ${statusClass}`}>{translate(statusKey)}</span>
      <span className="fh-text-caption ms-auto">{translate('sources:sourceConfiguration.enabledChannelCount', { count: enabledChannels.length })}</span>
    </summary>
    <div className="border-t border-border p-4 space-y-5">
      <div className="flex flex-wrap items-end gap-3">
        <label className="fh-inline-check"><input type="checkbox" checked={rule.enabled} onChange={event => onChange({ ...rule, enabled: event.target.checked })} />{rule.enabled ? translate('sources:sourceConfiguration.worksheetIncluded') : translate('sources:sourceConfiguration.worksheetIgnored')}</label>
        <label className="fh-field-label min-w-[220px]">{translate('sources:sourceConfiguration.dataStartsAtRow')}<input className="fh-input mt-1" type="number" min="1" disabled={!rule.enabled} value={rule.dataStartRow} onChange={event => onChange({ ...rule, dataStartRow: Number(event.target.value) })} /></label>
        <button className="fh-button-danger fh-button-sm ms-auto" type="button" onClick={onRemove}><Icon name="delete" /> {translate('sources:sourceConfiguration.removeWorksheetRule')}</button>
      </div>
      <section>
        <div className="flex flex-wrap items-center justify-between gap-3" title={translate('sources:sourceConfiguration.productColumnsHelp')}><h3 className="fh-form-section-title">{translate('sources:sourceConfiguration.productFieldsSharedByChannels')}</h3><button className="fh-button-secondary fh-button-sm" type="button" disabled={!rule.enabled} onClick={() => onRequestCopy({ kind: 'shared_fields', worksheetName: rule.worksheetName })}><Icon name="copy" /> {translate('sources:sourceConfiguration.copySharedFields')}</button></div>
        <div className="mt-3 grid gap-3 lg:grid-cols-2">
          {SOURCE_FIELD_DEFINITIONS.map(([field, key]) => {
            const mapping = rule.sourceFields.find(item => item.field === field) ?? emptyFieldMapping(field, field === 'name')
            const invalid = sourceFieldMissing(mapping)
            return <div className="grid gap-1" key={field}><span className="fh-field-label">{translate(key)}</span><ColumnSelector mapping={mapping} disabled={!rule.enabled} invalid={invalid} describedBy={sourceErrorId} allowInternalColumnId={sourceKind === 'flowhub_sheet'} onChange={value => updateSource(field, value)} /></div>
          })}
        </div>
        {missingSourceFields.length > 0 && <p className="fh-alert-warning mt-3" id={sourceErrorId} role="alert">{translate('sources:sourceConfiguration.sourceProductNameRequired')}</p>}
      </section>
      <section data-worksheet-channel-columns={rule.worksheetName}>
        <h3 className="fh-form-section-title" title={translate('sources:sourceConfiguration.channelMappingsAreIndependent')}>{translate('sources:sourceConfiguration.columnsForEachChannel')}</h3>
        <div className="mt-3 space-y-4">
          <ResourceSectionList resources={channelResources} renderItem={orderedChannel => {
            const channelInfo = orderedChannel.item
            const channel = configured(channelInfo.channelId)
            const disabled = !rule.enabled || !channelInfo.available
            const issues = channelValidationIssues(channel.fields, true)
            const copyResources = prepareResourceCollection(channels.filter(candidate => candidate.channelId !== channelInfo.channelId && rule.channels.some(item => item.channelId === candidate.channelId)), sourceChannelSignals)
            const channelOpen = expandedChannels.includes(channelInfo.channelId)
            return <details className="rounded-lg border border-border bg-bg-subtle" data-channel-rule={channelInfo.channelId} open={channelOpen} onToggle={event => {
              const next = event.currentTarget.open
              if (next && !channelOpen) setExpandedChannels(current => [...new Set([...current, channelInfo.channelId])])
              else if (!next && channelOpen) setExpandedChannels(current => current.filter(channelId => channelId !== channelInfo.channelId))
            }}>
              <summary className="flex cursor-pointer list-none items-center gap-3 p-3"><BrandIcon identity={{ provider: channelInfo.connectorType || channelInfo.channelId, sourceType: channelInfo.connectorType }} label={orderedChannel.displayName} size={40} /><strong className="text-text-base">{orderedChannel.displayName}</strong><ResourceStateBadge badge={orderedChannel.badge} />{issues.length > 0 && <span className="fh-badge fh-badge-warning ms-auto">{translate('sources:sourceConfiguration.issueCount', { count: issues.length })}</span>}</summary>
              <div className="border-t border-border p-3">
                <div className="mb-3 flex flex-wrap items-end gap-2">
                  <label className="fh-field-label min-w-[220px]">{translate('sources:sourceConfiguration.copyMappingFrom')}<select className="fh-input mt-1" disabled={disabled} value={copyFrom[channelInfo.channelId] ?? ''} onChange={event => setCopyFrom(current => ({ ...current, [channelInfo.channelId]: event.target.value }))}><option value="">{translate('sources:sourceConfiguration.selectChannel')}</option><ResourceOptionGroups resources={copyResources} renderLabel={item => item.displayName} /></select></label>
                  <button className="fh-button-secondary fh-button-sm" type="button" disabled={disabled || !copyFrom[channelInfo.channelId]} onClick={() => onRequestCopy({ kind: 'channel_to_channel', worksheetName: rule.worksheetName, sourceChannelId: copyFrom[channelInfo.channelId], targetChannelId: channelInfo.channelId })}>{translate('sources:sourceConfiguration.copyMapping')}</button>
                  <button className="fh-button-secondary fh-button-sm" type="button" disabled={disabled} onClick={() => onRequestCopy({ kind: 'channel_to_worksheets', worksheetName: rule.worksheetName, channelId: channelInfo.channelId })}>{translate('sources:sourceConfiguration.copyToWorksheets')}</button>
                  <button className="fh-button-secondary fh-button-sm" type="button" disabled={disabled} onClick={() => updateChannel(channelInfo.channelId, { ...channel, fields: emptyChannelFields() })}>{translate('sources:sourceConfiguration.clearMapping')}</button>
                </div>
                <div className="grid gap-3 lg:grid-cols-2">{CHANNEL_FIELD_DEFINITIONS.map(([field, key]) => <div className="grid gap-1" key={field}><span className="fh-field-label">{translate(key)}</span><ColumnSelector mapping={channel.fields.find(item => item.field === field) ?? emptyFieldMapping(field)} disabled={disabled} allowInternalColumnId={sourceKind === 'flowhub_sheet'} onChange={value => updateChannelField(channelInfo.channelId, field, value)} /></div>)}</div>
                {issues.length > 0 && <ul className="fh-alert-warning mt-3 list-disc ps-5">{issues.map(issue => <li key={issue}>{issue}</li>)}</ul>}
              </div>
            </details>
          }} />
        </div>
      </section>
      <details className="rounded-lg border border-border bg-bg-subtle p-3">
        <summary className="cursor-pointer font-medium text-text-base" title={translate('sources:sourceConfiguration.eachSpecialValueIsInterpretedExplicitlyCurrency')}>{translate('sources:sourceConfiguration.valueHandling')}</summary>
        <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{Object.entries(POLICY_OPTIONS).map(([key, options]) => <label className="fh-field-label" key={key}>{translate(`sources:sourceConfiguration.valueType.${key}`)}<select className="fh-input mt-1" disabled={!rule.enabled} value={rule.valuePolicy[key] ?? DEFAULT_SOURCE_VALUE_POLICY[key]} onChange={event => onChange({ ...rule, valuePolicy: { ...rule.valuePolicy, [key]: event.target.value } })}>{options.map(([value, label]) => <option value={value} key={value}>{translate(label)}</option>)}</select></label>)}</div>
      </details>
    </div>
  </details>
}
